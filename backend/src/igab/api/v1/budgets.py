import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Canonical result schema lives with the import endpoints — a local copy here
# drifted the moment imports.py gained fields (imports.py has no module-level
# api.v1 imports, so this cannot cycle).
from igab.api.v1.imports import YNABImportResult
from igab.db.models import Budget, BudgetMember
from igab.db.session import get_session
from igab.dependencies import (
    BudgetAccess,
    BudgetOwnerAccess,
    CurrentUser,
    get_account_repo,
    get_assignment_repo,
    get_category_group_repo,
    get_category_repo,
    get_liability_repo,
    get_payee_repo,
    get_reconciliation_repo,
    get_scheduled_transaction_repo,
    get_tag_repo,
    get_target_repo,
    get_transaction_repo,
    get_transaction_service,
)
from igab.integrations.ynab.importer import YNABImporter
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.repositories.tag_repo import TagRepository
from igab.repositories.target_repo import TargetRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.transaction_service import TransactionService

router = APIRouter()


class BudgetCreate(BaseModel):
    name: str
    currency_code: str = "USD"
    number_format: str = "comma_dot"
    date_format: str = "mdy"
    time_format: str = "12h"


class BudgetUpdate(BaseModel):
    name: str | None = None
    currency_code: str | None = None
    number_format: str | None = None
    date_format: str | None = None
    time_format: str | None = None


class BudgetResponse(BaseModel):
    id: uuid.UUID
    name: str
    currency_code: str
    number_format: str
    date_format: str
    time_format: str
    #: The CALLER's role in this budget ('owner' | 'member') — lets the UI
    #: show sharing affordances and "shared with you" hints. None only in
    #: nested contexts that predate membership (e.g. import responses).
    role: str | None = None

    model_config = {"from_attributes": True}


