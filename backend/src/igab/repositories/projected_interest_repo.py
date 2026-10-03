"""The ledger facts a loan's projected interest rows are planned from.

Reads only. The plan is `domain.projected_interest.plan_projection`; the
writes are `services/projected_interest.py`'s. Every predicate is a
`txn_filters` one — the payment, the lender's own interest row, the live
projection — so "what counts as a payment here" cannot drift from what the
liability page counts.
"""

import uuid
from datetime import date

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Liability, Transaction
from igab.domain.dates import add_months, month_start
from igab.domain.enums import AccountClassification
from igab.domain.projected_interest import MonthFacts, StandingProjection
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import (
    LENDER_INTEREST_ROW,
    LOAN_PAYMENT_ROW,
    PROJECTED_INTEREST_ROW,
)


class ProjectedInterestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.transactions = TransactionRepository(session)

    async def terms_on_file(self, account_id: uuid.UUID) -> Liability | None:
        """The liability whose terms project this account's interest, or None.

        "Terms on file" is: a live, OFF-budget, liability-classified account
        with a live companion Liability carrying a rate. On-budget cards are
        out — a card's interest is a purchase-shaped charge the issuer posts
        on its statement, and the card model (domain/cards.py) budgets it as
        spending, not as a loan's monthly accrual. A liability with no rate
        projects nothing: there is nothing to project from, and an imported
        loan stays exactly as the import left it until someone fills the
        terms in.
        """
        account = await self.session.get(Account, account_id)
        if (
            account is None
            or account.is_deleted
            or account.on_budget
            or account.classification != AccountClassification.LIABILITY
        ):
            return None
        liability = (
            await self.session.execute(
                select(Liability).where(
                    Liability.linked_account_id == account_id,
                    Liability.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if liability is None or liability.interest_rate is None:
            return None
        return liability

    async def month_facts(self, account_id: uuid.UUID, month: date) -> MonthFacts:
        """Everything `plan_projection` needs about one account's month."""
        opens = month_start(month)
        in_month = and_(
            Transaction.account_id == account_id,
            Transaction.date >= opens,
            Transaction.date < add_months(opens, 1),
        )
        first_payment = (
            await self.session.execute(
                select(func.min(Transaction.date)).where(in_month, LOAN_PAYMENT_ROW)
            )
        ).scalar_one()
        lender_interest = (
            await self.session.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    in_month, LENDER_INTEREST_ROW
                )
            )
        ).scalar_one()
        standing = await self.live_projection(account_id, opens)
        declined = (
            await self.session.execute(
                select(
                    exists().where(
                        Transaction.account_id == account_id,
                        Transaction.projected_interest_month == opens,
                        Transaction.is_deleted == True,  # noqa: E712
                    )
                )
            )
        ).scalar_one()
        return MonthFacts(
            month=opens,
            owed_at_open=await self.transactions.owed_at_month_open(account_id, opens),
            first_payment=first_payment,
            lender_interest=lender_interest,
            standing=(
                StandingProjection(id=standing.id, date=standing.date, amount=standing.amount)
                if standing is not None
                else None
            ),
            declined=bool(declined),
        )

    async def live_projection(self, account_id: uuid.UUID, month: date) -> Transaction | None:
        """The live projection standing for `month`, if any (the partial
        unique index allows one)."""
        return (
            await self.session.execute(
                select(Transaction).where(
                    Transaction.account_id == account_id,
                    PROJECTED_INTEREST_ROW,
                    Transaction.projected_interest_month == month_start(month),
                )
            )
        ).scalar_one_or_none()

    async def live_projections(
        self, account_id: uuid.UUID, from_month: date | None = None
    ) -> list[Transaction]:
        """Every live projection on the account, oldest month first —
        optionally only from `from_month` on."""
        stmt = select(Transaction).where(
            Transaction.account_id == account_id, PROJECTED_INTEREST_ROW
        )
        if from_month is not None:
            stmt = stmt.where(Transaction.projected_interest_month >= month_start(from_month))
        stmt = stmt.order_by(Transaction.projected_interest_month)
        return list((await self.session.execute(stmt)).scalars().all())
