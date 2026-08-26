"""Guide endpoints.

Thin by design: parse, authorise, delegate to GuideService, return. Everything
that decides anything lives in igab.guide, which nothing else imports.
"""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.guide import (
    BindingUpdate,
    CandidatesResponse,
    CheckupResponse,
    EmergencyFundRequest,
    EmergencyFundResponse,
    GuideOverview,
    LoanCompareRequest,
    LoanCompareResponse,
    PayoffPlanRequest,
    PayoffPlanResponse,
    PayVsSaveRequest,
    PayVsSaveResponse,
    PreferencesResponse,
    PreferencesUpdate,
    SignalsResponse,
    StepUpdate,
)
from igab.dependencies import BudgetAccess, CurrentUser, get_guide_service
from igab.guide.concepts import CONCEPT_KEYS
from igab.guide.scenarios import LoanCandidate
from igab.guide.service import GuideService
from igab.services.amortization import CascadeDebt
from igab.utils.clock import today_utc

router = APIRouter()

GuideServiceDep = Annotated[GuideService, Depends(get_guide_service)]


def _known(concept_key: str) -> str:
    if concept_key not in CONCEPT_KEYS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown concept '{concept_key}'"
        )
    return concept_key


@router.get("/{budget_id}/guide", response_model=GuideOverview)
async def guide_overview(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> GuideOverview:
    return GuideOverview(
        concepts=GuideService.concepts(),
        thresholds=GuideService.thresholds(),
        preferences=PreferencesResponse(**await service.preferences(budget_id)),
        progress=await service.progress(budget_id),
    )


@router.get("/{budget_id}/guide/signals", response_model=SignalsResponse)
async def guide_signals(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> SignalsResponse:
    return SignalsResponse(**await service.signals(budget_id))


@router.get("/{budget_id}/guide/candidates/{concept_key}", response_model=CandidatesResponse)
async def guide_candidates(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    concept_key: str,
) -> CandidatesResponse:
    key = _known(concept_key)
    return CandidatesResponse(concept_key=key, options=await service.candidates(budget_id, key))


@router.put("/{budget_id}/guide/bindings/{concept_key}", status_code=status.HTTP_204_NO_CONTENT)
async def set_guide_binding(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    concept_key: str,
    payload: BindingUpdate,
) -> None:
    key = _known(concept_key)
    await service.set_binding(
        budget_id,
        key,
        mode=payload.mode,
        entity_ids=payload.entity_ids,
        answer=payload.answer,
        external=payload.external,
        external_amount=payload.external_amount,
        note=payload.note,
    )


@router.get("/{budget_id}/guide/preferences", response_model=PreferencesResponse)
async def guide_preferences(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> PreferencesResponse:
    return PreferencesResponse(**await service.preferences(budget_id))


@router.put("/{budget_id}/guide/preferences", response_model=PreferencesResponse)
async def set_guide_preferences(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: PreferencesUpdate,
) -> PreferencesResponse:
    changes = payload.model_dump(exclude_none=True)
    return PreferencesResponse(**await service.set_preferences(budget_id, changes))


@router.put("/{budget_id}/guide/progress/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_guide_step(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    stage_id: str,
    payload: StepUpdate,
) -> None:
    await service.set_step(budget_id, stage_id, payload.state)


@router.get("/{budget_id}/guide/checkup", response_model=CheckupResponse)
async def guide_checkup(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> CheckupResponse:
    return CheckupResponse(**await service.checkup(budget_id))


@router.post("/{budget_id}/guide/checkup/run", response_model=CheckupResponse)
async def run_health_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> CheckupResponse:
    """The health report, run because the user pressed the button.

    Same payload as the GET, plus a stamp recording that they looked. Refused
    rather than quietly empty when reviews are off — a run that does nothing
    must not report success.
    """
    result = await service.checkup(budget_id, stamp=True)
    if not result["enabled"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Financial health reviews are switched off for this budget",
        )
    return CheckupResponse(**result)


# ── scenario calculators ─────────────────────────────────────────────────────
# POST because the inputs are a document, not a filter; nothing is stored.


@router.post("/{budget_id}/guide/scenarios/payoff-plan", response_model=PayoffPlanResponse)
async def scenario_payoff_plan(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: PayoffPlanRequest,
) -> PayoffPlanResponse:
    debts = [CascadeDebt(**d.model_dump()) for d in payload.debts]
    return PayoffPlanResponse.model_validate(
        asdict(service.payoff_plan(debts, payload.extra, today_utc()))
    )


@router.post("/{budget_id}/guide/scenarios/pay-vs-save", response_model=PayVsSaveResponse)
async def scenario_pay_vs_save(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: PayVsSaveRequest,
) -> PayVsSaveResponse:
    return PayVsSaveResponse.model_validate(
        asdict(
            service.pay_vs_save(
                payload.balance,
                payload.annual_rate,
                payload.minimum_payment,
                payload.extra,
                payload.savings_apy,
                today_utc(),
            )
        )
    )


@router.post("/{budget_id}/guide/scenarios/loan-compare", response_model=LoanCompareResponse)
async def scenario_loan_compare(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: LoanCompareRequest,
) -> LoanCompareResponse:
    loans = [LoanCandidate(**loan.model_dump()) for loan in payload.loans]
    return LoanCompareResponse.model_validate(asdict(service.loan_compare(loans, today_utc())))


@router.post("/{budget_id}/guide/scenarios/emergency-fund", response_model=EmergencyFundResponse)
async def scenario_emergency_fund(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: EmergencyFundRequest,
) -> EmergencyFundResponse:
    plan = await service.emergency_fund_plan(
        budget_id, payload.months, payload.monthly_contribution
    )
    return EmergencyFundResponse.model_validate(asdict(plan))
