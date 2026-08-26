"""Working out, from the budget, what the roadmap wants to know.

Every function here answers one concept and says how it got there. The
"how" is not decoration: the Guide shows a reason beside every derived figure,
and a claim the app cannot explain is a claim it should not make.

Detection is deliberately conservative. Where a heuristic cannot be confident
it reports what it found and leaves the concept unmet rather than guessing —
a roadmap that tells someone they have no emergency fund when they do is worse
than one that admits it cannot tell.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, AccountType, Category, Liability, Transaction
from igab.domain.activity_class import ACTIVITY_CLASS, ActivityClass, apply_class_joins
from igab.domain.carryover import available_through
from igab.domain.dates import month_end, month_start
from igab.domain.money import quantize_cents
from igab.guide.concepts import (
    ESSENTIALS_WINDOW_DAYS,
    HIGH_INTEREST_APR,
    MODERATE_INTEREST_APR,
    MORTGAGE_KINDS,
)
from igab.repositories.tag_repo import TagRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import (
    BALANCE_ROW,
    COUNTERPART_ACCOUNT_ID,
    LEAF,
    NOT_DELETED,
    POSTED,
)

TWO_PLACES = Decimal("0.01")


def _cents(value: Decimal) -> Decimal:
    """Round to cents.

    Was half-up, with a docstring claiming that was "the convention the money
    code uses". It was not — every other sum in the app rounds half-even, so
    the guide could report a figure one cent off the page it says it mirrors.
    """
    return quantize_cents(value)


#: Names that suggest an emergency fund. Deliberately narrow — a false match
#: here tells someone they are covered when they are not.
EMERGENCY_NAME = re.compile(r"emergency|rainy.?day|buffer", re.I)


@dataclass
class Finding:
    """One concept's answer, with its reasoning and its workings."""

    concept_key: str
    #: True/False when known; None when detection could not tell.
    met: bool | None = None
    #: The figure behind the answer, in the concept's own units.
    value: Decimal | None = None
    #: What the answer is measured against, where there is a target.
    target: Decimal | None = None
    #: One clause, shown to the user: "the category is tagged Savings and its
    #: name mentions an emergency".
    reason: str = ""
    #: Entities the figure came from, so the UI can show its workings and the
    #: override sheet can pre-select them.
    entities: dict[str, list[uuid.UUID]] = field(default_factory=dict)
    #: Rows worth mentioning even though they did not count — a card with no
    #: rate recorded, say. A gap in the data is a nudge, not a silence.
    gaps: list[str] = field(default_factory=list)


