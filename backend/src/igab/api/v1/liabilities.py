import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from igab.api.v1.schemas.category import CategoryResponse
from igab.api.v1.schemas.liability import (
    AmortizationMonthOut,
    AmortizationResponse,
    BalancePointOut,
    LiabilityBalanceSnapshotCreate,
    LiabilityBalanceSnapshotOut,
    LiabilityCreate,
    LiabilityOut,
    LiabilityUpdate,
    LinkLiabilityRequest,
    PromoProjectionOut,
)
from igab.db.models import Liability
from igab.dependencies import (
    BudgetAccess,
    CurrentUser,
    get_account_repo,
    get_category_repo,
    get_liability_repo,
    get_liability_service,
)
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.liability_repo import LiabilityRepository
from igab.services.amortization import AmortizationResult, amortization_schedule, quantize_cents
from igab.services.liability_service import LiabilityService
from igab.utils.clock import today_utc

router = APIRouter()


async def _get_owned_liability(
    liability_repo: LiabilityRepository, budget_id: uuid.UUID, liability_id: uuid.UUID
) -> Liability:
    liability = await liability_repo.get(liability_id)
    if liability is None or liability.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Liability not found")
    return liability


async def _validate_linked_account(
    account_repo: AccountRepository,
    liability_repo: LiabilityRepository,
    budget_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    exclude_liability_id: uuid.UUID | None = None,
) -> None:
    account = await account_repo.get(account_id)
    if account is None or account.budget_id != budget_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Linked account not found"
        )
    existing = await liability_repo.get_by_linked_account(account_id)
    if existing is not None and existing.id != exclude_liability_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That account is already linked to another liability",
        )


async def _liability_out(
    liability: Liability,
    liability_service: LiabilityService,
    category_repo: CategoryRepository,
) -> LiabilityOut:
    status_ = await liability_service.get_status(liability)
    linked_category = await category_repo.get_by_linked_liability(liability.id)

    # The term the contract implies, replayed from origination. If the
    # minimum payment can't amortize the ORIGINAL principal, the entered
    # payment is almost certainly escrow-inclusive vs P&I (or vice versa) —
    # surfaced so the UI can say so instead of a bare "won't pay off".
    implied_term_months: int | None = None
    implied_never_pays_off: bool | None = None
    if liability.origination_date is not None and liability.original_principal is not None:
        implied = amortization_schedule(
            liability.original_principal,
            liability.interest_rate,
            liability.minimum_payment,
            liability.origination_date,
        )
        implied_never_pays_off = implied.never_pays_off
        if not implied.never_pays_off:
            implied_term_months = len(implied.schedule)

    return LiabilityOut(
        id=liability.id,
        budget_id=liability.budget_id,
        name=liability.name,
        liability_type=liability.liability_type,
        mode="managed" if liability.linked_account_id is not None else "unmanaged",
        linked_account_id=liability.linked_account_id,
        linked_category_id=linked_category.id if linked_category else None,
        current_balance=status_.current_balance,
        balance_source=status_.balance_source,
        interest_rate=liability.interest_rate,
        minimum_payment=liability.minimum_payment,
        origination_date=liability.origination_date,
        original_principal=liability.original_principal,
        monthly_interest_now=quantize_cents(
            status_.current_balance * liability.interest_rate / Decimal("1200")
        ),
        average_recent_payment=status_.live.average_payment if status_.live else None,
        implied_term_months=implied_term_months,
        implied_never_pays_off=implied_never_pays_off,
        promo_end_date=liability.promo_end_date,
        promo_deferred_interest=liability.promo_deferred_interest,
        term_months=liability.term_months,
        promo_projection=(
            PromoProjectionOut(
                months_until_promo_end=status_.promo.months_until_promo_end,
                balance_at_promo_end_minimum=status_.promo.balance_at_promo_end_minimum,
                balance_at_promo_end_live=status_.promo.balance_at_promo_end_live,
                clears_before_promo=status_.promo.clears_before_promo,
                deferred_interest_estimate=status_.promo.deferred_interest_estimate,
            )
            if status_.promo is not None
            else None
        ),
        baseline_payoff_date=status_.baseline.payoff_date,
        baseline_never_pays_off=status_.baseline.never_pays_off,
        live_payoff_date=status_.live.payoff_date if status_.live else None,
        live_never_pays_off=status_.live.never_pays_off if status_.live else False,
        has_live_projection=status_.live is not None,
        created_at=liability.created_at,
        updated_at=liability.updated_at,
    )


