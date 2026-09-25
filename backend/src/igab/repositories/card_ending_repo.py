import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from igab.db.models import AccountCardEnding
from igab.repositories.base import BaseRepository


def card_ending_owner(
    budget_id: uuid.UUID | ColumnElement | InstrumentedAttribute,
    last4: str | ColumnElement,
) -> Select:
    """The account that owns a card ending in a budget — the one answer to
    "whose card is this?".

    A select rather than a value, so the AI job loader embeds it as a
    correlated subquery (`CARD_ENDING_ACCOUNT_EXPR`) and the worker executes
    it directly: one predicate, whichever side is asking. At most one row —
    `uq_card_ending_budget_last4` makes the ending unique per budget.
    """
    return select(AccountCardEnding.account_id).where(
        AccountCardEnding.budget_id == budget_id, AccountCardEnding.last4 == last4
    )


class CardEndingRepository(BaseRepository[AccountCardEnding]):
    model = AccountCardEnding

    async def list_for_budget(self, budget_id: uuid.UUID) -> list[AccountCardEnding]:
        result = await self.session.execute(
            select(AccountCardEnding)
            .where(AccountCardEnding.budget_id == budget_id)
            .order_by(AccountCardEnding.last4)
        )
        return list(result.scalars().all())

    async def owner(self, budget_id: uuid.UUID, last4: str) -> uuid.UUID | None:
        return await self.session.scalar(card_ending_owner(budget_id, last4))

    async def find(self, budget_id: uuid.UUID, last4: str) -> AccountCardEnding | None:
        result = await self.session.execute(
            select(AccountCardEnding).where(
                AccountCardEnding.budget_id == budget_id, AccountCardEnding.last4 == last4
            )
        )
        return result.scalar_one_or_none()