class GuideDetection:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tags = TagRepository(session)
        self.txns = TransactionRepository(session)

    # ── money the household has set aside ────────────────────────────────────

    async def emergency_fund(
        self, budget_id: uuid.UUID, bound: dict[str, tuple[uuid.UUID, ...]] | None = None
    ) -> Finding:
        """How much is reachable today if something goes wrong.

        Looks for a savings-tagged category whose name mentions an emergency
        first, because that is the arrangement the app can be most confident
        about. Falls back to savings accounts, which is a weaker signal — a
        savings account may be holding a house deposit.
        """
        if bound:
            total = await self._balance_of(budget_id, bound)
            return Finding(
                concept_key="emergency_fund",
                met=total > 0,
                value=total,
                reason="you told us what counts as your emergency fund",
                entities={k: list(v) for k, v in bound.items()},
            )

        savings_tagged = await self.tags.get_category_ids_by_system_keys(budget_id, ["savings"])
        rows = (
            await self.session.execute(
                select(Category.id, Category.name).where(
                    Category.budget_id == budget_id,
                    Category.is_deleted == False,  # noqa: E712
                )
            )
        ).all()
        named = [r for r in rows if EMERGENCY_NAME.search(r.name or "")]

        matched = [r.id for r in named if r.id in savings_tagged]
        if matched:
            total = await self._category_balance(budget_id, matched)
            return Finding(
                concept_key="emergency_fund",
                met=total > 0,
                value=total,
                reason="the category is tagged Savings and its name mentions an emergency",
                entities={"category": matched},
            )

        if named:
            ids = [r.id for r in named]
            total = await self._category_balance(budget_id, ids)
            return Finding(
                concept_key="emergency_fund",
                met=total > 0,
                value=total,
                reason="the category name mentions an emergency",
                entities={"category": ids},
            )

        accounts = (
            (
                await self.session.execute(
                    select(Account.id).where(
                        Account.budget_id == budget_id,
                        Account.is_deleted == False,  # noqa: E712
                        Account.account_type == "savings",
                    )
                )
            )
            .scalars()
            .all()
        )
        if accounts:
            total = await self._account_balance(list(accounts))
            return Finding(
                concept_key="emergency_fund",
                met=total > 0,
                value=total,
                reason="this is your savings account, which may also be holding other plans",
                entities={"account": list(accounts)},
            )

        return Finding(
            concept_key="emergency_fund",
            met=None,
            reason="we could not find anything that looks like an emergency fund",
        )

    async def essential_expenses(
        self, budget_id: uuid.UUID, bound: dict[str, tuple[uuid.UUID, ...]] | None = None
    ) -> Finding:
        """Roughly what a month costs — what an emergency fund is measured against.

        One query (TransactionRepository.essential_spend) answers this, the
        Overview's essentials card and the Essentials report, so the roadmap's
        target and the reports quote one figure. Precedence: categories the
        user bound here, else what they tagged Essential, else all spending.
        """
        today = date.today()
        since = today - timedelta(days=ESSENTIALS_WINDOW_DAYS)
        total, basis = await self.txns.essential_spend(
            budget_id, since, today, bound.get("category") if bound else None
        )
        reason = {
            "bound": "the categories you told us are essential",
            "tag": "the categories and payees you tagged Essential",
            "all": "your average spending over the last 90 days",
        }[basis]
        monthly = _cents(abs(total) / 3)
        return Finding(
            concept_key="essential_expenses",
            met=monthly > 0,
            value=monthly,
            reason=reason,
            entities={k: list(v) for k, v in (bound or {}).items()},
        )

    # ── what the household owes ──────────────────────────────────────────────

    async def high_interest_debt(self, budget_id: uuid.UUID) -> Finding:
        return await self._debt_band(
            budget_id,
            key="high_interest_debt",
            low=Decimal(HIGH_INTEREST_APR),
            high=None,
            exclude_mortgages=False,
            reason=f"these debts are at {HIGH_INTEREST_APR}% APR or higher",
        )

    async def moderate_interest_debt(self, budget_id: uuid.UUID) -> Finding:
        return await self._debt_band(
            budget_id,
            key="moderate_interest_debt",
            low=Decimal(MODERATE_INTEREST_APR),
            high=Decimal(HIGH_INTEREST_APR),
            exclude_mortgages=True,
            reason=(
                f"these debts are between {MODERATE_INTEREST_APR}% and "
                f"{HIGH_INTEREST_APR}% APR, not counting a mortgage"
            ),
        )

    async def _debt_band(
        self,
        budget_id: uuid.UUID,
        *,
        key: str,
        low: Decimal,
        high: Decimal | None,
        exclude_mortgages: bool,
        reason: str,
    ) -> Finding:
        """Debts whose rate falls in a band.

        Terms are optional since liabilities gained companion accounts, so a
        rate can legitimately be unknown. An unknown rate is reported as a gap
        rather than assumed cheap — assuming would quietly drop a 26% store
        card out of the roadmap's most important step.
        """
        liabilities = (
            (await self.session.execute(select(Liability).where(Liability.budget_id == budget_id)))
            .scalars()
            .all()
        )

        counted: list[uuid.UUID] = []
        total = Decimal("0")
        gaps: list[str] = []

        for lia in liabilities:
            kind = await self._debt_kind(lia)
            if lia.interest_rate is None:
                gaps.append(lia.name)
                continue
            if exclude_mortgages and kind in MORTGAGE_KINDS:
                continue
            rate = Decimal(lia.interest_rate)
            if rate < low or (high is not None and rate >= high):
                continue
            balance = await self._liability_balance(lia)
            if balance <= 0:
                continue
            counted.append(lia.id)
            total += balance

        return Finding(
            concept_key=key,
            met=bool(counted),
            value=_cents(total) if counted else Decimal("0"),
            reason=reason if counted else "no debts in this range",
            entities={"liability": counted},
            gaps=gaps,
        )

    async def _debt_kind(self, liability: Liability) -> str:
        """Mirror of LiabilityService.resolve_type.

        A managed liability's kind is its account's type — the account is the
        thing the user actually chose a type for. Duplicated rather than
        imported to keep detection free of the service graph; if the rule ever
        changes, both must move.
        """
        if liability.linked_account_id is None:
            return liability.liability_type or "other"
        account = await self.session.get(Account, liability.linked_account_id)
        if account is None:
            return liability.liability_type or "other"
        return account.account_type

    async def _liability_balance(self, liability: Liability) -> Decimal:
        if liability.linked_account_id is None:
            return abs(Decimal(liability.manual_balance or 0))
        total = (
            await self.session.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.account_id == liability.linked_account_id,
                    NOT_DELETED,
                    LEAF,
                )
            )
        ).scalar_one()
        return abs(Decimal(total))

    # ── retirement ───────────────────────────────────────────────────────────

    async def retirement_contributions(
        self, budget_id: uuid.UUID, bound: dict[str, tuple[uuid.UUID, ...]] | None = None
    ) -> Finding:
        """Share of income going towards retirement, over the last 12 months.

        Without a binding this cannot be answered honestly: IGAB knows which
        accounts are investments, but not which of those are for retirement,
        and a workplace plan it never sees will not appear at all. So it
        reports what it can see and says plainly that it is a lower bound.
        """
        since = date.today() - timedelta(days=365)
        accounts = list((bound or {}).get("account", ()))
        reason = "money you moved into the accounts you marked as retirement"

        if not accounts:
            rows = (
                (
                    await self.session.execute(
                        select(Account.id)
                        .join(AccountType, Account.account_type_id == AccountType.id)
                        .where(
                            Account.budget_id == budget_id,
                            Account.is_deleted == False,  # noqa: E712
                            Account.account_type == "investment",
                        )
                    )
                )
                .scalars()
                .all()
            )
            accounts = list(rows)
            reason = "money moved into your investment accounts — tell us which are for retirement"

        if not accounts:
            return Finding(
                concept_key="retirement_contributions",
                met=None,
                reason="we cannot see any retirement accounts",
            )

        contributed = (
            await self.session.execute(
                apply_class_joins(
                    select(func.coalesce(func.sum(Transaction.amount), 0))
                    .select_from(Transaction)
                    .where(
                        Transaction.budget_id == budget_id,
                        NOT_DELETED,
                        POSTED,
                        LEAF,
                        Transaction.date >= since,
                        or_(
                            COUNTERPART_ACCOUNT_ID.in_(accounts),
                            Transaction.account_id.in_(accounts),
                        ),
                        ACTIVITY_CLASS == ActivityClass.SAVINGS,
                    )
                )
            )
        ).scalar_one()

        income = (
            await self.session.execute(
                apply_class_joins(
                    select(func.coalesce(func.sum(Transaction.amount), 0))
                    .select_from(Transaction)
                    .where(
                        Transaction.budget_id == budget_id,
                        NOT_DELETED,
                        POSTED,
                        LEAF,
                        Transaction.date >= since,
                        ACTIVITY_CLASS == ActivityClass.INCOME,
                    )
                )
            )
        ).scalar_one()

        if not income or Decimal(income) <= 0:
            return Finding(
                concept_key="retirement_contributions",
                met=None,
                reason="no income recorded in the last year, so a rate would be meaningless",
                entities={"account": accounts},
            )

        rate = (abs(Decimal(contributed)) / Decimal(income)) * 100
        return Finding(
            concept_key="retirement_contributions",
            met=None,  # judged against the target by the caller
            value=_cents(rate),
            reason=reason,
            entities={"account": accounts},
        )

    # ── shared helpers ───────────────────────────────────────────────────────

    async def _balance_of(
        self, budget_id: uuid.UUID, bound: dict[str, tuple[uuid.UUID, ...]]
    ) -> Decimal:
        total = Decimal("0")
        if bound.get("category"):
            total += await self._category_balance(budget_id, list(bound["category"]))
        if bound.get("account"):
            total += await self._account_balance(list(bound["account"]))
        return _cents(total)

    async def _category_balance(
        self, budget_id: uuid.UUID, category_ids: list[uuid.UUID]
    ) -> Decimal:
        """What has accumulated in these categories, as the budget page reads it.

        This used to be `SUM(assigned) + SUM(activity)` over all time, which is
        not the budget page's number and is not what a user would recognise: it
        carried overspending forward that the budget had already covered from
        To Be Assigned, and it counted assignments for months that have not
        arrived. Any category that ever overspent read permanently low — and
        this figure decides whether the roadmap tells someone they have no
        emergency fund.

        The simulation runs per category and the totals are summed after,
        because the zero floor is per category: two categories, one $50 over
        and one $50 under, carry $0 and $50 — not $0 between them.
        """
        if not category_ids:
            return Decimal("0")
        from igab.db.models import BudgetAssignment

        month = month_start(date.today())
        total = Decimal("0")
        for category_id in category_ids:
            assignments = (
                await self.session.execute(
                    select(BudgetAssignment.month, BudgetAssignment.assigned).where(
                        BudgetAssignment.category_id == category_id,
                        BudgetAssignment.month <= month,
                    )
                )
            ).all()
            activity = (
                await self.session.execute(
                    select(
                        func.date_trunc("month", Transaction.date).label("m"),
                        func.coalesce(func.sum(Transaction.amount), 0),
                    )
                    .where(
                        Transaction.budget_id == budget_id,
                        Transaction.category_id == category_id,
                        NOT_DELETED,
                        POSTED,
                        LEAF,
                        Transaction.date <= month_end(month),
                    )
                    .group_by("m")
                )
            ).all()
            total += available_through(
                {m: Decimal(a) for m, a in assignments},
                {r[0].date(): Decimal(r[1]) for r in activity},
                month,
            )
        return _cents(total)

    async def _account_balance(self, account_ids: list[uuid.UUID]) -> Decimal:
        """The same rows AccountRepository.get_balance sums.

        Was NOT_DELETED + LEAF, which counted pending auth holds as real money
        — nothing else in the app does, so the guide's account figure drifted
        from the sidebar's by whatever was on hold.

        LEAF and PARENT_ROW both total a split correctly (LEAF takes the
        children and skips the parent; PARENT_ROW does the reverse), so that
        half was never wrong. Using BALANCE_ROW is still what stops the two
        answers from being arrived at separately.
        """
        if not account_ids:
            return Decimal("0")
        total = (
            await self.session.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.account_id.in_(account_ids),
                    BALANCE_ROW,
                )
            )
        ).scalar_one()
        return _cents(Decimal(total))
