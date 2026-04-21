import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from igab.api.v1.schemas.category import (
    AssignmentUpdate,
    AutoAssignRequest,
    BudgetMonthResponse,
    CategoryBalance,
    CategoryCreate,
    CategoryGroupCreate,
    CategoryGroupResponse,
    CategoryGroupUpdate,
    CategoryHistoryBatchRequest,
    CategoryHistoryResponse,
    CategoryResponse,
    CategoryTargetCreate,
    CategoryTargetResponse,
    CategoryUpdate,
    FillTargetsApplyRequest,
    FillTargetsPreviewItem,
    FillTargetsPreviewResponse,
)
from igab.dependencies import CurrentUser, get_budget_service, get_category_group_repo, get_category_repo, get_target_repo, get_target_service
from igab.domain.exceptions import NotFoundError
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository
from igab.repositories.target_repo import TargetRepository
from igab.services.budget_service import BudgetService
from igab.services.target_service import TargetService

router = APIRouter()


# ─── Category Groups ──────────────────────────────────────────────────────────


@router.get("/{budget_id}/category-groups", response_model=list[CategoryGroupResponse])
async def list_category_groups(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
    include_hidden: bool = False,
) -> list[CategoryGroupResponse]:
    groups = await group_repo.get_all(budget_id, include_hidden=include_hidden)
    return [CategoryGroupResponse.model_validate(g) for g in groups]


@router.post(
    "/{budget_id}/category-groups",
    response_model=CategoryGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category_group(
    budget_id: uuid.UUID,
    body: CategoryGroupCreate,
    current_user: CurrentUser,
    group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
) -> CategoryGroupResponse:
    group = await group_repo.create(
        budget_id=budget_id,
        name=body.name,
        sort_order=body.sort_order,
    )
    return CategoryGroupResponse.model_validate(group)


@router.patch("/category-groups/{group_id}", response_model=CategoryGroupResponse)
async def update_category_group(
    group_id: uuid.UUID,
    body: CategoryGroupUpdate,
    current_user: CurrentUser,
    group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
) -> CategoryGroupResponse:
    try:
        changes = body.model_dump(exclude_none=True)
        group = await group_repo.update(group_id, **changes)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return CategoryGroupResponse.model_validate(group)


@router.delete("/category-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_group(
    group_id: uuid.UUID,
    current_user: CurrentUser,
    group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
) -> None:
    group = await group_repo.get_or_raise(group_id)
    if group.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete system category groups",
        )
    await group_repo.soft_delete(group_id)


# ─── Categories ───────────────────────────────────────────────────────────────


@router.get("/{budget_id}/categories", response_model=list[CategoryResponse])
async def list_categories(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    include_hidden: bool = False,
) -> list[CategoryResponse]:
    cats = await category_repo.get_all(budget_id, include_hidden=include_hidden)
    return [CategoryResponse.model_validate(c) for c in cats]


