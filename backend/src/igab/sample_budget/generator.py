"""Materializes a SampleBudgetSpec into a real budget.

Follows the YNAB importer's bulk pattern: entities via repos, transactions
as one bulk insert with in-memory transfer/split cross-references. The
financial shape is guaranteed, not hoped for:

- Past months are funded to their zero-based budgets, topped up whenever a
  one-off would have pushed an envelope negative ("money was moved to cover
  it"), so no history month shows accidental overspending.
- The current month is funded to its full-month projection, except the one
  category configured to overspend, which is assigned exactly
  `overspend_this_month` below its spending to date.
- After base assignments, the income surplus is swept into the
  `sweep_remainder` category spread across all months, computed so the
  month view's To Be Assigned lands exactly on `spec.tba_target`.
"""

import calendar
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, BudgetAssignment, Category, CategoryGroup, Payee
from igab.domain.cards import card_funding, card_position, card_reserve
from igab.domain.carryover import available_at, available_through, sum_through
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.repositories.tag_repo import TagRepository
from igab.repositories.target_repo import TargetRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.sample_budget.card_scenarios import ExpectedPosition
from igab.sample_budget.data import SAMPLE_BUDGET
from igab.sample_budget.spec import (
    RelDate,
    SampleBudgetSpec,
    ScheduledSpec,
    shift_months,
)
from igab.services.card_payment import ensure_payment_category
from igab.services.liability_service import ensure_for_account
from igab.utils.clock import today_utc

# Sanity ceilings per tier — a spec edit that blows past these is a mistake,
# not ambition. (Insert-safety no longer depends on a single chunk: transfer
# links are applied after the bulk insert, the importer's pattern.)
TIER_ROW_CAPS = {"starter": 1000, "full": 6000}
MAX_TRANSACTION_ROWS = 1000  # fallback cap for unknown tiers

# Rows in the last N days before the anchor look freshly entered
UNCLEARED_DAYS = 5

_CENT = Decimal("0.01")
_ZERO = Decimal("0")


@dataclass
class SampleResult:
    accounts: int = 0
    category_groups: int = 0
    categories: int = 0
    payees: int = 0
    tags_linked: int = 0
    targets: int = 0
    transactions: int = 0
    assignments: int = 0
    scheduled: int = 0
    reconciliations: int = 0
    liabilities: int = 0


