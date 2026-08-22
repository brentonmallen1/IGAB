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
from igab.sample_budget.data import SAMPLE_BUDGET
from igab.sample_budget.spec import (
    RelDate,
    SampleBudgetSpec,
    ScheduledSpec,
    shift_months,
)
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

        result.assignments = await self._create_assignments(anchor, inserted, projected)
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
                    is_hidden=cat_spec.is_hidden,
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
                liability_type=spec.liability_type,
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
                    category=spec.opening_income_category if acct.on_budget else None,
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
        self, anchor: date, inserted: list[dict], projected: list[dict]
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

        # Sweep the surplus so TBA lands exactly on target. Uses the same
        # balance simulation as BudgetService: TBA = on-budget balances −
        # Σ non-system category available (computed on INSERTED rows only).
        # Mirror BudgetService.get_on_budget: closed accounts don't fund TBA
        on_budget_names = {a.name for a in spec.accounts if a.on_budget and not a.is_closed}
        on_budget_ids = {self._accounts[n].id for n in on_budget_names}
        balances = sum(
            (
                r["amount"]
                for r in inserted
                if r["account_id"] in on_budget_ids and r["parent_transaction_id"] is None
            ),
            _ZERO,
        )

        available_total = _ZERO
        for group_spec in spec.groups:
            if group_spec.name == spec.income_group:
                continue
            for cat_spec in group_spec.categories:
                category = self._categories[cat_spec.name]
                inserted_activity = activity_by_month(inserted, category.id)
                carry = _ZERO
                end = _ZERO
                for m in months:
                    end = (
                        carry
                        + assigned.get((category.id, m), _ZERO)
                        + inserted_activity.get(m, _ZERO)
                    )
                    carry = max(_ZERO, end)
                available_total += end  # current month may be negative

        surplus = balances - available_total - spec.tba_target
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
