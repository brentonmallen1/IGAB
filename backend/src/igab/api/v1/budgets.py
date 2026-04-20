import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Budget
from igab.db.session import get_session
from igab.dependencies import (
    CurrentUser,
    get_account_repo,
    get_assignment_repo,
    get_category_group_repo,
    get_category_repo,
    get_payee_repo,
    get_transaction_repo,
    get_transaction_service,
)
from igab.integrations.ynab.importer import YNABImporter
from igab.integrations.ynab.parser import YNABParser
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.transaction_service import TransactionService

router = APIRouter()


class BudgetCreate(BaseModel):
    name: str
    currency_code: str = "USD"


class BudgetUpdate(BaseModel):
    name: str | None = None
    currency_code: str | None = None


class BudgetResponse(BaseModel):
    id: uuid.UUID
    name: str
    currency_code: str

    model_config = {"from_attributes": True}


class YNABImportResult(BaseModel):
    accounts: int
    category_groups: int
    categories: int
    transactions: int
    skipped: int
    assignments: int
    errors: list[str]


class YNABImportBudgetResponse(BaseModel):
    budget: BudgetResponse
    import_result: YNABImportResult


@router.post(
    "/budgets/import-ynab",
    response_model=YNABImportBudgetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_ynab_as_budget(
    current_user: CurrentUser,
    name: Annotated[str, Form()],
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    account_repo: AccountRepository = Depends(get_account_repo),
    category_group_repo: CategoryGroupRepository = Depends(get_category_group_repo),
    category_repo: CategoryRepository = Depends(get_category_repo),
    payee_repo: PayeeRepository = Depends(get_payee_repo),
    transaction_repo: TransactionRepository = Depends(get_transaction_repo),
    assignment_repo: BudgetAssignmentRepository = Depends(get_assignment_repo),
    txn_service: TransactionService = Depends(get_transaction_service),
) -> YNABImportBudgetResponse:
    # Create the budget first
    budget = Budget(user_id=current_user.id, name=name.strip(), currency_code="USD")
    session.add(budget)
    await session.flush()
    await session.refresh(budget)

    # Parse the ZIP
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        parser = YNABParser()
        try:
            ynab_budget = parser.parse_zip(tmp_path)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

        importer = YNABImporter(
            session=session,
            budget_id=budget.id,
            account_repo=account_repo,
            category_group_repo=category_group_repo,
            category_repo=category_repo,
            payee_repo=payee_repo,
            transaction_repo=transaction_repo,
            transaction_service=txn_service,
            assignment_repo=assignment_repo,
        )
        result = await importer.import_budget(ynab_budget)
    finally:
        tmp_path.unlink(missing_ok=True)

    return YNABImportBudgetResponse(
        budget=BudgetResponse.model_validate(budget),
        import_result=YNABImportResult(
            accounts=result.accounts_imported,
            category_groups=result.category_groups_imported,
            categories=result.categories_imported,
            transactions=result.transactions_imported,
            skipped=result.transactions_skipped,
            assignments=result.assignments_imported,
            errors=result.errors,
        ),
    )


@router.get("/budgets", response_model=list[BudgetResponse])
async def list_budgets(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[BudgetResponse]:
    result = await session.execute(
        select(Budget).where(
            Budget.user_id == current_user.id,
            Budget.is_deleted == False,  # noqa: E712
        )
    )
    budgets = result.scalars().all()
    return [BudgetResponse.model_validate(b) for b in budgets]


@router.post("/budgets", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    body: BudgetCreate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BudgetResponse:
    budget = Budget(
        user_id=current_user.id,
        name=body.name,
        currency_code=body.currency_code,
    )
    session.add(budget)
    await session.flush()
    await session.refresh(budget)

    # Create default system category groups
    from igab.db.models import CategoryGroup

    for i, group_name in enumerate(["Income", "Bills", "Everyday Expenses", "Savings Goals"]):
        session.add(
            CategoryGroup(
                budget_id=budget.id,
                name=group_name,
                sort_order=i,
                is_system=(group_name == "Income"),
            )
        )
    await session.flush()
    return BudgetResponse.model_validate(budget)


@router.get("/budgets/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BudgetResponse:
    result = await session.execute(
        select(Budget).where(
            Budget.id == budget_id,
            Budget.user_id == current_user.id,
            Budget.is_deleted == False,  # noqa: E712
        )
    )
    budget = result.scalar_one_or_none()
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return BudgetResponse.model_validate(budget)


@router.patch("/budgets/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: uuid.UUID,
    body: BudgetUpdate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BudgetResponse:
    result = await session.execute(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == current_user.id)
    )
    budget = result.scalar_one_or_none()
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    if body.name:
        budget.name = body.name
    if body.currency_code:
        budget.currency_code = body.currency_code
    await session.flush()
    return BudgetResponse.model_validate(budget)


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    result = await session.execute(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == current_user.id)
    )
    budget = result.scalar_one_or_none()
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    budget.is_deleted = True
    await session.flush()