class SampleBudgetGenerator:
    def __init__(
        self,
        session: AsyncSession,
        budget_id: uuid.UUID,
        *,
        account_repo: AccountRepository,
        category_group_repo: CategoryGroupRepository,
        category_repo: CategoryRepository,
        payee_repo: PayeeRepository,
        transaction_repo: TransactionRepository,
        assignment_repo: BudgetAssignmentRepository,
        tag_repo: TagRepository,
        target_repo: TargetRepository,
        scheduled_repo: ScheduledTransactionRepository,
        reconciliation_repo: ReconciliationRepository,
        liability_repo: LiabilityRepository,
        spec: SampleBudgetSpec = SAMPLE_BUDGET,
        tier: str = "starter",
    ) -> None:
        self.session = session
        self.budget_id = budget_id
        self.tier = tier
        self.account_repo = account_repo
        self.category_group_repo = category_group_repo
        self.category_repo = category_repo
        self.payee_repo = payee_repo
        self.transaction_repo = transaction_repo
        self.assignment_repo = assignment_repo
        self.tag_repo = tag_repo
        self.target_repo = target_repo
        self.scheduled_repo = scheduled_repo
        self.reconciliation_repo = reconciliation_repo
        self.liability_repo = liability_repo
        self.spec = _filter_spec(spec, tier)

        self._accounts: dict[str, Account] = {}
        self._categories: dict[str, Category] = {}
        self._groups: dict[str, CategoryGroup] = {}
        self._payees: dict[str, Payee] = {}
        self._tags: dict[str, uuid.UUID] = {}

    async def generate(self, anchor: date | None = None) -> SampleResult:
        anchor = anchor or today_utc()
        result = SampleResult()

        await self._create_accounts(result)
        await self._create_categories(anchor, result)
        await self._create_tags_and_payees(result)
        await self._create_liabilities(anchor, result)

        inserted, projected = self._build_transaction_rows(anchor)
        cap = TIER_ROW_CAPS.get(self.tier, MAX_TRANSACTION_ROWS)
        if len(inserted) > cap:
            raise ValueError(
                f"sample data produced {len(inserted)} transactions; the "
                f"'{self.tier}' tier caps at {cap} rows"
            )
        # Insert with transfer links stripped, then link pairs afterwards — a
        # linked pair straddling a bulk_create chunk boundary would violate
        # the self-FK mid-statement.
        links = [
            (row["id"], row["transfer_id"]) for row in inserted if row["transfer_id"] is not None
        ]
        for row in inserted:
            row["transfer_id"] = None
        await self.transaction_repo.bulk_create(inserted)
        await self.transaction_repo.bulk_link_transfers(links)
        result.transactions = len(inserted)

        result.assignments = await self._create_assignments(anchor, inserted, projected, links)
        result.scheduled = await self._create_scheduled(anchor)
        result.reconciliations = await self._create_reconciliation(inserted)

        await self.session.flush()
        return result

    # ─── Entities ─────────────────────────────────────────────────────────────

    async def _create_accounts(self, result: SampleResult) -> None:
        from igab.services.account_type_service import apply_type, resolve_type

        for acct in self.spec.accounts:
            type_row = await resolve_type(self.session, self.budget_id, acct.account_type)
            self._accounts[acct.name] = await self.account_repo.create(
                budget_id=self.budget_id,
                name=acct.name,
                sort_order=acct.sort_order,
                is_closed=acct.is_closed,
                **apply_type(type_row, acct.on_budget),
            )
            result.accounts += 1

    def _write_import_anchor(self, spec, anchor: date):
        """Anchored scenarios' seeds, resolved to real ids and written as
        `ImportAnchor` rows — through `anchor_rows`, the importer's own shape,
        so a demoed anchor is one an import could have produced. One anchor
        per budget, asserted."""
        from igab.domain.cards import AnchorOpenings
        from igab.domain.dates import add_months, month_start
        from igab.repositories.import_anchor_repo import anchor_rows

        anchored = [sc for sc in spec.card_scenarios if sc.import_anchor is not None]
        if not anchored:
            return None
        months = {sc.import_anchor.months_ago for sc in anchored}
        assert len(months) == 1, f"one budget has one anchor month, got {sorted(months)}"
        boundary = add_months(month_start(anchor), -months.pop())
        opening_month = add_months(boundary, -1)
        available: dict[uuid.UUID, Decimal] = {}
        reserve: dict[uuid.UUID, Decimal] = {}
        uncovered: dict[uuid.UUID, Decimal] = {}
        for sc in anchored:
            ia = sc.import_anchor
            card_id = self._accounts[sc.card].id
            reserve[card_id] = ia.reserve
            uncovered[card_id] = ia.uncovered
            named = dict(ia.available)
            for name in sc.categories():
                # Every category the scenario touches gets a row, zeros
                # included — the importer writes a plan's whole B−1 month the
                # same way, and it is the zeros that carry "anchored" to a
                # card whose openings are all zero.
                available[self._categories[name].id] = named.get(name, _ZERO)
        self.session.add_all(
            anchor_rows(
                self.budget_id,
                opening_month,
                available=available,
                reserve=reserve,
                uncovered=uncovered,
            )
        )
        return AnchorOpenings(
            month=boundary,
            available_by_category=available,
            reserve_by_card=reserve,
            uncovered_by_card=uncovered,
        )

    async def _create_categories(self, anchor: date, result: SampleResult) -> None:
        for gi, group_spec in enumerate(self.spec.groups):
            group = await self.category_group_repo.create(
                budget_id=self.budget_id,
                name=group_spec.name,
                sort_order=gi,
                is_system=group_spec.is_system,
            )
            self._groups[group_spec.name] = group
            result.category_groups += 1

            for ci, cat_spec in enumerate(group_spec.categories):
                linked = (
                    self._accounts[cat_spec.linked_account].id if cat_spec.linked_account else None
                )
                category = await self.category_repo.create(
                    budget_id=self.budget_id,
                    category_group_id=group.id,
                    name=cat_spec.name,
                    sort_order=ci,
                    linked_account_id=linked,
                    is_archived=cat_spec.is_archived,
                )
                self._categories[cat_spec.name] = category
                result.categories += 1

                if cat_spec.target is not None:
                    t = cat_spec.target
                    await self.target_repo.create(
                        category_id=category.id,
                        target_type=t.target_type,
                        target_amount=t.amount,
                        target_date=t.target_date.resolve(anchor) if t.target_date else None,
                        repeat_frequency=t.repeat_frequency,
                    )
                    result.targets += 1

    async def _create_tags_and_payees(self, result: SampleResult) -> None:
        for name, color_slot in self.spec.custom_tags:
            await self.tag_repo.create(budget_id=self.budget_id, name=name, color_slot=color_slot)
        self._tags = {t.name: t.id for t in await self.tag_repo.list_for_budget(self.budget_id)}

        def tag_ids(names: tuple[str, ...]) -> list[uuid.UUID]:
            missing = [n for n in names if n not in self._tags]
            if missing:
                raise ValueError(
                    f"unknown tags {missing} — system tags must be seeded before generating"
                )
            return [self._tags[n] for n in names]

        for group_spec in self.spec.groups:
            for cat_spec in group_spec.categories:
                if cat_spec.tags:
                    await self.tag_repo.set_category_tags(
                        self._categories[cat_spec.name].id, tag_ids(cat_spec.tags)
                    )
                    result.tags_linked += len(cat_spec.tags)

        for payee_spec in self.spec.payees:
            default_id = (
                self._categories[payee_spec.default_category].id
                if payee_spec.default_category
                else None
            )
            payee = await self.payee_repo.create(
                budget_id=self.budget_id, name=payee_spec.name, default_category_id=default_id
            )
            self._payees[payee_spec.name] = payee
            result.payees += 1
            if payee_spec.tags:
                await self.tag_repo.set_payee_tags(payee.id, tag_ids(payee_spec.tags))
                result.tags_linked += len(payee_spec.tags)

        # Transfer payees, named the way TransactionService names them
        for acct in self.spec.accounts:
            payee = await self.payee_repo.create(
                budget_id=self.budget_id,
                name=f"Transfer : {acct.name}",
                transfer_account_id=self._accounts[acct.name].id,
            )
            self._payees[payee.name] = payee
            result.payees += 1

    async def _create_liabilities(self, anchor: date, result: SampleResult) -> None:
        for spec in self.spec.liabilities:
            linked_account_id = (
                self._accounts[spec.linked_account].id if spec.linked_account else None
            )
            liability = await self.liability_repo.create(
                budget_id=self.budget_id,
                name=spec.name,
                # Stored only when unmanaged — a linked liability reads its
                # kind off the account, so storing one here would seed the
                # reference dataset with the stale second copy this model
                # exists to remove.
                liability_type=None if linked_account_id else spec.liability_type,
                interest_rate=spec.interest_rate,
                minimum_payment=spec.minimum_payment,
                linked_account_id=linked_account_id,
                manual_balance=spec.balance,
                origination_date=spec.origination.resolve(anchor) if spec.origination else None,
                original_principal=spec.original_principal,
                term_months=spec.term_months,
                promo_end_date=spec.promo_end.resolve(anchor) if spec.promo_end else None,
                promo_deferred_interest=spec.promo_deferred_interest,
            )
            result.liabilities += 1

            for snap in spec.snapshots:
                await self.liability_repo.upsert_snapshot(
                    liability_id=liability.id,
                    snapshot_date=snap.when.resolve(anchor),
                    balance=snap.balance,
                    source="initial",
                )

        # After the specced ones, never before: these carry real terms and
        # linked_account_id is uniquely constrained, so a companion created at
        # account-creation time would occupy the slot the spec wants. Running
        # last makes this fill gaps only — the sample's credit cards get the
        # same empty companion a real user's would, which is the point.
        for account in self._accounts.values():
            if await ensure_for_account(self.session, account) is not None:
                result.liabilities += 1
            # Cards additionally get their set-aside envelope; the showcase
            # spec may have made one already, which ensure() then adopts.
            await ensure_payment_category(self.session, account)

    # ─── Transactions ─────────────────────────────────────────────────────────

    def _cleared_for(self, account_name: str, d: date, anchor: date) -> str:
        if d > anchor - timedelta(days=UNCLEARED_DAYS):
            return "uncleared"
        recon_cutoff = date(*shift_months(anchor, 1), 1)
        if self.tier == "full":
            # Real multi-year budgets end up almost entirely reconciled —
            # everything older than two months, on every account, plus the
            # primary checking through last month (matching the starter rule).
            deep_cutoff = date(*shift_months(anchor, 2), 1)
            if d < deep_cutoff:
                return "reconciled"
        if account_name == self.spec.accounts[0].name and d < recon_cutoff:
            return "reconciled"
        return "cleared"

    def _row(
        self,
        account_name: str,
        d: date,
        amount: Decimal,
        anchor: date,
        *,
        payee: str | None = None,
        category: str | None = None,
        memo: str | None = None,
        is_split: bool = False,
        parent_id: uuid.UUID | None = None,
        cleared: str | None = None,
    ) -> dict:
        return {
            "id": uuid.uuid4(),
            "budget_id": self.budget_id,
            "account_id": self._accounts[account_name].id,
            "date": d,
            "amount": amount,
            "payee_id": self._payees[payee].id if payee else None,
            "category_id": self._categories[category].id if category else None,
            "memo": memo,
            "cleared": cleared or self._cleared_for(account_name, d, anchor),
            "approved": True,
            "is_split": is_split,
            "is_deleted": False,
            "transfer_id": None,
            "parent_transaction_id": parent_id,
        }

    def _build_transaction_rows(self, anchor: date) -> tuple[list[dict], list[dict]]:
        """All rows for the 13-month window, split into (inserted, projected).

        Projected rows are the current month's remainder past the anchor;
        they exist only to compute full-month assignments and are never
        written to the database.
        """
        spec = self.spec
        rows: list[dict] = []
        opening_when = RelDate(spec.months_of_history, 1)

        for acct in spec.accounts:
            if acct.opening_balance == 0:
                continue
            rows.append(
                self._row(
                    acct.name,
                    opening_when.resolve(anchor),
                    acct.opening_balance,
                    anchor,
                    payee="Starting Balance",
                    # The rule `_anchor_opening_balance` follows on a real
                    # first sync: on a cash account the opening gap is income
                    # into Ready to Assign, on a card it is pre-history debt
                    # and stays uncategorized so it shows as Uncovered. A
                    # negative opening balance filed to an income category
                    # reaches no envelope at all — harmless for the arithmetic,
                    # but it made the generated budget the one place in the app
                    # where that shape existed, and the integrity check that
                    # names it (`outflows_filed_as_income`) was right to.
                    category=(
                        spec.opening_income_category
                        if acct.on_budget and acct.opening_balance > 0
                        else None
                    ),
                    memo="Starting balance",
                )
            )

        for months_ago in range(spec.months_of_history, -1, -1):
            year, month = shift_months(anchor, months_ago)
            month_len = calendar.monthrange(year, month)[1]

            for m in spec.monthly:
                d = date(year, month, min(m.day, month_len))
                if m.splits:
                    lines = m.splits[(month - 1) % len(m.splits)]
                    parent = self._row(
                        m.account,
                        d,
                        sum((line.amount for line in lines), _ZERO),
                        anchor,
                        payee=m.payee,
                        memo=m.memo,
                        is_split=True,
                    )
                    rows.append(parent)
                    for line in lines:
                        rows.append(
                            self._row(
                                m.account,
                                d,
                                line.amount,
                                anchor,
                                payee=m.payee,
                                category=line.category,
                                memo=line.memo,
                                parent_id=parent["id"],
                                cleared=parent["cleared"],
                            )
                        )
                else:
                    rows.append(
                        self._row(
                            m.account,
                            d,
                            m.amounts[(month - 1) % len(m.amounts)],
                            anchor,
                            payee=m.payee,
                            category=m.category,
                            memo=m.memo,
                        )
                    )

            for t in spec.transfers:
                d = date(year, month, min(t.day, month_len))
                out_row = self._row(
                    t.from_account,
                    d,
                    -t.amount,
                    anchor,
                    payee=f"Transfer : {t.to_account}",
                    category=t.category,
                    memo=t.memo,
                )
                in_row = self._row(
                    t.to_account,
                    d,
                    t.amount,
                    anchor,
                    payee=f"Transfer : {t.from_account}",
                    memo=t.memo,
                )
                out_row["transfer_id"] = in_row["id"]
                in_row["transfer_id"] = out_row["id"]
                rows.extend([out_row, in_row])

        window_start = opening_when.resolve(anchor)
        window_end = date(
            anchor.year, anchor.month, calendar.monthrange(anchor.year, anchor.month)[1]
        )
        for w in spec.weekly:
            occurrence = 0
            d = window_start
            while d <= window_end:
                if d.weekday() in w.weekdays:
                    rows.append(
                        self._row(
                            w.account,
                            d,
                            w.amounts[occurrence % len(w.amounts)],
                            anchor,
                            payee=w.payees[occurrence % len(w.payees)],
                            category=w.category,
                            memo=w.memo,
                        )
                    )
                    occurrence += 1
                d += timedelta(days=1)

        for o in spec.one_offs:
            d = o.when.resolve(anchor)
            if o.splits:
                parent = self._row(
                    o.account,
                    d,
                    sum((line.amount for line in o.splits), _ZERO),
                    anchor,
                    payee=o.payee,
                    memo=o.memo,
                    is_split=True,
                )
                rows.append(parent)
                for line in o.splits:
                    rows.append(
                        self._row(
                            o.account,
                            d,
                            line.amount,
                            anchor,
                            payee=o.payee,
                            category=line.category,
                            memo=line.memo,
                            parent_id=parent["id"],
                            cleared=parent["cleared"],
                        )
                    )
            else:
                rows.append(
                    self._row(
                        o.account,
                        d,
                        o.amount,
                        anchor,
                        payee=o.payee,
                        category=o.category,
                        memo=o.memo,
                    )
                )

        # One-off transfers. Both legs, mutually linked, never categorised —
        # a card payment is on-budget to on-budget, and only a paired transfer
        # spends the card's reserve. `generate()` strips and re-applies the
        # link either side of the bulk insert, same as the recurring ones.
        for ot in spec.one_off_transfers:
            d = ot.when.resolve(anchor)
            out_row = self._row(
                ot.from_account,
                d,
                -ot.amount,
                anchor,
                payee=f"Transfer : {ot.to_account}",
                memo=ot.memo,
            )
            in_row = self._row(
                ot.to_account,
                d,
                ot.amount,
                anchor,
                payee=f"Transfer : {ot.from_account}",
                memo=ot.memo,
            )
            out_row["transfer_id"] = in_row["id"]
            in_row["transfer_id"] = out_row["id"]
            rows.extend([out_row, in_row])

        inserted = [r for r in rows if r["date"] <= anchor]
        projected = [r for r in rows if r["date"] > anchor]

        # A projected transfer partner must not leave a dangling FK reference
        inserted_ids = {r["id"] for r in inserted}
        for r in inserted:
            if r["transfer_id"] is not None and r["transfer_id"] not in inserted_ids:
                r["transfer_id"] = None

        # Split parents must precede their children in the insert order
        inserted.sort(key=lambda r: r["parent_transaction_id"] is not None)
        return inserted, projected

    # ─── Assignments ──────────────────────────────────────────────────────────

    async def _create_assignments(
        self,
        anchor: date,
        inserted: list[dict],
        projected: list[dict],
        transfer_links: list[tuple[uuid.UUID, uuid.UUID]],
    ) -> int:
        spec = self.spec
        months = [date(*shift_months(anchor, n), 1) for n in range(spec.months_of_history, -1, -1)]
        current_month = months[-1]

        def activity_by_month(rows: list[dict], category_id: uuid.UUID) -> dict[date, Decimal]:
            out: dict[date, Decimal] = {}
            for r in rows:
                if r["category_id"] == category_id and not r["is_split"]:
                    key = r["date"].replace(day=1)
                    out[key] = out.get(key, _ZERO) + r["amount"]
            return out

        all_rows = inserted + projected
        assigned: dict[tuple[uuid.UUID, date], Decimal] = {}
        sweep_category: Category | None = None

        for group_spec in spec.groups:
            if group_spec.name == spec.income_group:
                continue
            for cat_spec in group_spec.categories:
                category = self._categories[cat_spec.name]
                if cat_spec.sweep_remainder:
                    sweep_category = category
                if cat_spec.assignments_are_explicit:
                    # Stated, not inferred. The loop below would fund away the
                    # very shortfall the scenario exists to demonstrate.
                    continue
                full_activity = activity_by_month(all_rows, category.id)
                inserted_activity = activity_by_month(inserted, category.id)

                carry = _ZERO
                for m in months:
                    if m == current_month and cat_spec.overspend_this_month is not None:
                        spent_so_far = -inserted_activity.get(m, _ZERO)
                        amount = max(_ZERO, spent_so_far - cat_spec.overspend_this_month)
                    elif cat_spec.monthly_budget is None:
                        # Bill-like: funded to exactly what the month spends
                        amount = max(_ZERO, -full_activity.get(m, _ZERO))
                    else:
                        amount = cat_spec.monthly_budget
                        shortfall = -(carry + amount + full_activity.get(m, _ZERO))
                        if shortfall > 0:
                            amount += shortfall  # topped up to cover a big one-off
                    if amount != 0:
                        assigned[(category.id, m)] = amount
                    carry = max(_ZERO, carry + amount + full_activity.get(m, _ZERO))

        # Assignments the spec states outright, added on top of the derived
        # ones. This is the only way money reaches a card's payment envelope:
        # nothing can be filed to one, so its activity is always empty and the
        # inference above always yields zero. Added here, before the identity
        # below reads them, so a paydown assignment counts in the envelope
        # term exactly as the budget page counts it.
        for ea in spec.explicit_assignments:
            category = self._categories[ea.category]
            month = ea.when.resolve(anchor).replace(day=1)
            key = (category.id, month)
            assigned[key] = assigned.get(key, _ZERO) + ea.amount

        # Sweep the surplus so TBA lands exactly on target, mirroring
        # BudgetService's identity with the domain's own functions:
        #   TBA = cash balances − Σ envelope available (cards' set-aside
        #   envelopes included) − uncovered_current
        # computed on INSERTED rows only. Cash excludes cards — a card's debt
        # lives beside its set-aside, not in cash (domain/cards.py). Closed
        # accounts stay in; closing moves no money.
        on_budget_names = {a.name for a in spec.accounts if a.on_budget}
        on_budget_ids = {self._accounts[n].id for n in on_budget_names}
        card_ids = {
            aid
            for aid in on_budget_ids
            for a in [next(a for a in self._accounts.values() if a.id == aid)]
            if a.classification == "liability"
        }
        cash_ids = on_budget_ids - card_ids
        balances = sum(
            (
                r["amount"]
                for r in inserted
                if r["account_id"] in cash_ids and r["parent_transaction_id"] is None
            ),
            _ZERO,
        )

        available_total = _ZERO
        assigned_by_cat: dict[uuid.UUID, dict[date, Decimal]] = {}
        activity_by_cat: dict[uuid.UUID, dict[date, Decimal]] = {}
        credit_outflows: dict[uuid.UUID, dict[uuid.UUID, dict[date, Decimal]]] = {}
        # card -> its payment category, and that category's assignments. They
        # go into `card_funding` (which needs them to retire riding debt) but
        # NOT into `assigned_by_cat`, whose loop below is the envelope term and
        # would count a card's reserve a second time.
        card_categories: dict[uuid.UUID, uuid.UUID] = {}
        card_category_assigned: dict[uuid.UUID, dict[date, Decimal]] = {}
        for group_spec in spec.groups:
            if group_spec.name == spec.income_group:
                continue
            for cat_spec in group_spec.categories:
                category = self._categories[cat_spec.name]
                asg = {
                    m: assigned[(category.id, m)] for m in months if (category.id, m) in assigned
                }
                if cat_spec.linked_account:
                    # A card's set-aside envelope — simulated below from
                    # funded credit and payments, not from the spec loop.
                    card_categories[self._accounts[cat_spec.linked_account].id] = category.id
                    card_category_assigned[category.id] = asg
                    continue
                inserted_activity = activity_by_month(inserted, category.id)
                assigned_by_cat[category.id] = asg
                activity_by_cat[category.id] = inserted_activity
                by_card: dict[uuid.UUID, dict[date, Decimal]] = {}
                for r in inserted:
                    if (
                        r["category_id"] == category.id
                        and not r["is_split"]
                        and r["account_id"] in card_ids
                    ):
                        key = r["date"].replace(day=1)
                        per = by_card.setdefault(r["account_id"], {})
                        per[key] = per.get(key, _ZERO) - r["amount"]
                for card_id, outflows in by_card.items():
                    net = {m: v for m, v in outflows.items() if v != 0}
                    if net:
                        credit_outflows.setdefault(category.id, {})[card_id] = net

        # An anchored scenario's seeds, resolved to real ids, and its rows
        # written the way the importer writes them — the verification below
        # then exercises the same anchored walk the app serves.
        openings = self._write_import_anchor(spec, anchor)
        funding = card_funding(
            assigned_by_cat | card_category_assigned,
            activity_by_cat,
            credit_outflows,
            card_categories,
            openings=openings,
        )
        # The envelope term of the identity, read the way the budget page reads
        # it: out of `card_funding`'s adjusted series for any category a card
        # inflow corrected, and the ordinary simulation for the rest. Summing
        # the raw series here while the page sums the adjusted one is how a
        # generated budget silently misses its own TBA target.
        for cat_id, asg in assigned_by_cat.items():
            adjusted = funding.end_balances.get(cat_id)
            available_total += (
                available_at(adjusted, current_month)
                if adjusted is not None
                else available_through(
                    asg,
                    activity_by_cat[cat_id],
                    current_month,
                    # Anchored budgets truncate EVERY category at the
                    # boundary, opening at the anchor's figure (zero when it
                    # names none) — the serving side's rule, mirrored.
                    opening=openings.opening_for(cat_id) if openings is not None else None,
                )
            )
        # Card inflows: forbidden outright where the spec declares no
        # scenarios, contracted per card where it does.
        #
        # This used to be an unconditional "the register has no card inflow at
        # all", which was true and which forbade the refund, reimbursement and
        # repayment shapes from ever being demoed. The replacement is
        # stronger, not weaker: below, every declared card must land exactly
        # where its scenario says, so an unintended inflow fails because the
        # position moved — and an intended one is finally expressible.
        if not spec.card_scenarios:
            assert not funding.repaid_by_category, (
                "sample register grew an uncovered-debt repayment"
            )
            assert not funding.residual_by_card, "sample register grew an unmatched card inflow"
        # Payments come from the captured link pairs — generate() strips
        # `transfer_id` off these very dicts before bulk insert, so the rows
        # themselves no longer say they are transfers.
        rows_by_id = {r["id"]: r for r in inserted}
        payments: dict[uuid.UUID, dict[date, Decimal]] = {}
        paid_leg_ids: set[uuid.UUID] = set()
        for leg_id, partner_id in transfer_links:
            leg = rows_by_id.get(leg_id)
            partner = rows_by_id.get(partner_id)
            if (
                leg is not None
                and partner is not None
                and leg["account_id"] in card_ids
                and partner["account_id"] in cash_ids
                and leg["amount"] > 0
            ):
                key = leg["date"].replace(day=1)
                per = payments.setdefault(leg["account_id"], {})
                per[key] = per.get(key, _ZERO) + leg["amount"]
                paid_leg_ids.add(leg["id"])
        scenario_by_card_id = {
            self._accounts[sc.card].id: sc
            for sc in spec.card_scenarios
            if sc.card in self._accounts
        }
        card_balances: dict[uuid.UUID, Decimal] = {}
        for r in inserted:
            if r["account_id"] in card_ids and not r["is_split"]:
                card_balances[r["account_id"]] = (
                    card_balances.get(r["account_id"], _ZERO) + r["amount"]
                )
        if openings is not None:
            payments = {
                card_id: {m: v for m, v in series.items() if m >= openings.month}
                for card_id, series in payments.items()
            }
        for card_id in card_ids:
            opening_leg = (
                {openings.opening_month: openings.reserve_by_card.get(card_id, _ZERO)}
                if openings is not None
                else None
            )
            set_aside = card_reserve(
                funding, card_id, payments.get(card_id, {}), opening=opening_leg
            ).set_aside(current_month)
            available_total += set_aside
            scenario = scenario_by_card_id.get(card_id)
            if scenario is None:
                # A card with no scenario keeps the old guarantee, now said
                # per card rather than over the whole register: it may not
                # take an inflow. Ordinary textured spending is welcome — what
                # is not is a refund or a reimbursement landing on a card
                # whose resulting position nobody declared, which is the state
                # the demo used to be in wholesale.
                stray = [
                    r
                    for r in inserted
                    if r["account_id"] == card_id
                    and r["amount"] > _ZERO
                    and r["id"] not in paid_leg_ids
                ]
                assert not stray, (
                    f"card {card_id} takes an inflow but is "
                    "not a declared scenario — say what it should read, in card_scenarios.py"
                )
                continue
            balance = card_balances.get(card_id, _ZERO)
            position = card_position(set_aside, balance)
            # The month ledger off the rows actually inserted — the same
            # posted-parent-row terms `card_month_flows` sums, so an event
            # generated into the wrong month fails here, in the generator,
            # before any test reads the served summary.
            month_rows = [
                r
                for r in inserted
                if r["account_id"] == card_id
                and not r["is_split"]
                and r["date"].replace(day=1) == current_month
                and r.get("cleared") != "pending"
            ]
            charged = -sum((r["amount"] for r in month_rows if r["amount"] < _ZERO), _ZERO)
            inflows = sum((r["amount"] for r in month_rows if r["amount"] > _ZERO), _ZERO)
            differences = scenario.expect.differences(
                ExpectedPosition(
                    balance=balance,
                    set_aside=set_aside,
                    uncovered=position.uncovered,
                    over_reserved=position.over_reserved,
                    short_reserved=position.short_reserved,
                    card_credit=position.card_credit,
                    riding=sum_through(funding.riding_by_card.get(card_id, {}), current_month),
                    charged_this_month=charged,
                    inflows_this_month=inflows,
                    paid_this_month=payments.get(card_id, {}).get(current_month, _ZERO),
                    debt_change_this_month=inflows - charged,
                )
            )
            assert not differences, (
                f"scenario {scenario.slug!r} does not land where it says: "
                f"{differences} (want, got). {scenario.story}"
            )
        uncovered_current = sum(
            (
                by_month.get(current_month, _ZERO)
                for by_month in funding.floored_by_category.values()
            ),
            _ZERO,
        )

        surplus = balances - available_total - uncovered_current - spec.tba_target
        if sweep_category is None or surplus < 0:
            raise ValueError(
                f"sample spec cannot reach TBA target {spec.tba_target}: surplus={surplus}, "
                "sweep category "
                + ("missing" if sweep_category is None else "cannot absorb a deficit")
            )
        per_month = (surplus / len(months)).quantize(_CENT, rounding=ROUND_DOWN)
        for m in months:
            key = (sweep_category.id, m)
            extra = per_month if m != current_month else surplus - per_month * (len(months) - 1)
            assigned[key] = assigned.get(key, _ZERO) + extra

        self.session.add_all(
            BudgetAssignment(budget_id=self.budget_id, category_id=cat_id, month=m, assigned=amount)
            for (cat_id, m), amount in assigned.items()
        )
        await self.session.flush()
        return len(assigned)

    # ─── Scheduled transactions ───────────────────────────────────────────────

    async def _create_scheduled(self, anchor: date) -> int:
        count = 0
        for s in self.spec.scheduled:
            start_months_ago = (
                s.last_occurrence_months_ago
                if s.frequency == "yearly"
                else self.spec.months_of_history
            )
            await self.scheduled_repo.create(
                budget_id=self.budget_id,
                account_id=self._accounts[s.account].id,
                amount=s.amount,
                payee_id=self._payees[s.payee].id if s.payee else None,
                category_id=self._categories[s.category].id if s.category else None,
                memo=s.memo,
                frequency=s.frequency,
                start_date=RelDate(start_months_ago, s.day).resolve(anchor),
                second_day_of_month=s.second_day_of_month,
                auto_create=False,
                transfer_account_id=(
                    self._accounts[s.transfer_account].id if s.transfer_account else None
                ),
                next_occurrence_date=_next_occurrence(s, anchor),
            )
            count += 1
        return count

    # ─── Reconciliation ───────────────────────────────────────────────────────

    async def _create_reconciliation(self, inserted: list[dict]) -> int:
        # Starter reconciles only the primary checking; the full tier stamps
        # every account that has reconciled rows (matching _cleared_for).
        names = (
            [a.name for a in self.spec.accounts]
            if self.tier == "full"
            else [self.spec.accounts[0].name]
        )
        count = 0
        for name in names:
            account = self._accounts[name]
            reconciled_total = sum(
                (
                    r["amount"]
                    for r in inserted
                    if r["account_id"] == account.id
                    and r["cleared"] == "reconciled"
                    and r["parent_transaction_id"] is None
                ),
                _ZERO,
            )
            if reconciled_total == 0:
                continue
            await self.reconciliation_repo.create(
                account_id=account.id,
                statement_balance=reconciled_total,
                cleared_balance=reconciled_total,
                note="Sample statement reconciliation",
            )
            await self.account_repo.update(
                account.id,
                last_reconciled_at=datetime.now(tz=UTC),
                last_reconciled_balance=reconciled_total,
            )
            count += 1
        return count