@router.post(
    "/{budget_id}/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    budget_id: uuid.UUID,
    body: CategoryCreate,
    current_user: CurrentUser,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> CategoryResponse:
    cat = await category_repo.create(
        budget_id=budget_id,
        category_group_id=body.category_group_id,
        name=body.name,
        sort_order=body.sort_order,
        note=body.note,
    )
    return CategoryResponse.model_validate(cat)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    current_user: CurrentUser,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> CategoryResponse:
    try:
        changes = body.model_dump(exclude_none=True)
        cat = await category_repo.update(category_id, **changes)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return CategoryResponse.model_validate(cat)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    current_user: CurrentUser,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> None:
    await category_repo.soft_delete(category_id)


# ─── Budget Month / Assignments ───────────────────────────────────────────────


@router.get("/{budget_id}/months/{month}", response_model=BudgetMonthResponse)
async def get_budget_month(
    budget_id: uuid.UUID,
    month: date,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
) -> BudgetMonthResponse:
    summary = await budget_service.get_budget_summary(budget_id, month)
    return BudgetMonthResponse(
        month=month,
        to_be_assigned=summary.to_be_assigned,
        total_assigned=summary.total_assigned,
        total_activity=summary.total_activity,
        category_balances=[
            CategoryBalance(
                category_id=b.category_id,
                month=b.month,
                assigned=b.assigned,
                activity=b.activity,
                available=b.available,
            )
            for b in summary.category_balances
        ],
    )


# ─── Category Targets ─────────────────────────────────────────────────────────


@router.post(
    "/categories/{category_id}/target",
    response_model=CategoryTargetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_category_target(
    category_id: uuid.UUID,
    body: CategoryTargetCreate,
    current_user: CurrentUser,
    target_svc: Annotated[TargetService, Depends(get_target_service)],
) -> CategoryTargetResponse:
    target = await target_svc.upsert(
        category_id=category_id,
        target_type=body.target_type,
        target_amount=body.target_amount,
        target_date=body.target_date,
        repeat_frequency=body.repeat_frequency,
    )
    return CategoryTargetResponse.model_validate(target)


@router.get("/categories/{category_id}/target", response_model=CategoryTargetResponse | None)
async def get_category_target(
    category_id: uuid.UUID,
    current_user: CurrentUser,
    target_svc: Annotated[TargetService, Depends(get_target_service)],
) -> CategoryTargetResponse | None:
    target = await target_svc.get(category_id)
    if target is None:
        return None
    return CategoryTargetResponse.model_validate(target)


@router.delete("/categories/{category_id}/target", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_target(
    category_id: uuid.UUID,
    current_user: CurrentUser,
    target_svc: Annotated[TargetService, Depends(get_target_service)],
) -> None:
    await target_svc.delete(category_id)


@router.patch("/categories/{category_id}/assignment", status_code=status.HTTP_204_NO_CONTENT)
async def set_category_assignment(
    category_id: uuid.UUID,
    body: AssignmentUpdate,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    month: date = Query(...),
    budget_id: uuid.UUID = Query(...),
) -> None:
    await budget_service.set_assignment(budget_id, category_id, month, body.amount)


# ─── Category History ─────────────────────────────────────────────────────────


@router.get(
    "/{budget_id}/categories/{category_id}/history",
    response_model=CategoryHistoryResponse,
)
async def get_category_history(
    budget_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    month: date = Query(default=None),
) -> CategoryHistoryResponse:
    from datetime import date as date_cls
    current = month or date_cls.today()
    history = await budget_service.get_category_history(category_id, current)
    return CategoryHistoryResponse(
        category_id=history.category_id,
        last_month_assigned=history.last_month_assigned,
        last_month_spent=history.last_month_spent,
        average_assigned=history.average_assigned,
        average_spent=history.average_spent,
        months_included=history.months_included,
    )


@router.post(
    "/{budget_id}/categories/history/batch",
    response_model=list[CategoryHistoryResponse],
)
async def get_category_history_batch(
    budget_id: uuid.UUID,
    body: CategoryHistoryBatchRequest,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    month: date = Query(default=None),
) -> list[CategoryHistoryResponse]:
    from datetime import date as date_cls
    current = month or date_cls.today()
    results = []
    for cat_id in body.category_ids:
        h = await budget_service.get_category_history(cat_id, current)
        results.append(CategoryHistoryResponse(
            category_id=h.category_id,
            last_month_assigned=h.last_month_assigned,
            last_month_spent=h.last_month_spent,
            average_assigned=h.average_assigned,
            average_spent=h.average_spent,
            months_included=h.months_included,
        ))
    return results


@router.post("/{budget_id}/categories/auto-assign", status_code=status.HTTP_204_NO_CONTENT)
async def auto_assign_categories(
    budget_id: uuid.UUID,
    body: AutoAssignRequest,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
) -> None:
    for cat_id in body.category_ids:
        await budget_service.auto_assign(budget_id, cat_id, body.month, body.action)


@router.get(
    "/{budget_id}/auto-assign/preview",
    response_model=FillTargetsPreviewResponse,
)
async def fill_targets_preview(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    target_repo: Annotated[TargetRepository, Depends(get_target_repo)],
    target_service: Annotated[TargetService, Depends(get_target_service)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    month: date = Query(default=None),
) -> FillTargetsPreviewResponse:
    from datetime import date as date_cls
    current_month = month or date_cls.today()

    summary = await budget_service.get_budget_summary(budget_id, current_month)
    tba = summary.to_be_assigned
    balance_map = {b.category_id: b for b in summary.category_balances}

    category_ids = list(balance_map.keys())
    targets = await target_repo.get_by_category_ids(category_ids)
    target_map = {t.category_id: t for t in targets}

    categories = await category_repo.get_all(budget_id, include_hidden=True)
    name_map = {c.id: c.name for c in categories}

    items_with_need: list[tuple[uuid.UUID, Decimal]] = []
    for cat_id, target in target_map.items():
        bal = balance_map.get(cat_id)
        if bal is None:
            continue
        needed = target_service.calculate_needed(
            target,
            Decimal(str(bal.assigned)),
            Decimal(str(bal.available)),
        )
        if needed > 0:
            items_with_need.append((cat_id, needed))

    available_tba = max(Decimal("0"), tba)
    total_shortfall = sum(n for _, n in items_with_need)

    preview_items: list[FillTargetsPreviewItem] = []
    for cat_id, needed in items_with_need:
        bal = balance_map[cat_id]
        if total_shortfall > 0:
            proportion = needed / total_shortfall
            proposed = min(needed, (proportion * available_tba).quantize(Decimal("0.01")))
        else:
            proposed = Decimal("0")
        current_assigned = Decimal(str(bal.assigned))
        preview_items.append(
            FillTargetsPreviewItem(
                category_id=cat_id,
                category_name=name_map.get(cat_id, "Unknown"),
                current_assigned=current_assigned,
                proposed_addition=proposed,
                new_assigned=current_assigned + proposed,
            )
        )

    preview_items.sort(key=lambda x: x.proposed_addition, reverse=True)
    total_addition = sum(i.proposed_addition for i in preview_items)

    return FillTargetsPreviewResponse(
        items=preview_items,
        total_addition=total_addition,
        tba_before=tba,
        tba_after=tba - total_addition,
    )


@router.post("/{budget_id}/auto-assign/apply", status_code=status.HTTP_204_NO_CONTENT)
async def fill_targets_apply(
    budget_id: uuid.UUID,
    body: FillTargetsApplyRequest,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
) -> None:
    for item in body.items:
        if item.proposed_addition > 0:
            await budget_service.set_assignment(
                budget_id, item.category_id, body.month, item.new_assigned
            )
