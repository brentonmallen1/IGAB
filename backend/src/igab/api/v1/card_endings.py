"""The card endings on file for a budget's accounts — full CRUD.

An ending is the last four digits of a card that pays from an account. A
receipt scan reads the ending off the receipt; the review then says which
account's card paid, or offers to remember an ending it has not seen. Every
write records (change_log.py); an ending is a hard row, so undo of a delete
re-inserts it and refuses if the same ending was put on file again since.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from igab.api.route import CommitRoute
from igab.api.v1.schemas.base import ApiModel
from igab.db.models import Account, AccountCardEnding
from igab.dependencies import BudgetAccess, CurrentUser, get_change_recorder, get_session
from igab.repositories.card_ending_repo import CardEndingRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match

router = APIRouter(route_class=CommitRoute)

Recorder = Annotated[ChangeRecorder, Depends(get_change_recorder)]
Session = Annotated[AsyncSession, Depends(get_session)]

#: Exactly four digits as typed. Reading an ending out of receipt text is
#: `domain.card_endings.card_last4`'s job; a person entering one types four.
LAST4 = Field(pattern=r"^\d{4}$")


class CardEndingIn(ApiModel):
    account_id: uuid.UUID
    last4: str = LAST4
    label: str | None = Field(default=None, max_length=60)


class CardEndingUpdate(ApiModel):
    account_id: uuid.UUID | None = None
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    label: str | None = Field(default=None, max_length=60)


class CardEndingOut(ApiModel):
    id: uuid.UUID
    account_id: uuid.UUID
    last4: str
    label: str | None

    model_config = {"from_attributes": True}


async def _account(session: AsyncSession, budget_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    account = await session.get(Account, account_id)
    if account is None or account.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


async def _get(session: AsyncSession, budget_id: uuid.UUID, ending_id: uuid.UUID):
    row = await session.get(AccountCardEnding, ending_id)
    if row is None or row.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card ending not found")
    return row


async def _refuse_taken(
    session: AsyncSession, budget_id: uuid.UUID, last4: str, *, except_id: uuid.UUID | None
) -> None:
    """An ending names one account. A second claim is refused with the name of
    the account that has it, so the person can move it deliberately."""
    taken = await CardEndingRepository(session).find(budget_id, last4)
    if taken is not None and taken.id != except_id:
        owner = await session.get(Account, taken.account_id)
        name = owner.name if owner else "another account"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A card ending in {last4} is already on {name}",
        )


@router.get("/{budget_id}/card-endings", response_model=list[CardEndingOut])
async def list_card_endings(
    budget_id: BudgetAccess, current_user: CurrentUser, session: Session
) -> list[CardEndingOut]:
    rows = await CardEndingRepository(session).list_for_budget(budget_id)
    return [CardEndingOut.model_validate(r) for r in rows]


@router.post(
    "/{budget_id}/card-endings", response_model=CardEndingOut, status_code=status.HTTP_201_CREATED
)
async def create_card_ending(
    budget_id: BudgetAccess,
    body: CardEndingIn,
    current_user: CurrentUser,
    session: Session,
    recorder: Recorder,
) -> CardEndingOut:
    await _account(session, budget_id, body.account_id)
    await _refuse_taken(session, budget_id, body.last4, except_id=None)
    row = AccountCardEnding(
        budget_id=budget_id,
        account_id=body.account_id,
        last4=body.last4,
        label=(body.label or "").strip() or None,
    )
    session.add(row)
    await session.flush()
    await recorder.record(
        budget_id=budget_id,
        entity_type="card_ending",
        entity_id=row.id,
        action="create",
        after=snapshot("card_ending", row),
    )
    return CardEndingOut.model_validate(row)


@router.patch("/{budget_id}/card-endings/{ending_id}", response_model=CardEndingOut)
async def update_card_ending(
    budget_id: BudgetAccess,
    ending_id: uuid.UUID,
    body: CardEndingUpdate,
    current_user: CurrentUser,
    session: Session,
    recorder: Recorder,
) -> CardEndingOut:
    row = await _get(session, budget_id, ending_id)
    before = snapshot("card_ending", row)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("account_id") is not None:
        await _account(session, budget_id, changes["account_id"])
        row.account_id = changes["account_id"]
    if changes.get("last4") is not None:
        await _refuse_taken(session, budget_id, changes["last4"], except_id=row.id)
        row.last4 = changes["last4"]
    if "label" in changes:
        row.label = (changes["label"] or "").strip() or None
    await session.flush()
    after = snapshot("card_ending", row)
    if snapshots_match(after, before):
        await recorder.record(
            budget_id=budget_id,
            entity_type="card_ending",
            entity_id=row.id,
            action="update",
            before=before,
            after=after,
        )
    return CardEndingOut.model_validate(row)


@router.delete("/{budget_id}/card-endings/{ending_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card_ending(
    budget_id: BudgetAccess,
    ending_id: uuid.UUID,
    current_user: CurrentUser,
    session: Session,
    recorder: Recorder,
) -> None:
    row = await _get(session, budget_id, ending_id)
    await recorder.record(
        budget_id=budget_id,
        entity_type="card_ending",
        entity_id=row.id,
        action="delete",
        before=snapshot("card_ending", row),
    )
    await session.delete(row)
    await session.flush()