def _filter_spec(spec: SampleBudgetSpec, tier: str) -> SampleBudgetSpec:
    """The spec as one tier sees it: elements filtered by their `tiers` tag,
    window/target overridden per tier. The generator then runs unchanged —
    the starter output is byte-identical to the pre-tiering data."""

    def keep(items):
        return tuple(item for item in items if tier in item.tiers)

    groups = tuple(
        replace(g, categories=keep(g.categories)) for g in spec.groups if tier in g.tiers
    )
    overrides = dict(spec.tier_overrides).get(tier)
    return replace(
        spec,
        accounts=keep(spec.accounts),
        groups=groups,
        payees=keep(spec.payees),
        monthly=keep(spec.monthly),
        weekly=keep(spec.weekly),
        one_offs=keep(spec.one_offs),
        transfers=keep(spec.transfers),
        scheduled=keep(spec.scheduled),
        liabilities=keep(spec.liabilities),
        one_off_transfers=keep(spec.one_off_transfers),
        explicit_assignments=keep(spec.explicit_assignments),
        # Filtered like everything else: a full-tier card's payment surviving
        # into the starter would pay an account that is not there.
        card_scenarios=keep(spec.card_scenarios),
        months_of_history=(overrides.months_of_history if overrides else spec.months_of_history),
        tba_target=overrides.tba_target if overrides else spec.tba_target,
    )


def _next_occurrence(s: ScheduledSpec, anchor: date) -> date:
    """First occurrence strictly after the anchor."""

    def day_in(year: int, month: int, day: int) -> date:
        return date(year, month, min(day, calendar.monthrange(year, month)[1]))

    if s.frequency == "twice_monthly" and s.second_day_of_month is not None:
        candidates = sorted((s.day, s.second_day_of_month))
        for day in candidates:
            candidate = day_in(anchor.year, anchor.month, day)
            if candidate > anchor:
                return candidate
        year, month = shift_months(anchor, -1)
        return day_in(year, month, candidates[0])

    if s.frequency == "yearly":
        last = RelDate(s.last_occurrence_months_ago, s.day).resolve(anchor)
        nxt = day_in(last.year + 1, last.month, s.day)
        while nxt <= anchor:
            nxt = day_in(nxt.year + 1, nxt.month, s.day)
        return nxt

    # monthly (the only other frequency used by the sample data)
    candidate = day_in(anchor.year, anchor.month, s.day)
    if candidate > anchor:
        return candidate
    year, month = shift_months(anchor, -1)
    return day_in(year, month, s.day)
