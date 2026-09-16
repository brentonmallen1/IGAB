"""The emergency fund picker: what the fund counts, chosen in one place.

Thin: `services/emergency_fund_choice.py` orchestrates the save, and
`services/emergency_fund.py` is what the fund is. Opened from Settings → Tags,
the tag notices, the Guide and every report that quotes the fund.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.emergency_fund import (
    EmergencyFundChoiceRequest,
    EmergencyFundPickerOut,
    FundAccountCandidateOut,
)
from igab.api.v1.schemas.report import EmergencyFundOut
from igab.dependencies import BudgetAccess, CurrentUser, SessionDep, get_change_recorder
from igab.domain.exceptions import InvariantViolation
from igab.services.change_log import ChangeRecorder
from igab.services.emergency_fund_choice import (
    ExternalChoice,
    FundChoice,
    picker,
    save_choice,
)

router = APIRouter(route_class=CommitRoute)

Recorder = Annotated[ChangeRecorder, Depends(get_change_recorder)]


async def _picker_out(session, budget_id) -> EmergencyFundPickerOut:
    fund, candidates = await picker(session, budget_id)
    return EmergencyFundPickerOut(
        fund=EmergencyFundOut.model_validate(fund),
        account_candidates=[FundAccountCandidateOut.model_validate(c) for c in candidates],
    )


@router.get("/{budget_id}/emergency-fund", response_model=EmergencyFundPickerOut)
async def get_emergency_fund(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: SessionDep,
) -> EmergencyFundPickerOut:
    return await _picker_out(session, budget_id)


@router.put("/{budget_id}/emergency-fund", response_model=EmergencyFundPickerOut)
async def set_emergency_fund(
    budget_id: BudgetAccess,
    body: EmergencyFundChoiceRequest,
    current_user: CurrentUser,
    session: SessionDep,
    recorder: Recorder,
) -> EmergencyFundPickerOut:
    external = body.external
    note = (external.note or "").strip() or None
    choice = FundChoice(
        add_categories=frozenset(body.add_categories),
        remove_categories=frozenset(body.remove_categories),
        savings_modes=body.savings_modes,
        account_ids=frozenset(body.account_ids),
        # An undeclared amount carries no figure and no note.
        external=ExternalChoice(
            declared=external.declared,
            amount=external.amount if external.declared else None,
            note=note if external.declared else None,
        ),
    )
    try:
        await save_choice(session, recorder, budget_id, choice)
    except InvariantViolation as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from e
    return await _picker_out(session, budget_id)
