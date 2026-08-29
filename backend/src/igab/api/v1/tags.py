from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.tag import (
    BulkSetCategoryTagsRequest,
    SetTagsRequest,
    TagCreate,
    TagOut,
    TagOutSimple,
    TagSuggestionOut,
    TagUpdate,
)
from igab.dependencies import (
    BudgetAccess,
    CategoryAccess,
    CurrentUser,
    PayeeAccess,
    TagAccess,
    get_category_repo,
    get_payee_repo,
    get_tag_repo,
)
from igab.domain.tag_hints import DERIVED_KEYS, TAG_HINTS, suggest_review_tags
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.tag_repo import (
    SYSTEM_TAGS,
    TAG_COLOR_SLOTS,
    TagRepository,
    seed_system_tags,
)

router = APIRouter()


@router.get("/{budget_id}/tags", response_model=list[TagOut])
async def list_tags(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
) -> list[TagOut]:
    tags_with_counts = await tag_repo.list_for_budget_with_counts(budget_id)

    # Backfill any system tag this budget is missing. Testing "has none at
    # all" was the bug: `debt_principal` was added to SYSTEM_TAGS after the
    # backfill migration was written, so every budget that already had the
    # other three was judged done and never got it.
    present = {tag.system_key for tag, _, _ in tags_with_counts if tag.system_key}
    if any(key not in present for key, _, _ in SYSTEM_TAGS):
        await seed_system_tags(tag_repo.session, budget_id)
        tags_with_counts = await tag_repo.list_for_budget_with_counts(budget_id)

    return [
        TagOut(
            id=tag.id,
            name=tag.name,
            system_key=tag.system_key,
            color_slot=tag.color_slot,
            category_count=cat_count,
            payee_count=payee_count,
        )
        for tag, cat_count, payee_count in tags_with_counts
    ]


@router.post("/{budget_id}/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    budget_id: BudgetAccess,
    body: TagCreate,
    current_user: CurrentUser,
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
) -> TagOut:
    if body.color_slot and body.color_slot not in TAG_COLOR_SLOTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid color_slot. Must be one of: {', '.join(sorted(TAG_COLOR_SLOTS))}",
        )
    existing = await tag_repo.get_by_name(budget_id, body.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tag '{body.name}' already exists",
        )
    tag = await tag_repo.create(
        budget_id=budget_id,
        name=body.name,
        color_slot=body.color_slot,
    )
    return TagOut(
        id=tag.id,
        name=tag.name,
        system_key=tag.system_key,
        color_slot=tag.color_slot,
        category_count=0,
        payee_count=0,
    )


@router.patch("/{budget_id}/tags/{tag_id}", response_model=TagOut)
async def update_tag(
    budget_id: BudgetAccess,
    tag_id: TagAccess,
    body: TagUpdate,
    current_user: CurrentUser,
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
) -> TagOut:
    tag = await tag_repo.get_or_raise(tag_id)
    updates: dict = {}
    if body.name is not None:
        # A system tag's name is how the user recognises what it does — a
        # "Savings" tag renamed "Fun" still routes money to the savings
        # reports. Colour is cosmetic; the name is not.
        if tag.system_key is not None and body.name != tag.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="System tags cannot be renamed; change the colour instead",
            )
        if body.name.lower() != tag.name.lower():
            existing = await tag_repo.get_by_name(budget_id, body.name)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Tag '{body.name}' already exists",
                )
        updates["name"] = body.name
    if body.color_slot is not None:
        if body.color_slot not in TAG_COLOR_SLOTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid color_slot. Must be one of: {', '.join(sorted(TAG_COLOR_SLOTS))}",
            )
        updates["color_slot"] = body.color_slot
    if updates:
        tag = await tag_repo.update(tag_id, **updates)
    tags_with_counts = await tag_repo.list_for_budget_with_counts(budget_id)
    for t, cat_count, payee_count in tags_with_counts:
        if t.id == tag_id:
            return TagOut(
                id=t.id,
                name=t.name,
                system_key=t.system_key,
                color_slot=t.color_slot,
                category_count=cat_count,
                payee_count=payee_count,
            )
    return TagOut.model_validate(tag)


@router.delete("/{budget_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    budget_id: BudgetAccess,
    tag_id: TagAccess,
    current_user: CurrentUser,
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
) -> None:
    tag = await tag_repo.get_or_raise(tag_id)
    if tag.system_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System tags cannot be deleted",
        )
    await tag_repo.delete_with_associations(tag_id)