@router.get("/{budget_id}/liabilities", response_model=list[LiabilityOut])
async def list_liabilities(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    liability_repo: Annotated[LiabilityRepository, Depends(get_liability_repo)],
    liability_service: Annotated[LiabilityService, Depends(get_liability_service)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> list[LiabilityOut]:
    liabilities = await liability_repo.get_all(budget_id)
    return [await _liability_out(item, liability_service, category_repo) for item in liabilities]


@router.post(
    "/{budget_id}/liabilities", response_model=LiabilityOut, status_code=status.HTTP_201_CREATED
)
async def create_liability(
    budget_id: BudgetAccess,
    body: LiabilityCreate,
    current_user: CurrentUser,
    liability_repo: Annotated[LiabilityRepository, Depends(get_liability_repo)],
    liability_service: Annotated[LiabilityService, Depends(get_liability_service)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> LiabilityOut:
    if body.linked_account_id is not None and body.manual_balance is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A liability is managed (linked) or unmanaged (manual balance), not both",
        )
    if body.linked_account_id is not None:
        await _validate_linked_account(
            account_repo, liability_repo, budget_id, body.linked_account_id
        )

    liability = await liability_repo.create(
        budget_id=budget_id,
        name=body.name,
        liability_type=body.liability_type,
        linked_account_id=body.linked_account_id,
        manual_balance=body.manual_balance,
        interest_rate=body.interest_rate,
        minimum_payment=body.minimum_payment,
        origination_date=body.origination_date,
        original_principal=body.original_principal,
        promo_end_date=body.promo_end_date,
        promo_deferred_interest=body.promo_deferred_interest,
        term_months=body.term_months,
    )
    if liability.linked_account_id is None and body.manual_balance is not None:
        # Seed the snapshot trail so history starts at creation
        await liability_repo.upsert_snapshot(
            liability.id, today_utc(), Decimal(body.manual_balance), source="initial"
        )
    return await _liability_out(liability, liability_service, category_repo)


@router.patch("/{budget_id}/liabilities/{liability_id}", response_model=LiabilityOut)
async def update_liability(
    budget_id: BudgetAccess,
    liability_id: uuid.UUID,
    body: LiabilityUpdate,
    current_user: CurrentUser,
    liability_repo: Annotated[LiabilityRepository, Depends(get_liability_repo)],
    liability_service: Annotated[LiabilityService, Depends(get_liability_service)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> LiabilityOut:
    liability = await _get_owned_liability(liability_repo, budget_id, liability_id)
    # exclude_unset (not exclude_none): PATCHing linked_account_id to null is
    # exactly how a liability switches from managed to unmanaged
    changes = body.model_dump(exclude_unset=True)

    new_account_id = changes.get("linked_account_id", liability.linked_account_id)
    if new_account_id is not None and "linked_account_id" in changes:
        await _validate_linked_account(
            account_repo,
            liability_repo,
            budget_id,
            new_account_id,
            exclude_liability_id=liability.id,
        )
    if new_account_id is not None and changes.get("manual_balance") is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A managed liability's balance comes from its account — unlink it first",
        )

    liability = await liability_repo.update(liability.id, **changes)
    return await _liability_out(liability, liability_service, category_repo)


@router.delete("/{budget_id}/liabilities/{liability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_liability(
    budget_id: BudgetAccess,
    liability_id: uuid.UUID,
    current_user: CurrentUser,
    liability_repo: Annotated[LiabilityRepository, Depends(get_liability_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> None:
    liability = await _get_owned_liability(liability_repo, budget_id, liability_id)
    linked_category = await category_repo.get_by_linked_liability(liability.id)
    if linked_category is not None:
        await category_repo.update(linked_category.id, linked_liability_id=None)
    await liability_repo.soft_delete(liability.id)


@router.post(
    "/{budget_id}/liabilities/{liability_id}/balance-snapshots",
    response_model=LiabilityBalanceSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_balance_snapshot(
    budget_id: BudgetAccess,
    liability_id: uuid.UUID,
    body: LiabilityBalanceSnapshotCreate,
    current_user: CurrentUser,
    liability_repo: Annotated[LiabilityRepository, Depends(get_liability_repo)],
) -> LiabilityBalanceSnapshotOut:
    liability = await _get_owned_liability(liability_repo, budget_id, liability_id)
    if liability.linked_account_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Snapshots are for unmanaged liabilities — this one tracks an account",
        )
    snapshot_date = body.date or today_utc()
    snapshot = await liability_repo.upsert_snapshot(
        liability.id, snapshot_date, Decimal(body.balance), source="manual"
    )
    # Update manual_balance if this is the newest snapshot (don't regress)
    all_snaps = await liability_repo.get_snapshots(liability.id)
    newest = max(all_snaps, key=lambda s: s.date) if all_snaps else None
    if newest is not None and newest.id == snapshot.id:
        await liability_repo.update(liability.id, manual_balance=snapshot.balance)
    return LiabilityBalanceSnapshotOut(
        id=snapshot.id,
        liability_id=snapshot.liability_id,
        date=snapshot.date,
        balance=snapshot.balance,
        source=snapshot.source,
    )


@router.get(
    "/{budget_id}/liabilities/{liability_id}/amortization", response_model=AmortizationResponse
)
async def get_amortization(
    budget_id: BudgetAccess,
    liability_id: uuid.UUID,
    current_user: CurrentUser,
    liability_repo: Annotated[LiabilityRepository, Depends(get_liability_repo)],
    liability_service: Annotated[LiabilityService, Depends(get_liability_service)],
    extra_payment: Decimal = Query(default=Decimal("0")),
    from_: Literal["now", "origination"] = Query(default="now", alias="from"),
) -> AmortizationResponse:
    liability = await _get_owned_liability(liability_repo, budget_id, liability_id)
    status_ = await liability_service.get_status(liability)
    baseline = status_.baseline
    extra_sched: AmortizationResult | None = None
    if extra_payment > 0:
        extra_sched = amortization_schedule(
            status_.current_balance,
            liability.interest_rate,
            liability.minimum_payment + extra_payment,
            today_utc(),
        )

    history: list[BalancePointOut] = []
    if from_ == "origination":
        for point_date, balance in await liability_service.get_balance_history(liability):
            history.append(BalancePointOut(date=point_date, balance=balance))

    return AmortizationResponse(
        current_balance=status_.current_balance,
        baseline_schedule=[
            AmortizationMonthOut(
                month_index=m.month_index,
                date=m.date,
                payment=m.payment,
                principal_paid=m.principal_paid,
                interest_paid=m.interest_paid,
                balance=m.balance,
            )
            for m in baseline.schedule
        ],
        baseline_payoff_date=baseline.payoff_date,
        baseline_never_pays_off=baseline.never_pays_off,
        baseline_total_interest=baseline.total_interest,
        extra_payment=extra_payment if extra_payment > 0 else None,
        extra_schedule=(
            [
                AmortizationMonthOut(
                    month_index=m.month_index,
                    date=m.date,
                    payment=m.payment,
                    principal_paid=m.principal_paid,
                    interest_paid=m.interest_paid,
                    balance=m.balance,
                )
                for m in extra_sched.schedule
            ]
            if extra_sched
            else None
        ),
        extra_payoff_date=extra_sched.payoff_date if extra_sched else None,
        extra_never_pays_off=extra_sched.never_pays_off if extra_sched else False,
        extra_total_interest=extra_sched.total_interest if extra_sched else None,
        live_payoff_date=status_.live.payoff_date if status_.live else None,
        live_never_pays_off=status_.live.never_pays_off if status_.live else False,
        live_average_payment=status_.live.average_payment if status_.live else None,
        history=history,
    )


@router.put("/{budget_id}/categories/{category_id}/link-liability", response_model=CategoryResponse)
async def link_category_to_liability(
    budget_id: BudgetAccess,
    category_id: uuid.UUID,
    body: LinkLiabilityRequest,
    current_user: CurrentUser,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    liability_repo: Annotated[LiabilityRepository, Depends(get_liability_repo)],
) -> CategoryResponse:
    category = await category_repo.get(category_id)
    if category is None or category.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    if body.liability_id is None:
        await category_repo.update(category.id, linked_liability_id=None)
    else:
        if category.linked_account_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This category is already linked to an account — a category "
                "can track an account or a liability, not both",
            )
        liability = await _get_owned_liability(liability_repo, budget_id, body.liability_id)
        previous = await category_repo.get_by_linked_liability(liability.id)
        if previous is not None and previous.id != category.id:
            await category_repo.update(previous.id, linked_liability_id=None)
        await category_repo.update(category.id, linked_liability_id=liability.id)

    with_tags = await category_repo.get_with_tags(category.id)
    return CategoryResponse.model_validate(with_tags)
