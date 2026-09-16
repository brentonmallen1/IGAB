"""Working out, from the budget, what the roadmap wants to know.

Every function here answers one concept and says how it got there. The
"how" is not decoration: the Guide shows a reason beside every derived figure,
and a claim the app cannot explain is a claim it should not make.

Detection is deliberately conservative. Where a heuristic cannot be confident
it reports what it found and leaves the concept unmet rather than guessing —
a roadmap that tells someone they have no emergency fund when they do is worse
than one that admits it cannot tell.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, AccountType, Liability, Transaction
from igab.domain.activity_class import ACTIVITY_CLASS, ActivityClass, apply_class_joins
from igab.domain.money import quantize_cents
from igab.guide.concepts import (
    HIGH_INTEREST_APR,
    MODERATE_INTEREST_APR,
    MORTGAGE_KINDS,
    EssentialsMonthly,
)
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.import_anchor_repo import ImportAnchorRepository
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.snapshot_repo import SnapshotRepository
from igab.repositories.tag_repo import TagRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import (
    COUNTERPART_ACCOUNT_ID,
    LEAF,
    NOT_DELETED,
    POSTED,
)
from igab.services.budget_service import BudgetService
from igab.services.category_service import CategoryService
from igab.services.emergency_fund import EmergencyFund, emergency_fund
from igab.services.essentials import essentials_figures
from igab.services.liability_service import LiabilityService

TWO_PLACES = Decimal("0.01")


def _cents(value: Decimal) -> Decimal:
    """Round to cents.

    Was half-up, with a docstring claiming that was "the convention the money
    code uses". It was not — every other sum in the app rounds half-even, so
    the guide could report a figure one cent off the page it says it mirrors.
    """
    return quantize_cents(value)


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
    #: The essential-expenses concept only: both essentials figures
    #: (`services.essentials.essentials_figures`); `value` is their `.monthly`.
    essentials: EssentialsMonthly | None = None
    #: The emergency-fund concept only: the whole composition
    #: (`services.emergency_fund`), whose `total` the signal quotes.
    fund: EmergencyFund | None = None


def budget_service_from(session: AsyncSession) -> BudgetService:
    """The budget page's own service, built the way the DI layer builds it.

    Detection reads envelope balances through it rather than re-deriving them,
    so the Guide's figure for a category is the budget page's figure by
    construction — not by a comment asking two queries to stay in step.
    """
    return BudgetService(
        AccountRepository(session),
        CategoryRepository(session),
        CategoryGroupRepository(session),
        BudgetAssignmentRepository(session),
        TransactionRepository(session),
        snapshot_repo=SnapshotRepository(session),
        anchor_repo=ImportAnchorRepository(session),
    )


def category_service_from(session: AsyncSession, budget_service: BudgetService) -> CategoryService:
    """The budget page's category service, built the way the DI layer builds it.

    The Guide needs it to retire the Wishlist group — archiving a group is a
    money operation, and doing it with a column write is what let the switch
    strand a wish envelope's balance.
    """
    return CategoryService(
        session,
        CategoryRepository(session),
        CategoryGroupRepository(session),
        budget_service,
        TransactionRepository(session),
        BudgetAssignmentRepository(session),
    )


def liability_service_from(session: AsyncSession) -> LiabilityService:
    """The liabilities page's service — the one home of "what is owed"."""
    return LiabilityService(
        LiabilityRepository(session),
        AccountRepository(session),
        CategoryRepository(session),
        TransactionRepository(session),
    )


class GuideDetection:
    def __init__(
        self,
        session: AsyncSession,
        budget_service: BudgetService | None = None,
        liability_service: LiabilityService | None = None,
    ) -> None:
        self.session = session
        self.tags = TagRepository(session)
        self.txns = TransactionRepository(session)
        # Optional so a test can say `GuideDetection(session)`; the request
        # path passes the instances the rest of the request already built.
        self.budget = budget_service or budget_service_from(session)
        self.liabilities = liability_service or liability_service_from(session)

    # ── money the household has set aside ────────────────────────────────────

    async def emergency_fund(self, budget_id: uuid.UUID) -> Finding:
        """How much is set aside for a genuine surprise — what the household
        chose to count, never a guess (`services.emergency_fund`).

        `value` is what IGAB can see: the tagged envelopes and marked accounts,
        without any amount declared as kept elsewhere, which the signal folds
        on top. `fund` is the whole composition, so the signal quotes the one
        total every report quotes.

        It used to guess — a category named for an emergency, else every
        savings-type account — and a house deposit could be reported as a
        household's emergency fund with nothing on screen saying so.
        """
        fund = await emergency_fund(self.session, budget_id, self.budget)
        if not fund.set_up:
            return Finding(
                concept_key="emergency_fund",
                met=None,
                reason="nothing has been chosen to count as your emergency fund yet",
                fund=fund,
            )
        entities: dict[str, list[uuid.UUID]] = {}
        if fund.categories:
            entities["category"] = [p.id for p in fund.categories]
        if fund.accounts:
            entities["account"] = [p.id for p in fund.accounts]
        return Finding(
            concept_key="emergency_fund",
            met=None if fund.total is None else fund.total > 0,
            value=fund.in_budget,
            reason="what you chose to count",
            entities=entities,
            fund=fund,
        )

    async def essential_expenses(
        self, budget_id: uuid.UUID, bound: dict[str, tuple[uuid.UUID, ...]] | None = None
    ) -> Finding:
        """Roughly what a month costs — what an emergency fund is measured against.

        One entry point (`services.essentials.essentials_figures`) answers
        this, the Overview's essentials card and the Essentials report, so the
        roadmap's target and the reports quote one figure — spread or as paid,
        as the budget's setting says. Precedence: categories the user bound
        here, else what they tagged Essential, else all spending.
        """
        figures, basis = await essentials_figures(
            self.session, budget_id, date.today(), bound.get("category") if bound else None
        )
        reason = {
            "bound": "the categories you told us are essential",
            "tag": "the categories you tagged Essential",
            "all": "your average spending over the last 90 days",
        }[basis]
        return Finding(
            concept_key="essential_expenses",
            met=figures.monthly > 0,
            value=figures.monthly,
            reason=reason,
            entities={k: list(v) for k, v in (bound or {}).items()},
            essentials=figures,
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
            if lia.interest_rate is None:
                gaps.append(lia.name)
                continue
            if exclude_mortgages and await self.liabilities.resolve_type(lia) in MORTGAGE_KINDS:
                continue
            rate = Decimal(lia.interest_rate)
            if rate < low or (high is not None and rate >= high):
                continue
            # The liabilities page's number, not a second reading of the
            # ledger: a copy here once counted pending holds and read an
            # overpaid loan as debt.
            balance = await self.liabilities.get_balance(lia)
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
                            # An investment account someone said is not
                            # savings is not a retirement contribution either.
                            Account.counts_as_savings == True,  # noqa: E712
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
