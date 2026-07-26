import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from igab.api.v1.schemas.category import CategoryResponse
from igab.api.v1.schemas.debt import (
    AmortizationMonthOut,
    AmortizationResponse,
    BalancePointOut,
    DebtBalanceSnapshotCreate,
    DebtBalanceSnapshotOut,
    DebtCreate,
    DebtOut,
    DebtUpdate,
    LinkDebtRequest,
)
from igab.db.models import Debt
from igab.dependencies import (
    BudgetAccess,
    CurrentUser,
    get_account_repo,
    get_category_repo,
    get_debt_repo,
    get_debt_service,
)
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.debt_repo import DebtRepository
from igab.services.debt_math import AmortizationResult, amortization_schedule
from igab.services.debt_service import DebtService
from igab.utils.clock import today_utc

router = APIRouter()


async def _get_owned_debt(
    debt_repo: DebtRepository, budget_id: uuid.UUID, debt_id: uuid.UUID
) -> Debt:
    debt = await debt_repo.get(debt_id)
    if debt is None or debt.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debt not found")
    return debt


async def _validate_linked_account(
    account_repo: AccountRepository,
    debt_repo: DebtRepository,
    budget_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    exclude_debt_id: uuid.UUID | None = None,
) -> None:
    account = await account_repo.get(account_id)
    if account is None or account.budget_id != budget_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Linked account not found"
        )
    existing = await debt_repo.get_by_linked_account(account_id)
    if existing is not None and existing.id != exclude_debt_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That account is already linked to another debt",
        )


async def _debt_out(
    debt: Debt, debt_service: DebtService, category_repo: CategoryRepository
) -> DebtOut:
    status_ = await debt_service.get_status(debt)
    linked_category = await category_repo.get_by_linked_debt(debt.id)
    return DebtOut(
        id=debt.id,
        budget_id=debt.budget_id,
        name=debt.name,
        debt_type=debt.debt_type,
        mode="managed" if debt.linked_account_id is not None else "unmanaged",
        linked_account_id=debt.linked_account_id,
        linked_category_id=linked_category.id if linked_category else None,
        current_balance=status_.current_balance,
        interest_rate=debt.interest_rate,
        minimum_payment=debt.minimum_payment,
        compounding=debt.compounding,
        origination_date=debt.origination_date,
        original_principal=debt.original_principal,
        baseline_payoff_date=status_.baseline.payoff_date,
        baseline_never_pays_off=status_.baseline.never_pays_off,
        live_payoff_date=status_.live.payoff_date if status_.live else None,
        live_never_pays_off=status_.live.never_pays_off if status_.live else False,
        has_live_projection=status_.live is not None,
        created_at=debt.created_at,
        updated_at=debt.updated_at,
    )