@router.get("/{budget_id}/tags/suggestions", response_model=list[TagSuggestionOut])
async def list_tag_suggestions(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> list[TagSuggestionOut]:
    """System tags each category's names point at but does not carry.

    Proposals only. Nothing here is written until the caller sends them back
    through the bulk update, which is the whole difference between this and
    what the importer does: the importer applies two keys it is confident
    about, and everything else is offered to a person.

    Seeds first, because a budget can be missing a system tag entirely — the
    backfill migration predates three of the six keys, and `list_tags` is the
    only other place that repairs it. Suggesting a key whose tag row does not
    exist would offer a choice that cannot be accepted.
    """
    await seed_system_tags(tag_repo.session, budget_id)

    rows = await category_repo.get_taggable_with_group_names(budget_id)
    existing = await tag_repo.get_tags_for_categories([c.id for c, _ in rows])
    applied = {h.system_key for h in TAG_HINTS if h.applied_on_import}

    out: list[TagSuggestionOut] = []
    for category, group_name in rows:
        held = {t.system_key for t in existing.get(category.id, []) if t.system_key}
        for suggestion in suggest_review_tags(category.name, group_name):
            if suggestion.system_key in held:
                continue
            out.append(
                TagSuggestionOut(
                    category_id=category.id,
                    system_key=suggestion.system_key,
                    matched_on=suggestion.matched_on,
                    applied_on_import=suggestion.system_key in applied,
                )
            )
    return out


@router.put("/{budget_id}/categories/tags", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_set_category_tags(
    budget_id: BudgetAccess,
    body: BulkSetCategoryTagsRequest,
    current_user: CurrentUser,
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> None:
    """Set tags on many categories at once, in one transaction.

    The import review changes a dozen categories in a single decision; sending
    a dozen requests would leave the budget half-reviewed if one failed, and
    each one is a classification override.

    Every id is checked against this budget before anything is written, so a
    stray id fails the whole call rather than applying a partial review.
    """
    for update in body.updates:
        category = await category_repo.get(update.category_id)
        if category is None or category.budget_id != budget_id or category.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category {update.category_id} not found",
            )
        for tag_id in update.tag_ids:
            tag = await tag_repo.get(tag_id)
            if tag is None or tag.budget_id != budget_id or tag.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tag {tag_id} not found",
                )
            if tag.system_key in DERIVED_KEYS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"The {tag.name} tag is set by the wishlist itself, from which "
                        "envelopes fund an open wish. Setting it by hand would be undone "
                        "on the next wishlist change."
                    ),
                )

    for update in body.updates:
        await tag_repo.set_category_tags(update.category_id, update.tag_ids)


@router.put("/{budget_id}/categories/{category_id}/tags", response_model=list[TagOutSimple])
async def set_category_tags(
    budget_id: BudgetAccess,
    category_id: CategoryAccess,
    body: SetTagsRequest,
    current_user: CurrentUser,
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> list[TagOutSimple]:
    for tag_id in body.tag_ids:
        tag = await tag_repo.get(tag_id)
        if tag is None or tag.budget_id != budget_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tag {tag_id} not found",
            )
    await tag_repo.set_category_tags(category_id, body.tag_ids)
    tags_map = await tag_repo.get_tags_for_categories([category_id])
    return [TagOutSimple.model_validate(t) for t in tags_map.get(category_id, [])]


@router.put("/{budget_id}/payees/{payee_id}/tags", response_model=list[TagOutSimple])
async def set_payee_tags(
    budget_id: BudgetAccess,
    payee_id: PayeeAccess,
    body: SetTagsRequest,
    current_user: CurrentUser,
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
) -> list[TagOutSimple]:
    for tag_id in body.tag_ids:
        tag = await tag_repo.get(tag_id)
        if tag is None or tag.budget_id != budget_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tag {tag_id} not found",
            )
    await tag_repo.set_payee_tags(payee_id, body.tag_ids)
    tags_map = await tag_repo.get_tags_for_payees([payee_id])
    return [TagOutSimple.model_validate(t) for t in tags_map.get(payee_id, [])]


@router.post("/{budget_id}/payees/{payee_id}/tags/add", response_model=list[TagOutSimple])
async def add_payee_tags(
    budget_id: BudgetAccess,
    payee_id: PayeeAccess,
    body: SetTagsRequest,
    current_user: CurrentUser,
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
) -> list[TagOutSimple]:
    """Add tags to a payee without removing existing ones (additive)."""
    for tag_id in body.tag_ids:
        tag = await tag_repo.get(tag_id)
        if tag is None or tag.budget_id != budget_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tag {tag_id} not found",
            )
        await tag_repo.add_payee_tag(payee_id, tag_id)
    tags_map = await tag_repo.get_tags_for_payees([payee_id])
    return [TagOutSimple.model_validate(t) for t in tags_map.get(payee_id, [])]
