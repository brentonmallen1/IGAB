"""Guide endpoints.

Thin by design: parse, authorise, delegate to GuideService, return. Everything
that decides anything lives in igab.guide, which nothing else imports.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.guide import (
    BindingUpdate,
    CandidatesResponse,
    GuideOverview,
    PreferencesResponse,
    PreferencesUpdate,
    SignalsResponse,
    StepUpdate,
)
from igab.dependencies import BudgetAccess, CurrentUser, get_guide_service
from igab.guide.concepts import CONCEPT_KEYS
from igab.guide.service import GuideService

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
