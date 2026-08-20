"""Budget membership: who can use a shared budget.

Owner-gated management (add/remove members), with two humane exceptions —
a member may always remove THEMSELF (leave), and the last owner can never be
removed (a budget must not become unreachable). Non-members get 404 from
BudgetAccess like everywhere else; members hitting owner-only operations get
403 (they already know the budget exists).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import BudgetMember, User
from igab.db.session import get_session
from igab.dependencies import BudgetAccess, BudgetOwnerAccess, CurrentUser

router = APIRouter()


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None
    role: str


class MemberAddRequest(BaseModel):
    user_id: uuid.UUID


@router.get("/{budget_id}/members", response_model=list[MemberResponse])
async def list_members(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MemberResponse]:
    result = await session.execute(
        select(BudgetMember, User)
        .join(User, BudgetMember.user_id == User.id)
        .where(BudgetMember.budget_id == budget_id)
        .order_by(BudgetMember.created_at)
    )
    return [
        MemberResponse(user_id=m.user_id, email=u.email, display_name=u.display_name, role=m.role)
        for m, u in result.all()
    ]


@router.post(
    "/{budget_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED
)
async def add_member(
    budget_id: BudgetOwnerAccess,
    body: MemberAddRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberResponse:
    user = await session.get(User, body.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    existing = await session.get(BudgetMember, (budget_id, body.user_id))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already a member of this budget"
        )
    member = BudgetMember(budget_id=budget_id, user_id=body.user_id, role="member")
    session.add(member)
    await session.flush()
    return MemberResponse(
        user_id=user.id, email=user.email, display_name=user.display_name, role=member.role
    )


@router.delete("/{budget_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    budget_id: BudgetAccess,
    user_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Owners remove anyone; a member may remove only themself (leave)."""
    me = await session.get(BudgetMember, (budget_id, current_user.id))
    # BudgetAccess guarantees me is not None, but be defensive.
    if me is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    if me.role != "owner" and user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the budget owner can remove other members",
        )

    target = await session.get(BudgetMember, (budget_id, user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target.role == "owner":
        owners = await session.execute(
            select(BudgetMember.user_id).where(
                BudgetMember.budget_id == budget_id, BudgetMember.role == "owner"
            )
        )
        if len(owners.scalars().all()) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A budget must keep at least one owner",
            )

    await session.delete(target)
    await session.flush()
