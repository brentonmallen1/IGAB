import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from igab.api.v1.schemas.category import (
    AssignApplyRequest,
    AssignApplyResponse,
    AssignmentUpdate,
    AssignPreviewItemOut,
    AssignPreviewResponse,
    AssignStrategyTotal,
    AssignStrategyTotalsResponse,
    AutoAssignRequest,
    BudgetMonthResponse,
    BudgetMoveResponse,
    CategoryBalance,
    CategoryClassification,
    CategoryClassSlice,
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
    CoverOverspentApplyRequest,
    CoverOverspentPreviewItem,
    CoverOverspentPreviewResponse,
    FutureOverspendPreviewRequest,
    FutureOverspendPreviewResponse,
    FutureOverspendWarningOut,
    MoveMoneyRequest,
    RecentPayeeResponse,
)
from igab.db.models import CategoryGroup, Transaction
from igab.dependencies import (
    BudgetAccess,
    CategoryAccess,
    CategoryGroupAccess,
    CurrentUser,
    SessionDep,
    get_assign_service,
    get_budget_service,
    get_category_group_repo,
    get_category_repo,
    get_change_recorder,
    get_target_repo,
    get_target_service,
    get_transaction_repo,
)
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    ACTIVITY_REASON,
    CLASS_LABEL,
    ActivityClass,
    apply_class_joins,
    explain,
)
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository
from igab.repositories.target_repo import TargetRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import LEAF, NOT_DELETED, POSTED
from igab.services.assign_service import AssignPreview, AssignService
from igab.services.budget_service import BudgetService
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
from igab.services.ownership import require_in_budget
from igab.services.target_service import TargetService

router = APIRouter()


# ─── Category Groups ──────────────────────────────────────────────────────────


