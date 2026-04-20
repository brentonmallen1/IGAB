import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from igab.api.v1.schemas.ai import (
    InsightsResponse,
    NormalizePayeeRequest,
    NormalizePayeeResponse,
    PayeeCleanupGroup,
    SuggestCategoryRequest,
    SuggestCategoryResponse,
)
from igab.dependencies import CurrentUser, get_ai_service
from igab.services.ai_service import AIService

router = APIRouter()


@router.post("/{budget_id}/ai/suggest-category", response_model=SuggestCategoryResponse)
async def suggest_category(
    budget_id: uuid.UUID,
    body: SuggestCategoryRequest,
    current_user: CurrentUser,
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
) -> SuggestCategoryResponse:
    result = await ai_svc.suggest_category(
        budget_id, body.payee_name, body.amount, body.memo
    )
    return SuggestCategoryResponse(**result)


@router.post("/{budget_id}/ai/normalize-payee", response_model=NormalizePayeeResponse)
async def normalize_payee(
    budget_id: uuid.UUID,
    body: NormalizePayeeRequest,
    current_user: CurrentUser,
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
) -> NormalizePayeeResponse:
    normalized = await ai_svc.normalize_payee(body.payee_name)
    return NormalizePayeeResponse(normalized_name=normalized)


@router.get("/{budget_id}/ai/payee-cleanup", response_model=list[PayeeCleanupGroup])
async def payee_cleanup_suggestions(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
) -> list[PayeeCleanupGroup]:
    groups = await ai_svc.suggest_payee_merges(budget_id)
    return [PayeeCleanupGroup(**g) for g in groups]


@router.get("/{budget_id}/ai/insights", response_model=InsightsResponse)
async def spending_insights(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
    month: date | None = None,
) -> InsightsResponse:
    target_month = month or date.today()
    text = await ai_svc.spending_insights(budget_id, target_month)
    return InsightsResponse(insights=text)