@router.get("/{budget_id}/debts", response_model=list[DebtOut])
async def list_debts(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    debt_repo: Annotated[DebtRepository, Depends(get_debt_repo)],
    debt_service: Annotated[DebtService, Depends(get_debt_service)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> list[DebtOut]:
    debts = await debt_repo.get_all(budget_id)
    return [await _debt_out(d, debt_service, category_repo) for d in debts]


@router.post("/{budget_id}/debts", response_model=DebtOut, status_code=status.HTTP_201_CREATED)
async def create_debt(
    budget_id: BudgetAccess,
    body: DebtCreate,
    current_user: CurrentUser,
    debt_repo: Annotated[DebtRepository, Depends(get_debt_repo)],
    debt_service: Annotated[DebtService, Depends(get_debt_service)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> DebtOut:
    if body.linked_account_id is not None and body.manual_balance is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A debt is managed (linked account) or unmanaged (manual balance), not both",
        )
    if body.linked_account_id is not None:
        await _validate_linked_account(account_repo, debt_repo, budget_id, body.linked_account_id)

    debt = await debt_repo.create(
        budget_id=budget_id,
        name=body.name,
        debt_type=body.debt_type,
        linked_account_id=body.linked_account_id,
        manual_balance=body.manual_balance,
        interest_rate=body.interest_rate,
        minimum_payment=body.minimum_payment,
        compounding=body.compounding,
        origination_date=body.origination_date,
        original_principal=body.original_principal,
    )
    if debt.linked_account_id is None and body.manual_balance is not None:
        # Seed the snapshot trail so history starts at creation
        await debt_repo.upsert_snapshot(
            debt.id, today_utc(), Decimal(body.manual_balance), source="initial"
        )
    return await _debt_out(debt, debt_service, category_repo)


@router.patch("/{budget_id}/debts/{debt_id}", response_model=DebtOut)
async def update_debt(
    budget_id: BudgetAccess,
    debt_id: uuid.UUID,
    body: DebtUpdate,
    current_user: CurrentUser,
    debt_repo: Annotated[DebtRepository, Depends(get_debt_repo)],
    debt_service: Annotated[DebtService, Depends(get_debt_service)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> DebtOut:
    debt = await _get_owned_debt(debt_repo, budget_id, debt_id)
    # exclude_unset (not exclude_none): PATCHing linked_account_id to null is
    # exactly how a debt switches from managed to unmanaged
    changes = body.model_dump(exclude_unset=True)

    new_account_id = changes.get("linked_account_id", debt.linked_account_id)
    if new_account_id is not None and "linked_account_id" in changes:
        await _validate_linked_account(
            account_repo, debt_repo, budget_id, new_account_id, exclude_debt_id=debt.id
        )
    if new_account_id is not None and changes.get("manual_balance") is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A managed debt's balance comes from its account — unlink it first",
        )

    debt = await debt_repo.update(debt.id, **changes)
    return await _debt_out(debt, debt_service, category_repo)


@router.delete("/{budget_id}/debts/{debt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_debt(
    budget_id: BudgetAccess,
    debt_id: uuid.UUID,
    current_user: CurrentUser,
    debt_repo: Annotated[DebtRepository, Depends(get_debt_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> None:
    debt = await _get_owned_debt(debt_repo, budget_id, debt_id)
    linked_category = await category_repo.get_by_linked_debt(debt.id)
    if linked_category is not None:
        await category_repo.update(linked_category.id, linked_debt_id=None)
    await debt_repo.soft_delete(debt.id)


@router.post(
    "/{budget_id}/debts/{debt_id}/balance-snapshots",
    response_model=DebtBalanceSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_balance_snapshot(
    budget_id: BudgetAccess,
    debt_id: uuid.UUID,
    body: DebtBalanceSnapshotCreate,
    current_user: CurrentUser,
    debt_repo: Annotated[DebtRepository, Depends(get_debt_repo)],
) -> DebtBalanceSnapshotOut:
    debt = await _get_owned_debt(debt_repo, budget_id, debt_id)
    if debt.linked_account_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A managed debt's balance comes from its account ledger",
        )
    snapshot_date = body.date or today_utc()
    snapshot = await debt_repo.upsert_snapshot(debt.id, snapshot_date, Decimal(body.balance))
    # Keep the resolved balance current when this is the newest information
    existing = await debt_repo.get_snapshots(debt.id)
    if snapshot_date >= max(s.date for s in existing):
        await debt_repo.update(debt.id, manual_balance=Decimal(body.balance))
    return DebtBalanceSnapshotOut.model_validate(snapshot)


@router.get("/{budget_id}/debts/{debt_id}/amortization", response_model=AmortizationResponse)
async def get_amortization(
    budget_id: BudgetAccess,
    debt_id: uuid.UUID,
    current_user: CurrentUser,
    debt_repo: Annotated[DebtRepository, Depends(get_debt_repo)],
    debt_service: Annotated[DebtService, Depends(get_debt_service)],
    extra_payment: Decimal = Query(default=Decimal("0"), ge=0),
    from_: Literal["now", "origination"] = Query(default="now", alias="from"),
) -> AmortizationResponse:
    debt = await _get_owned_debt(debt_repo, budget_id, debt_id)
    status_ = await debt_service.get_status(debt)

    def months_out(result: AmortizationResult) -> list[AmortizationMonthOut]:
        return [
            AmortizationMonthOut(
                month_index=m.month_index,
                date=m.date,
                payment=m.payment,
                principal_paid=m.principal_paid,
                interest_paid=m.interest_paid,
                balance=m.balance,
            )
            for m in result.schedule
        ]

    extra_result: AmortizationResult | None = None
    if extra_payment > 0:
        extra_result = amortization_schedule(
            status_.current_balance,
            debt.interest_rate,
            debt.minimum_payment + extra_payment,
            today_utc(),
        )

    history: list[BalancePointOut] = []
    if from_ == "origination":
        points = await debt_service.get_balance_history(debt)
        history = [BalancePointOut(date=d, balance=b) for d, b in points]

    return AmortizationResponse(
        current_balance=status_.current_balance,
        baseline_schedule=months_out(status_.baseline),
        baseline_payoff_date=status_.baseline.payoff_date,
        baseline_never_pays_off=status_.baseline.never_pays_off,
        baseline_total_interest=status_.baseline.total_interest,
        extra_payment=extra_payment if extra_payment > 0 else None,
        extra_schedule=months_out(extra_result) if extra_result else None,
        extra_payoff_date=extra_result.payoff_date if extra_result else None,
        extra_never_pays_off=extra_result.never_pays_off if extra_result else False,
        extra_total_interest=extra_result.total_interest if extra_result else None,
        live_payoff_date=status_.live.payoff_date if status_.live else None,
        live_never_pays_off=status_.live.never_pays_off if status_.live else False,
        live_average_payment=status_.live.average_payment if status_.live else None,
        history=history,
    )


@router.put("/{budget_id}/categories/{category_id}/link-debt", response_model=CategoryResponse)
async def link_category_debt(
    budget_id: BudgetAccess,
    category_id: uuid.UUID,
    body: LinkDebtRequest,
    current_user: CurrentUser,
    debt_repo: Annotated[DebtRepository, Depends(get_debt_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
) -> CategoryResponse:
    """Link a budget category's outflows to a debt as its payment history.

    A category carries linked_account_id OR linked_debt_id, never both; a
    debt has at most one linked category (relinking moves the link)."""
    category = await category_repo.get(category_id)
    if category is None or category.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    if body.debt_id is None:
        await category_repo.update(category.id, linked_debt_id=None)
    else:
        if category.linked_account_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This category is already linked to an account — a category "
                "can track an account or a debt, not both",
            )
        debt = await _get_owned_debt(debt_repo, budget_id, body.debt_id)
        previous = await category_repo.get_by_linked_debt(debt.id)
        if previous is not None and previous.id != category.id:
            await category_repo.update(previous.id, linked_debt_id=None)
        await category_repo.update(category.id, linked_debt_id=debt.id)

    with_tags = await category_repo.get_with_tags(category.id)
    return CategoryResponse.model_validate(with_tags)
