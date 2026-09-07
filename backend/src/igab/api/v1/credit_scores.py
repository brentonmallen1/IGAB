"""Credit scores the person typed in, by date and bureau.

Manual on purpose: there is no API a household should wire a credit bureau
into, and a number you looked up yourself is the honest one. The Guide's
credit-score tool draws them as a line and links to where to look one up.
Every write records (change_log.py); a score is a hard row, so undo of a
delete re-inserts it and refuses if the same day and bureau were re-entered
since.
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.api.route import CommitRoute
from igab.api.v1.schemas.base import ApiModel
from igab.db.models import CreditScore
from igab.dependencies import BudgetAccess, CurrentUser, get_change_recorder, get_session
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match

router = APIRouter(route_class=CommitRoute)

Recorder = Annotated[ChangeRecorder, Depends(get_change_recorder)]


class CreditScoreIn(ApiModel):
    recorded_on: date
    score: int = Field(ge=300, le=900)
    bureau: str | None = Field(default=None, max_length=40)
    source: str | None = Field(default=None, max_length=100)
    note: str | None = None


class CreditScoreUpdate(ApiModel):
    recorded_on: date | None = None
    score: int | None = Field(default=None, ge=300, le=900)
    bureau: str | None = None
    source: str | None = None
    note: str | None = None


class CreditScoreOut(ApiModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    recorded_on: date
    score: int
    bureau: str | None
    source: str | None
    note: str | None

    model_config = {"from_attributes": True}


async def _get(session: AsyncSession, budget_id: uuid.UUID, score_id: uuid.UUID) -> CreditScore:
    row = await session.get(CreditScore, score_id)
    if row is None or row.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Score not found")
    return row


@router.get("/{budget_id}/credit-scores", response_model=list[CreditScoreOut])
async def list_credit_scores(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CreditScoreOut]:
    rows = await session.execute(
        select(CreditScore)
        .where(CreditScore.budget_id == budget_id)
        .order_by(CreditScore.recorded_on, CreditScore.bureau)
    )
    return [CreditScoreOut.model_validate(r) for r in rows.scalars().all()]


@router.post(
    "/{budget_id}/credit-scores",
    response_model=CreditScoreOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_credit_score(
    budget_id: BudgetAccess,
    body: CreditScoreIn,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    recorder: Recorder,
) -> CreditScoreOut:
    clash = await session.execute(
        select(CreditScore.id).where(
            CreditScore.budget_id == budget_id,
            CreditScore.recorded_on == body.recorded_on,
            CreditScore.bureau.is_(None)
            if body.bureau is None
            else CreditScore.bureau == body.bureau,
        )
    )
    if clash.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A score for that day and bureau is already recorded — edit it instead",
        )
    row = CreditScore(budget_id=budget_id, **body.model_dump())
    session.add(row)
    await session.flush()
    await recorder.record(
        budget_id=budget_id,
        entity_type="credit_score",
        entity_id=row.id,
        action="create",
        after=snapshot("credit_score", row),
    )
    return CreditScoreOut.model_validate(row)


@router.patch("/{budget_id}/credit-scores/{score_id}", response_model=CreditScoreOut)
async def update_credit_score(
    budget_id: BudgetAccess,
    score_id: uuid.UUID,
    body: CreditScoreUpdate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    recorder: Recorder,
) -> CreditScoreOut:
    row = await _get(session, budget_id, score_id)
    before = snapshot("credit_score", row)
    nullable = {"bureau", "source", "note"}
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None or key in nullable:
            setattr(row, key, value)
    await session.flush()
    after = snapshot("credit_score", row)
    if snapshots_match(after, before):
        await recorder.record(
            budget_id=budget_id,
            entity_type="credit_score",
            entity_id=row.id,
            action="update",
            before=before,
            after=after,
        )
    return CreditScoreOut.model_validate(row)


@router.delete("/{budget_id}/credit-scores/{score_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credit_score(
    budget_id: BudgetAccess,
    score_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    recorder: Recorder,
) -> None:
    row = await _get(session, budget_id, score_id)
    await recorder.record(
        budget_id=budget_id,
        entity_type="credit_score",
        entity_id=row.id,
        action="delete",
        before=snapshot("credit_score", row),
    )
    await session.delete(row)
    await session.flush()