@router.get("/{budget_id}/category-groups", response_model=list[CategoryGroupResponse])
async def list_category_groups(
    budget_id: BudgetAccess,
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
    budget_id: BudgetAccess,
    body: CategoryGroupCreate,
    current_user: CurrentUser,
    group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> CategoryGroupResponse:
    group = await group_repo.create(
        budget_id=budget_id,
        name=body.name,
        sort_order=body.sort_order,
    )
    await recorder.record(
        budget_id=budget_id,
        entity_type="category_group",
        entity_id=group.id,
        action="create",
        after=snapshot("category_group", group),
    )
    return CategoryGroupResponse.model_validate(group)


@router.patch("/category-groups/{group_id}", response_model=CategoryGroupResponse)
async def update_category_group(
    group_id: CategoryGroupAccess,
    body: CategoryGroupUpdate,
    current_user: CurrentUser,
    group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> CategoryGroupResponse:
    try:
        before = snapshot("category_group", await group_repo.get_or_raise(group_id))
        changes = body.model_dump(exclude_none=True)
        group = await group_repo.update(group_id, **changes)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    after = snapshot("category_group", group)
    if snapshots_match(after, before):
        await recorder.record(
            budget_id=group.budget_id,
            entity_type="category_group",
            entity_id=group_id,
            action="update",
            before=before,
            after=after,
        )
    return CategoryGroupResponse.model_validate(group)


@router.delete("/category-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_group(
    group_id: CategoryGroupAccess,
    current_user: CurrentUser,
    group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> None:
    group = await group_repo.get_or_raise(group_id)
    if group.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete system category groups",
        )
    before = snapshot("category_group", group)
    await group_repo.soft_delete(group_id)
    await recorder.record(
        budget_id=group.budget_id,
        entity_type="category_group",
        entity_id=group_id,
        action="delete",
        before=before,
    )


# ─── Categories ───────────────────────────────────────────────────────────────


@router.get("/{budget_id}/categories", response_model=list[CategoryResponse])
async def list_categories(
    budget_id: BudgetAccess,
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
    budget_id: BudgetAccess,
    body: CategoryCreate,
    current_user: CurrentUser,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> CategoryResponse:
    # category_group_id comes from the body, bypassing BudgetAccess; reject a
    # group belonging to another budget before creating the category.
    await require_in_budget(
        category_repo.session, CategoryGroup, body.category_group_id, budget_id, "Category group"
    )
    cat = await category_repo.create(
        budget_id=budget_id,
        category_group_id=body.category_group_id,
        name=body.name,
        subtitle=body.subtitle,
        sort_order=body.sort_order,
        note=body.note,
    )
    await recorder.record(
        budget_id=budget_id,
        entity_type="category",
        entity_id=cat.id,
        action="create",
        after=snapshot("category", cat),
    )
    # Reload with tags eagerly loaded; serializing the freshly created row would
    # otherwise lazy-load the `tags` relationship in a sync context and raise
    # MissingGreenlet.
    created = await category_repo.get_with_tags(cat.id)
    return CategoryResponse.model_validate(created)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: CategoryAccess,
    body: CategoryUpdate,
    current_user: CurrentUser,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> CategoryResponse:
    try:
        before = snapshot("category", await category_repo.get_or_raise(category_id))
        changes = body.model_dump(exclude_unset=True)
        cat = await category_repo.update(category_id, **changes)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    after = snapshot("category", cat)
    if snapshots_match(after, before):
        await recorder.record(
            budget_id=cat.budget_id,
            entity_type="category",
            entity_id=category_id,
            action="update",
            before=before,
            after=after,
        )
    return CategoryResponse.model_validate(await category_repo.get_with_tags(category_id))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: CategoryAccess,
    current_user: CurrentUser,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> None:
    cat = await category_repo.get_or_raise(category_id)
    before = snapshot("category", cat)
    await category_repo.soft_delete(category_id)
    await recorder.record(
        budget_id=cat.budget_id,
        entity_type="category",
        entity_id=category_id,
        action="delete",
        before=before,
    )


# ─── Budget Month / Assignments ───────────────────────────────────────────────


@router.get("/{budget_id}/months/{month}", response_model=BudgetMonthResponse)
async def get_budget_month(
    budget_id: BudgetAccess,
    month: date,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    target_service: Annotated[TargetService, Depends(get_target_service)],
) -> BudgetMonthResponse:
    summary = await budget_service.get_budget_summary(budget_id, month)

    # Targets are loaded here rather than inside get_budget_summary on purpose:
    # AssignService._gather calls that method and loads targets itself, so
    # folding them in would do the work twice on the strategies path.
    targets = {
        t.category_id: t
        for t in await target_service.repo.get_by_category_ids(
            [b.category_id for b in summary.category_balances]
        )
    }

    return BudgetMonthResponse(
        month=month,
        to_be_assigned=summary.to_be_assigned,
        total_assigned=summary.total_assigned,
        total_activity=summary.total_activity,
        total_overspent=summary.total_overspent,
        overspent_count=summary.overspent_count,
        assigned_in_future=summary.assigned_in_future,
        category_balances=[
            CategoryBalance(
                category_id=b.category_id,
                month=b.month,
                assigned=b.assigned,
                activity=b.activity,
                available=b.available,
                target_status=(
                    target_service.calculate_status(t, b.assigned, b.available)
                    if (t := targets.get(b.category_id))
                    else None
                ),
                needed_this_month=(
                    target_service.calculate_needed(t, b.assigned, b.available)
                    if (t := targets.get(b.category_id))
                    else None
                ),
            )
            for b in summary.category_balances
        ],
    )


@router.post(
    "/{budget_id}/months/preview-overspend",
    response_model=FutureOverspendPreviewResponse,
)
async def preview_future_overspend(
    budget_id: BudgetAccess,
    body: FutureOverspendPreviewRequest,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
) -> FutureOverspendPreviewResponse:
    """Pre-save check: would this edit push a future month's category negative?"""
    warnings = await budget_service.preview_future_overspend(
        budget_id,
        [(i.category_id, i.date, i.amount_delta) for i in body.items],
    )
    return FutureOverspendPreviewResponse(
        warnings=[
            FutureOverspendWarningOut(
                category_id=w.category_id,
                category_name=w.category_name,
                month=w.month,
                available_before=w.available_before,
                available_after=w.available_after,
            )
            for w in warnings
        ]
    )


# ─── Category Targets ─────────────────────────────────────────────────────────


@router.post(
    "/categories/{category_id}/target",
    response_model=CategoryTargetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_category_target(
    category_id: CategoryAccess,
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
    category_id: CategoryAccess,
    current_user: CurrentUser,
    target_svc: Annotated[TargetService, Depends(get_target_service)],
) -> CategoryTargetResponse | None:
    target = await target_svc.get(category_id)
    if target is None:
        return None
    return CategoryTargetResponse.model_validate(target)


@router.delete("/categories/{category_id}/target", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_target(
    category_id: CategoryAccess,
    current_user: CurrentUser,
    target_svc: Annotated[TargetService, Depends(get_target_service)],
) -> None:
    await target_svc.delete(category_id)


@router.get("/{budget_id}/targets", response_model=list[CategoryTargetResponse])
async def list_budget_targets(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    target_repo: Annotated[TargetRepository, Depends(get_target_repo)],
) -> list[CategoryTargetResponse]:
    categories = await category_repo.get_all(budget_id)
    category_ids = [c.id for c in categories]
    targets = await target_repo.get_by_category_ids(category_ids)
    return [CategoryTargetResponse.model_validate(t) for t in targets]


@router.get(
    "/categories/{category_id}/classification",
    response_model=CategoryClassification,
)
async def get_category_classification(
    category_id: CategoryAccess,
    current_user: CurrentUser,
    session: SessionDep,
) -> CategoryClassification:
    """How this category's recent activity counts in reports.

    The per-transaction endpoint answers "why is this row not spending?";
    this one answers it a level earlier — on the category itself, before the
    user has opened a report and wondered where Car Payment went. Same
    reasoning as there: derived via correlated subqueries, so it is its own
    endpoint fetched when the inspector opens, not a field on every list row.

    Trailing twelve months of outflow, not the viewed month: the badge
    describes how the category *behaves*, and a month with no activity would
    otherwise flicker the tag off.
    """
    window_start = date.today() - timedelta(days=365)
    rows = (
        await session.execute(
            apply_class_joins(
                # select_from, not a stray Transaction column: this aggregates,
                # so an extra column would have to join the GROUP BY.
                select(
                    ACTIVITY_CLASS.label("cls"),
                    ACTIVITY_REASON.label("reason"),
                    func.sum(func.abs(Transaction.amount)).label("total"),
                    func.count().label("count"),
                ).select_from(Transaction)
            )
            .where(
                Transaction.category_id == category_id,
                NOT_DELETED,
                POSTED,
                LEAF,
                Transaction.amount < 0,
                Transaction.date >= window_start,
            )
            .group_by(ACTIVITY_CLASS, ACTIVITY_REASON)
        )
    ).all()

    by_class: dict[str, dict] = {}
    for r in rows:
        slot = by_class.setdefault(r.cls, {"total": Decimal("0"), "count": 0, "reasons": {}})
        slot["total"] += r.total
        slot["count"] += r.count
        slot["reasons"][r.reason] = slot["reasons"].get(r.reason, Decimal("0")) + r.total

    ordered = sorted(by_class.items(), key=lambda kv: kv[1]["total"], reverse=True)
    classes = [
        CategoryClassSlice(
            activity_class=cls,
            label=CLASS_LABEL[ActivityClass(cls)],
            total=v["total"].quantize(Decimal("0.01")),
            count=v["count"],
        )
        for cls, v in ordered
    ]

    dominant = dominant_label = explanation = None
    grand = sum((v["total"] for _, v in ordered), Decimal("0"))
    if ordered and grand > 0:
        cls, v = ordered[0]
        if cls != ActivityClass.SPENDING.value and v["total"] * 2 > grand:
            dominant = cls
            dominant_label = CLASS_LABEL[ActivityClass(cls)]
            top_reason = max(v["reasons"], key=lambda k: v["reasons"][k])
            qualifier = "All" if v["total"] == grand else "Most"
            explanation = (
                f"{qualifier} of this category's activity in the last 12 months "
                f"counts as {dominant_label} in reports, because "
                f"{explain(top_reason)}."
            )

    return CategoryClassification(
        classes=classes,
        dominant=dominant,
        dominant_label=dominant_label,
        explanation=explanation,
    )


@router.get("/categories/{category_id}/recent-payee", response_model=RecentPayeeResponse | None)
async def get_recent_payee_for_category(
    category_id: CategoryAccess,
    current_user: CurrentUser,
    budget_id: BudgetAccess,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> RecentPayeeResponse | None:
    """Most recent (non-transfer) payee in this category, for add-transaction prefill."""
    row = await txn_repo.get_most_recent_payee_for_category(budget_id, category_id)
    if row is None:
        return None
    return RecentPayeeResponse(payee_id=row[0], name=row[1])


@router.patch("/categories/{category_id}/assignment", status_code=status.HTTP_204_NO_CONTENT)
async def set_category_assignment(
    category_id: CategoryAccess,
    body: AssignmentUpdate,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    budget_id: BudgetAccess,
    month: date = Query(...),
) -> None:
    await budget_service.set_assignment(budget_id, category_id, month, body.amount)


@router.post("/{budget_id}/budget/move-money", status_code=status.HTTP_204_NO_CONTENT)
async def move_money(
    budget_id: BudgetAccess,
    body: MoveMoneyRequest,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
) -> None:
    """Move money between envelopes; a null side means To-Be-Assigned."""
    try:
        await budget_service.move_money(
            budget_id,
            body.from_category_id,
            body.to_category_id,
            body.amount,
            body.month,
        )
    except InvariantViolation as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{budget_id}/budget/moves", response_model=list[BudgetMoveResponse])
async def get_move_history(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    month: date = Query(...),
) -> list[BudgetMoveResponse]:
    moves = await budget_service.get_move_history(budget_id, month)
    return [BudgetMoveResponse.model_validate(m) for m in moves]


# ─── Category History ─────────────────────────────────────────────────────────


@router.get(
    "/{budget_id}/categories/{category_id}/history",
    response_model=CategoryHistoryResponse,
)
async def get_category_history(
    budget_id: BudgetAccess,
    category_id: uuid.UUID,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    month: date = Query(default=None),
) -> CategoryHistoryResponse:
    from datetime import date as date_cls

    current = month or date_cls.today()
    history = await budget_service.get_category_history(budget_id, category_id, current)
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
    budget_id: BudgetAccess,
    body: CategoryHistoryBatchRequest,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    month: date = Query(default=None),
) -> list[CategoryHistoryResponse]:
    from datetime import date as date_cls

    current = month or date_cls.today()
    results = []
    for cat_id in body.category_ids:
        h = await budget_service.get_category_history(budget_id, cat_id, current)
        results.append(
            CategoryHistoryResponse(
                category_id=h.category_id,
                last_month_assigned=h.last_month_assigned,
                last_month_spent=h.last_month_spent,
                average_assigned=h.average_assigned,
                average_spent=h.average_spent,
                months_included=h.months_included,
            )
        )
    return results


@router.post("/{budget_id}/categories/auto-assign", status_code=status.HTTP_204_NO_CONTENT)
async def auto_assign_categories(
    budget_id: BudgetAccess,
    body: AutoAssignRequest,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
) -> None:
    with budget_service.changes.batch():
        for cat_id in body.category_ids:
            await budget_service.auto_assign(budget_id, cat_id, body.month, body.action)


# ─── Assign Strategies (TBA hero dropdown) ────────────────────────────────────


def _assign_preview_out(preview: AssignPreview) -> AssignPreviewResponse:
    return AssignPreviewResponse(
        strategy=preview.strategy,
        items=[
            AssignPreviewItemOut(
                category_id=i.category_id,
                category_name=i.category_name,
                current_assigned=i.current_assigned,
                delta=i.delta,
                new_assigned=i.new_assigned,
            )
            for i in preview.items
        ],
        total_needed=preview.total_needed,
        to_assign=preview.to_assign,
        to_return=preview.to_return,
        tba_before=preview.tba_before,
        tba_after=preview.tba_after,
    )


@router.get("/{budget_id}/assign/strategies", response_model=AssignStrategyTotalsResponse)
async def assign_strategy_totals(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    assign_service: Annotated[AssignService, Depends(get_assign_service)],
    month: date = Query(...),
) -> AssignStrategyTotalsResponse:
    """Per-strategy totals for the Assign dropdown menu — one call, all rows."""
    totals = await assign_service.strategy_totals(budget_id, month)
    return AssignStrategyTotalsResponse(
        month=totals.month,
        tba=totals.tba,
        total_overspent=totals.total_overspent,
        strategies=[
            AssignStrategyTotal(
                strategy=p.strategy,
                total_amount=p.total_amount,
                total_needed=p.total_needed,
                to_assign=p.to_assign,
                to_return=p.to_return,
                affected_count=p.affected_count,
            )
            for p in totals.strategies
        ],
    )


@router.get("/{budget_id}/assign/preview", response_model=AssignPreviewResponse)
async def assign_strategy_preview(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    assign_service: Annotated[AssignService, Depends(get_assign_service)],
    month: date = Query(...),
    strategy: str = Query(...),
) -> AssignPreviewResponse:
    try:
        preview = await assign_service.preview(budget_id, month, strategy)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return _assign_preview_out(preview)


@router.post("/{budget_id}/assign/apply", response_model=AssignApplyResponse)
async def assign_strategy_apply(
    budget_id: BudgetAccess,
    body: AssignApplyRequest,
    current_user: CurrentUser,
    assign_service: Annotated[AssignService, Depends(get_assign_service)],
) -> AssignApplyResponse:
    """Recompute the strategy server-side and apply it through move_money.

    The body carries no amounts on purpose: applied deltas are derived from
    live balances, so a stale preview can never over- or mis-assign."""
    try:
        applied = await assign_service.apply(budget_id, body.month, body.strategy)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return AssignApplyResponse(
        to_assign=applied.to_assign,
        to_return=applied.to_return,
        categories_changed=applied.affected_count,
        tba_after=applied.tba_after,
    )


@router.get(
    "/{budget_id}/cover-overspent/preview",
    response_model=CoverOverspentPreviewResponse,
)
async def cover_overspent_preview(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    month: date = Query(default=None),
) -> CoverOverspentPreviewResponse:
    from datetime import date as date_cls

    current_month = month or date_cls.today()
    preview = await budget_service.cover_overspent_preview(budget_id, current_month)
    return CoverOverspentPreviewResponse(
        items=[
            CoverOverspentPreviewItem(
                category_id=i.category_id,
                category_name=i.category_name,
                overspent=i.overspent,
                proposed_addition=i.proposed_addition,
                remaining_after=i.remaining_after,
            )
            for i in preview.items
        ],
        total_overspent=preview.total_overspent,
        total_addition=preview.total_addition,
        tba_before=preview.tba_before,
        tba_after=preview.tba_after,
    )


@router.post("/{budget_id}/cover-overspent/apply", status_code=status.HTTP_204_NO_CONTENT)
async def cover_overspent_apply(
    budget_id: BudgetAccess,
    body: CoverOverspentApplyRequest,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
) -> None:
    try:
        await budget_service.cover_overspent_apply(
            budget_id,
            body.month,
            [(item.category_id, item.proposed_addition) for item in body.items],
        )
    except InvariantViolation as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