def _grant_owner(session: "AsyncSession", budget_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Every budget-creation path must call this: membership is the
    authorization source of truth, and a budget without an owner row would be
    invisible even to its creator."""
    session.add(BudgetMember(budget_id=budget_id, user_id=user_id, role="owner"))


class YNABImportBudgetResponse(BaseModel):
    budget: BudgetResponse
    import_result: YNABImportResult


@router.post("/budgets/import-ynab/preview")
async def preview_ynab_budget_import(
    current_user: CurrentUser,
    file: UploadFile = File(...),
):
    """Parse a YNAB export without creating anything: account list with
    name-based type suggestions for the mapping step. Budget-less — this
    flow runs BEFORE the budget exists."""
    from igab.api.v1.imports import build_ynab_preview, parse_uploaded_ynab_zip

    ynab_budget = await parse_uploaded_ynab_zip(file)
    return build_ynab_preview(ynab_budget)


@router.post(
    "/budgets/import-ynab",
    response_model=YNABImportBudgetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_ynab_as_budget(
    current_user: CurrentUser,
    name: Annotated[str, Form()],
    file: UploadFile = File(...),
    account_types: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
    account_repo: AccountRepository = Depends(get_account_repo),
    category_group_repo: CategoryGroupRepository = Depends(get_category_group_repo),
    category_repo: CategoryRepository = Depends(get_category_repo),
    payee_repo: PayeeRepository = Depends(get_payee_repo),
    transaction_repo: TransactionRepository = Depends(get_transaction_repo),
    assignment_repo: BudgetAssignmentRepository = Depends(get_assignment_repo),
    txn_service: TransactionService = Depends(get_transaction_service),
) -> YNABImportBudgetResponse:
    from igab.api.v1.imports import (
        parse_account_types_form,
        parse_uploaded_ynab_zip,
        run_ynab_import,
    )

    # Validate the mapping and the zip BEFORE creating the budget so a bad
    # request doesn't leave an empty budget behind.
    type_map, skip_accounts = parse_account_types_form(account_types)
    ynab_budget = await parse_uploaded_ynab_zip(file)

    budget_name = name.strip()
    existing = await session.execute(
        select(Budget).where(Budget.user_id == current_user.id, Budget.name == budget_name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A budget named '{budget_name}' already exists.",
        )

    budget = Budget(user_id=current_user.id, name=budget_name, currency_code="USD")
    session.add(budget)
    await session.flush()
    _grant_owner(session, budget.id, current_user.id)
    await session.refresh(budget)

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
        account_types=type_map,
        skip_accounts=skip_accounts,
    )
    # On failure this raises a 400; get_session rolls back, discarding the
    # budget created above along with every partial row.
    result = await run_ynab_import(importer, ynab_budget)

    return YNABImportBudgetResponse(
        budget=BudgetResponse.model_validate(budget),
        import_result=YNABImportResult(
            accounts=result.accounts_imported,
            category_groups=result.category_groups_imported,
            categories=result.categories_imported,
            transactions=result.transactions_imported,
            skipped=result.transactions_skipped,
            assignments=result.assignments_imported,
            accounts_skipped=result.accounts_skipped,
            transactions_excluded=result.transactions_excluded,
            errors=result.errors,
        ),
    )


class SampleBudgetRequest(BaseModel):
    name: str | None = None


class SampleBudgetCounts(BaseModel):
    accounts: int
    category_groups: int
    categories: int
    payees: int
    tags_linked: int
    targets: int
    transactions: int
    assignments: int
    scheduled: int
    reconciliations: int
    liabilities: int


class SampleBudgetResponse(BaseModel):
    budget: BudgetResponse
    counts: SampleBudgetCounts


@router.post(
    "/budgets/create-sample",
    response_model=SampleBudgetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sample_budget(
    current_user: CurrentUser,
    body: SampleBudgetRequest | None = None,
    session: AsyncSession = Depends(get_session),
    account_repo: AccountRepository = Depends(get_account_repo),
    category_group_repo: CategoryGroupRepository = Depends(get_category_group_repo),
    category_repo: CategoryRepository = Depends(get_category_repo),
    payee_repo: PayeeRepository = Depends(get_payee_repo),
    transaction_repo: TransactionRepository = Depends(get_transaction_repo),
    assignment_repo: BudgetAssignmentRepository = Depends(get_assignment_repo),
    tag_repo: TagRepository = Depends(get_tag_repo),
    target_repo: TargetRepository = Depends(get_target_repo),
    scheduled_repo: ScheduledTransactionRepository = Depends(get_scheduled_transaction_repo),
    reconciliation_repo: ReconciliationRepository = Depends(get_reconciliation_repo),
    liability_repo: LiabilityRepository = Depends(get_liability_repo),
) -> SampleBudgetResponse:
    """Create a budget pre-filled with 12 months of curated demo data.

    A one-click throwaway: on a name collision the name is auto-suffixed
    ("Sample Budget 2", …) instead of erroring.
    """
    from igab.repositories.tag_repo import seed_system_tags
    from igab.sample_budget.generator import SampleBudgetGenerator

    base_name = (body.name.strip() if body and body.name else "") or "Sample Budget"
    existing = await session.execute(select(Budget.name).where(Budget.user_id == current_user.id))
    taken = {name.lower() for (name,) in existing}
    name = base_name
    suffix = 2
    while name.lower() in taken:
        name = f"{base_name} {suffix}"
        suffix += 1

    budget = Budget(user_id=current_user.id, name=name, currency_code="USD")
    session.add(budget)
    await session.flush()
    _grant_owner(session, budget.id, current_user.id)
    await session.refresh(budget)
    await seed_system_tags(session, budget.id)

    generator = SampleBudgetGenerator(
        session,
        budget.id,
        account_repo=account_repo,
        category_group_repo=category_group_repo,
        category_repo=category_repo,
        payee_repo=payee_repo,
        transaction_repo=transaction_repo,
        assignment_repo=assignment_repo,
        tag_repo=tag_repo,
        target_repo=target_repo,
        scheduled_repo=scheduled_repo,
        reconciliation_repo=reconciliation_repo,
        liability_repo=liability_repo,
    )
    counts = await generator.generate()

    return SampleBudgetResponse(
        budget=BudgetResponse.model_validate(budget),
        counts=SampleBudgetCounts(**vars(counts)),
    )


@router.get("/budgets", response_model=list[BudgetResponse])
async def list_budgets(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[BudgetResponse]:
    result = await session.execute(
        select(Budget, BudgetMember.role)
        .join(BudgetMember, BudgetMember.budget_id == Budget.id)
        .where(BudgetMember.user_id == current_user.id)
        .order_by(Budget.created_at)
    )
    return [
        BudgetResponse.model_validate(b).model_copy(update={"role": role})
        for b, role in result.all()
    ]


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
    _grant_owner(session, budget.id, current_user.id)
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

    # Seed system tags
    from igab.repositories.tag_repo import seed_system_tags

    await seed_system_tags(session, budget.id)

    return BudgetResponse.model_validate(budget)


@router.get("/budgets/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BudgetResponse:
    # BudgetAccess already proved membership — no owner re-check (members see
    # shared budgets; the old Budget.user_id filter would 404 them here).
    result = await session.execute(
        select(Budget, BudgetMember.role)
        .join(BudgetMember, BudgetMember.budget_id == Budget.id)
        .where(Budget.id == budget_id, BudgetMember.user_id == current_user.id)
    )
    budget, role = result.one()
    return BudgetResponse.model_validate(budget).model_copy(update={"role": role})


@router.patch("/budgets/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: BudgetAccess,
    body: BudgetUpdate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BudgetResponse:
    # Member-level operation; BudgetAccess already authorized.
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    if body.name:
        budget.name = body.name
    if body.currency_code:
        budget.currency_code = body.currency_code
    if body.number_format:
        budget.number_format = body.number_format
    if body.date_format:
        budget.date_format = body.date_format
    if body.time_format:
        budget.time_format = body.time_format
    await session.flush()
    return BudgetResponse.model_validate(budget)


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: BudgetOwnerAccess,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Owner-only: deleting a budget destroys every member's view of it."""
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    await session.delete(budget)
    await session.flush()


# ─── Financial integrity ──────────────────────────────────────────────────────


class IntegrityCheckResponse(BaseModel):
    name: str
    description: str
    passed: bool
    problem_count: int
    details: list[str]


class IntegrityReportResponse(BaseModel):
    all_passed: bool
    checks: list[IntegrityCheckResponse]


@router.get("/budgets/{budget_id}/integrity", response_model=IntegrityReportResponse)
async def run_integrity_checks(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IntegrityReportResponse:
    """Run the financial invariant suite against live data: money
    conservation, split/transfer integrity, orphaned matches, stale pendings."""
    from igab.services.integrity_service import IntegrityService

    report = await IntegrityService(session).run(budget_id)
    return IntegrityReportResponse(
        all_passed=report.all_passed,
        checks=[
            IntegrityCheckResponse(
                name=c.name,
                description=c.description,
                passed=c.passed,
                problem_count=c.problem_count,
                details=c.details,
            )
            for c in report.checks
        ],
    )
