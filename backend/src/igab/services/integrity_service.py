"""Live financial-integrity checks, runnable against production data anytime.

Mirrors the test-suite invariant checker (tests/integration/invariants.py):
money conservation across the two aggregation shapes, split integrity,
transfer pairing, and hygiene checks for matches and stale pendings. Drift
becomes visible immediately instead of surfacing months later as an
unexplainable balance.
"""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from igab.db.models import (
    Account,
    BudgetAssignment,
    Category,
    CategoryGroup,
    Payee,
    ScheduledTransaction,
    Transaction,
    TransactionMatch,
)
from igab.domain.splits import split_balances, split_sum
from igab.domain.transfers import leg_may_carry_category
from igab.guide.detection import budget_service_from
from igab.repositories.category_filters import LINKED_TO_CARD, UNDER_DELETED_GROUP
from igab.services.card_payment import CARD_PAYMENTS_GROUP
from igab.utils.clock import today_utc

STALE_PENDING_DAYS = 21
MAX_DETAILS = 20


@dataclass
class IntegrityCheck:
    name: str
    description: str
    passed: bool
    problem_count: int = 0
    details: list[str] = field(default_factory=list)


@dataclass
class IntegrityReport:
    all_passed: bool
    checks: list[IntegrityCheck]


class IntegrityService:
    def __init__(self, session: AsyncSession, budget_service=None) -> None:
        self.session = session
        # The card reserve check reads `CardStatus.reserve_discrepancy` off the
        # budget summary rather than re-deriving it, so the check and the page
        # cannot tell different stories about the same card. Built here the way
        # the DI layer builds it; injectable so a caller that already has one
        # does not pay for a second.
        self._budget_service = budget_service or budget_service_from(session)

    async def run(self, budget_id: uuid.UUID) -> IntegrityReport:
        checks = [
            await self._check_split_integrity(budget_id),
            await self._check_transfer_integrity(budget_id),
            await self._check_money_conservation(budget_id),
            await self._check_orphaned_matches(budget_id),
            await self._check_orphaned_categories(budget_id),
            await self._check_stale_pendings(budget_id),
            await self._check_card_envelope_rows(budget_id),
            await self._check_card_payment_envelope_pairing(budget_id),
            await self._check_card_reserve_identity(budget_id),
        ]
        return IntegrityReport(all_passed=all(c.passed for c in checks), checks=checks)

    async def _check_orphaned_categories(self, budget_id: uuid.UUID) -> IntegrityCheck:
        """Anything still pointing at a deleted category.

        This is the one place that watches for the whole class, rather than
        adding a `Category.is_deleted` filter to each of the twelve report
        queries that join categories. Before deleting became a real operation
        it left every referrer dangling, and the results disagreed by
        construction: a transaction reported `needs_category = False` while
        rendering as unfiled, Spending by Category still listed the deleted
        name, Budget vs Actual showed the same money as "Unknown", and a
        future-month assignment stayed subtracted from an earlier month's
        Ready to Assign.

        Anything found here predates that fix (or came in through a path that
        bypasses `CategoryService`); the hygiene repair action clears it.
        """
        problems: list[str] = []

        async def _names(stmt) -> list[str]:
            return [str(r) for r in (await self.session.execute(stmt)).scalars().all()]

        dead = (
            select(Category.id)
            .where(
                Category.budget_id == budget_id,
                Category.is_deleted == True,  # noqa: E712
            )
            .scalar_subquery()
        )

        txns = await _names(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.category_id.in_(dead),
            )
        )
        if txns and int(txns[0]) > 0:
            problems.append(f"{txns[0]} transactions filed in a deleted category")

        assignments = await _names(
            select(func.count())
            .select_from(BudgetAssignment)
            .where(
                BudgetAssignment.budget_id == budget_id,
                BudgetAssignment.category_id.in_(dead),
            )
        )
        if assignments and int(assignments[0]) > 0:
            problems.append(
                f"{assignments[0]} assignments on a deleted category "
                "(money deducted from Ready to Assign with no envelope holding it)"
            )

        payees = await _names(
            select(func.count())
            .select_from(Payee)
            .where(
                Payee.budget_id == budget_id,
                Payee.is_deleted == False,  # noqa: E712
                Payee.default_category_id.in_(dead),
            )
        )
        if payees and int(payees[0]) > 0:
            problems.append(f"{payees[0]} payees defaulting to a deleted category")

        scheduled = await _names(
            select(func.count())
            .select_from(ScheduledTransaction)
            .where(
                ScheduledTransaction.budget_id == budget_id,
                ScheduledTransaction.is_deleted == False,  # noqa: E712
                ScheduledTransaction.category_id.in_(dead),
            )
        )
        if scheduled and int(scheduled[0]) > 0:
            problems.append(f"{scheduled[0]} scheduled transactions on a deleted category")

        # A live category under a deleted group: gone from the grid, which
        # renders only groups it was given, but still in the budget summary.
        stranded = await _names(
            select(func.count())
            .select_from(Category)
            .where(
                Category.budget_id == budget_id,
                Category.is_deleted == False,  # noqa: E712
                UNDER_DELETED_GROUP,
            )
        )
        if stranded and int(stranded[0]) > 0:
            problems.append(
                f"{stranded[0]} live categories under a deleted group "
                "(invisible on the budget page, still reducing Ready to Assign)"
            )

        return self._result(
            "orphaned_categories",
            "Nothing still points at a deleted category",
            problems,
        )

    async def _check_split_integrity(self, budget_id: uuid.UUID) -> IntegrityCheck:
        problems: list[str] = []
        parents = (
            (
                await self.session.execute(
                    select(Transaction).where(
                        Transaction.budget_id == budget_id,
                        Transaction.is_split == True,  # noqa: E712
                        Transaction.is_deleted == False,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        for parent in parents:
            children = (
                (
                    await self.session.execute(
                        select(Transaction).where(
                            Transaction.parent_transaction_id == parent.id,
                            Transaction.is_deleted == False,  # noqa: E712
                        )
                    )
                )
                .scalars()
                .all()
            )
            child_sum = split_sum(c.amount for c in children)
            if not children:
                problems.append(f"split {parent.id} ({parent.date}) has no lines")
            elif not split_balances(parent.amount, [c.amount for c in children]):
                problems.append(
                    f"split {parent.id} ({parent.date}): total {parent.amount} "
                    f"!= lines sum {child_sum}"
                )
            if parent.category_id is not None:
                problems.append(f"split {parent.id} carries a category directly")
            for child in children:
                if child.date != parent.date or child.cleared != parent.cleared:
                    problems.append(
                        f"split line {child.id} out of sync with its parent "
                        f"({parent.id}) on date/cleared"
                    )
        return self._result(
            "split_integrity",
            "Every split's lines sum to its total and mirror its date/status",
            problems,
        )

    async def _check_transfer_integrity(self, budget_id: uuid.UUID) -> IntegrityCheck:
        problems: list[str] = []
        legs = (
            (
                await self.session.execute(
                    select(Transaction).where(
                        Transaction.budget_id == budget_id,
                        Transaction.transfer_id.isnot(None),
                        Transaction.is_deleted == False,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        by_id = {leg.id: leg for leg in legs}
        accounts = {
            a.id: a
            for a in (
                await self.session.execute(select(Account).where(Account.budget_id == budget_id))
            )
            .scalars()
            .all()
        }
        for leg in legs:
            if leg.transfer_id is None:  # narrowed by the query; guard for typing
                continue
            partner = by_id.get(leg.transfer_id)
            if partner is None:
                problems.append(
                    f"transfer {leg.id} ({leg.date}, {leg.amount}) points at a "
                    "missing or deleted partner"
                )
                continue
            if partner.transfer_id != leg.id:
                problems.append(f"transfer link not mutual: {leg.id} ↔ {partner.id}")
            if leg.amount != -partner.amount:
                problems.append(
                    f"transfer pair {leg.id}/{partner.id} does not sum to zero: "
                    f"{leg.amount} vs {partner.amount}"
                )
            if leg.category_id is not None:
                own = accounts.get(leg.account_id)
                partner_acct = accounts.get(partner.account_id)
                if not (
                    own
                    and partner_acct
                    and leg_may_carry_category(own.on_budget, partner_acct.on_budget)
                ):
                    problems.append(
                        f"transfer leg {leg.id} is categorized but is not the "
                        "on-budget side of an off-budget transfer"
                    )
        return self._result(
            "transfer_integrity",
            "Transfer pairs are mutually linked, zero-sum, and validly categorized",
            problems,
        )

    async def _check_money_conservation(self, budget_id: uuid.UUID) -> IntegrityCheck:
        posted_on_budget = and_(
            Transaction.budget_id == budget_id,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.cleared != "pending",
            Account.on_budget == True,  # noqa: E712
        )

        async def _sum(*extra) -> Decimal:
            result = await self.session.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0))
                .join(Account, Transaction.account_id == Account.id)
                .where(posted_on_budget, *extra)
            )
            return Decimal(str(result.scalar_one()))

        parent_total = await _sum(Transaction.parent_transaction_id.is_(None))
        leaf = Transaction.is_split == False  # noqa: E712
        categorized = await _sum(leaf, Transaction.category_id.isnot(None))
        uncategorized_plain = await _sum(
            leaf, Transaction.category_id.is_(None), Transaction.transfer_id.is_(None)
        )
        uncategorized_transfer = await _sum(
            leaf, Transaction.category_id.is_(None), Transaction.transfer_id.isnot(None)
        )
        leaf_total = categorized + uncategorized_plain + uncategorized_transfer

        problems: list[str] = []
        if parent_total != leaf_total:
            problems.append(
                f"account-shape total {parent_total} != category-shape total "
                f"{leaf_total} (categorized {categorized}, uncategorized "
                f"{uncategorized_plain}, transfers {uncategorized_transfer})"
            )
        return self._result(
            "money_conservation",
            "Account balances and category activity see the same money",
            problems,
        )

    async def _check_orphaned_matches(self, budget_id: uuid.UUID) -> IntegrityCheck:
        synced = aliased(Transaction)
        manual = aliased(Transaction)
        result = await self.session.execute(
            select(TransactionMatch.id)
            .join(synced, TransactionMatch.synced_transaction_id == synced.id)
            .join(manual, TransactionMatch.manual_transaction_id == manual.id)
            .where(
                synced.budget_id == budget_id,
                TransactionMatch.status == "pending",
                or_(
                    synced.is_deleted == True,  # noqa: E712
                    manual.is_deleted == True,  # noqa: E712
                ),
            )
        )
        problems = [f"pending match {mid} references a deleted transaction" for (mid,) in result]
        return self._result(
            "orphaned_matches",
            "No pending review matches point at deleted transactions",
            problems,
        )

    async def _check_stale_pendings(self, budget_id: uuid.UUID) -> IntegrityCheck:
        cutoff = today_utc() - timedelta(days=STALE_PENDING_DAYS)
        result = await self.session.execute(
            select(Transaction.id, Transaction.date, Transaction.amount).where(
                Transaction.budget_id == budget_id,
                Transaction.cleared == "pending",
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.date < cutoff,
            )
        )
        problems = [
            f"pending transaction {tid} from {tdate} ({amount}) is older than "
            f"{STALE_PENDING_DAYS} days"
            for tid, tdate, amount in result
        ]
        return self._result(
            "stale_pendings",
            f"No pending transactions older than {STALE_PENDING_DAYS} days",
            problems,
        )

    async def _check_card_envelope_rows(self, budget_id: uuid.UUID) -> IntegrityCheck:
        """Rows filed to a card's set-aside envelope — money that vanished.

        The budget summary computes that envelope's balance from card
        arithmetic and overwrites its transaction sums, so such a row shows
        nowhere: not in the envelope, not in Ready to Assign, not as
        overspending. `require_not_card_envelope` makes new ones impossible;
        this finds any the register's old category dropdown let through,
        because nothing else in the app would ever mention them.
        """
        result = await self.session.execute(
            select(Transaction.id, Category.name)
            .join(Category, Category.id == Transaction.category_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                LINKED_TO_CARD,
            )
        )
        problems = [
            f"transaction {tid} is filed to card payment envelope '{name}' — "
            "recategorize it; the budget cannot show it"
            for tid, name in result
        ]
        return self._result(
            "card_envelope_rows",
            "No transactions are filed to a credit card's payment envelope",
            problems,
        )

    async def _check_card_payment_envelope_pairing(self, budget_id: uuid.UUID) -> IntegrityCheck:
        """Every on-budget card has exactly one set-aside envelope, and every
        set-aside envelope has its card.

        Both halves are silent when broken, in opposite ways.

        A card with no envelope: `get_budget_summary` computes its set-aside
        for the card row but only folds it into the envelope term when a linked
        category exists, so Ready to Assign loses the reserve with nothing on
        screen to say so. Every path that makes a card calls
        `ensure_payment_category` — this is the check that says so out loud.

        An envelope with no card: left behind when a card account is deleted.
        It sits in a hidden group holding whatever was assigned to it, invisible
        to the grid, still counted in the envelope term.
        """
        cards = (
            await self.session.execute(
                select(Account.id, Account.name).where(
                    Account.budget_id == budget_id,
                    Account.is_deleted == False,  # noqa: E712
                    Account.on_budget == True,  # noqa: E712
                    Account.classification == "liability",
                )
            )
        ).all()
        envelopes = (
            await self.session.execute(
                select(Category.id, Category.name, Category.linked_account_id)
                .join(CategoryGroup, CategoryGroup.id == Category.category_group_id)
                .where(
                    Category.budget_id == budget_id,
                    Category.is_deleted == False,  # noqa: E712
                    or_(LINKED_TO_CARD, CategoryGroup.name == CARD_PAYMENTS_GROUP),
                )
            )
        ).all()

        linked = {e.linked_account_id for e in envelopes if e.linked_account_id is not None}
        problems = [
            f"credit card '{name}' ({cid}) has no set-aside envelope — its reserve "
            "is missing from Ready to Assign; re-save the account to rebuild it"
            for cid, name in cards
            if cid not in linked
        ]
        live_cards = {cid for cid, _ in cards}
        problems += [
            f"card payment envelope '{e.name}' ({e.id}) points at no live card — "
            "money assigned to it is counted but unreachable; delete it or relink it"
            for e in envelopes
            if e.linked_account_id is None or e.linked_account_id not in live_cards
        ]
        return self._result(
            "card_payment_envelope_pairing",
            "Every credit card has its set-aside envelope, and vice versa",
            problems,
        )

    async def _check_card_reserve_identity(self, budget_id: uuid.UUID) -> IntegrityCheck:
        """Every card's reserve makes sense against what it owes.

            set_aside + uncovered == -balance + over_reserved
                                     - short_reserved + card_credit

        An identity given the definitions, so the content is its three bounds
        (domain/cards.py `reserve_discrepancy`): a reserve exceeds the debt only
        by an assignment or an outside credit; it goes negative only by an
        overpayment or an inflow beyond what the category ever had riding there;
        and a credit balance on the card is either budget money or somebody
        else's.

        This check exists because the invariant was stated years before it was
        enforced, and stated with an exclusion clause — "for a card with no
        assignments and no inflows that predate their reservations" — that
        excused precisely the histories that broke it. Every defect the credit
        model has shipped was visible in this one equation, and nothing asked.
        The bounds are what removed the clause.
        """
        summary = await self._budget_service.get_budget_summary(budget_id, today_utc())
        problems = [
            f"card '{card.name}' reserve does not add up: set aside {card.set_aside}, "
            f"balance {card.balance}, unexplained by {card.reserve_discrepancy} — "
            "an inflow, assignment or payment is landing somewhere the reserve "
            "arithmetic cannot see"
            for card in summary.cards
            if card.reserve_discrepancy != Decimal("0")
        ]
        return self._result(
            "card_reserve_identity",
            "Every credit card's set-aside agrees with what it owes",
            problems,
        )

    @staticmethod
    def _result(name: str, description: str, problems: list[str]) -> IntegrityCheck:
        return IntegrityCheck(
            name=name,
            description=description,
            passed=not problems,
            problem_count=len(problems),
            details=problems[:MAX_DETAILS],
        )
