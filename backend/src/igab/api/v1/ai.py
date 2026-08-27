from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from igab.api.v1.schemas.ai import (
    AIStatusResponse,
    InsightsResponse,
    OllamaModelInfo,
    OllamaModelsResponse,
    SuggestCategoryRequest,
    SuggestCategoryResponse,
    SuggestRegexRequest,
    SuggestRegexResponse,
)
from igab.dependencies import BudgetAccess, CurrentUser, get_ai_service
from igab.services.ai_service import AIService

router = APIRouter()


@router.get("/ai/status", response_model=AIStatusResponse)
async def ai_status(
    current_user: CurrentUser,
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
) -> AIStatusResponse:
    """Check if AI is enabled and Ollama is reachable."""
    result = await ai_svc.check_availability()
    return AIStatusResponse(**result)


@router.get("/ai/models", response_model=OllamaModelsResponse)
async def list_ollama_models(
    current_user: CurrentUser,
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
) -> OllamaModelsResponse:
    """List available models from the configured Ollama instance."""
    models = await ai_svc.list_models()
    return OllamaModelsResponse(models=[OllamaModelInfo(**m) for m in models])


@router.post("/{budget_id}/ai/suggest-category", response_model=SuggestCategoryResponse)
async def suggest_category(
    budget_id: BudgetAccess,
    body: SuggestCategoryRequest,
    current_user: CurrentUser,
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
) -> SuggestCategoryResponse:
    result = await ai_svc.suggest_category(budget_id, body.payee_name, body.amount, body.memo)
    return SuggestCategoryResponse(**result)


@router.post("/{budget_id}/ai/suggest-regex", response_model=SuggestRegexResponse)
async def suggest_regex(
    budget_id: BudgetAccess,
    body: SuggestRegexRequest,
    current_user: CurrentUser,
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
) -> SuggestRegexResponse:
    """Candidate payee match patterns generalizing the given raw names,
    most specific first."""
    patterns = await ai_svc.suggest_regex(body.names)
    return SuggestRegexResponse(patterns=patterns)


@router.get("/{budget_id}/ai/insights", response_model=InsightsResponse)
async def spending_insights(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
    month: date | None = None,
) -> InsightsResponse:
    target_month = month or date.today()
    text = await ai_svc.spending_insights(budget_id, target_month)
    return InsightsResponse(insights=text)
