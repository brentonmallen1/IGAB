import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from igab.api.v1.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from igab.dependencies import (
    AccountAccess,
    BudgetAccess,
    CurrentUser,
    SessionDep,
    get_account_repo,
    get_transaction_matching_service,
    get_transaction_service,
)
from igab.domain.exceptions import DuplicateError, NotFoundError
from igab.repositories.account_repo import AccountRepository, LiabilityDisposition
from igab.services.account_hygiene import AccountHygieneService
from igab.services.account_type_service import apply_type, resolve_type
from igab.services.liability_service import (
    LIABILITY_CLASSIFICATION,
    ensure_for_account,
    release_for_account,
)
from igab.services.transaction_matching_service import TransactionMatchingService
from igab.services.transaction_service import TransactionService

router = APIRouter()


@router.get("/{budget_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    include_closed: bool = False,
) -> list[AccountResponse]:
    accounts = await account_repo.get_all(budget_id, include_closed=include_closed)
    result = []
    for acc in accounts:
        balance = await account_repo.get_balance(acc.id)
        cleared = await account_repo.get_cleared_balance(acc.id)
        uncategorized = await account_repo.get_uncategorized_count(acc.id)
        resp = AccountResponse.model_validate(acc)
        resp.balance = balance
        resp.cleared_balance = cleared
        resp.uncleared_balance = balance - cleared
        resp.uncategorized_count = uncategorized
        result.append(resp)
    return result


class HygieneFindingResponse(BaseModel):
    kind: str
    title: str
    detail: str
    action: str
    account_ids: list[uuid.UUID] = []
    transaction_count: int = 0


class HygieneReportResponse(BaseModel):
    findings: list[HygieneFindingResponse]
    clean: bool


@router.get("/{budget_id}/accounts/hygiene", response_model=HygieneReportResponse)
async def account_hygiene(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: SessionDep,
) -> HygieneReportResponse:
    """Things about this budget's accounts that are probably wrong.

    Separate from `/integrity`, which reports invariant violations. Everything
    here is a judgement call — a dormant account, a suspicious type — and a
    clean integrity run has to keep meaning "the arithmetic is sound".

    Declared above `/accounts/{account_id}` is unnecessary (the prefixes
    differ) but the ordering is kept obvious anyway.
    """
    report = await AccountHygieneService(session).run(budget_id)
    return HygieneReportResponse(
        findings=[HygieneFindingResponse(**vars(f)) for f in report.findings],
        clean=report.clean,
    )


class RepairTransfersResponse(BaseModel):
    #: Pairs linked. Each is two rows that already existed.
    linked: int
    #: Legs with more than one possible partner — left alone on purpose, for a
    #: person to answer in the register's picker.
    ambiguous: int
    #: Legs with no candidate at all: the other side was never imported.
    remaining: int


@router.post("/{budget_id}/accounts/hygiene/repair-transfers")
async def repair_transfers(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    date_tolerance_days: int = Query(0, ge=0, le=14),
) -> RepairTransfersResponse:
    """Link the unpaired transfer legs whose partner is unmistakable.

    Repairs history the fixed importer can't reach. It writes no money and
    creates no rows — only `transfer_id` on pairs that already exist — and it
    is idempotent, so a second run links nothing. Anything ambiguous is left
    for the register's picker rather than guessed at.
    """
    return RepairTransfersResponse(
        **await txn_service.repair_transfers(budget_id, date_tolerance_days=date_tolerance_days)
    )


class RepairTrackingCategoriesResponse(BaseModel):
    #: Rows whose category was removed. Zero means the budget was clean.
    stripped: int


@router.post("/{budget_id}/accounts/hygiene/repair-tracking-categories")
async def repair_tracking_categories(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> RepairTrackingCategoriesResponse:
    """Strip categories from rows on off-budget accounts.

    Those categories count nowhere — the budget's activity sums exclude
    off-budget rows — so this moves no money; it makes the register agree
    with the budget. One undoable batch; idempotent.
    """
    return RepairTrackingCategoriesResponse(
        **await txn_service.repair_tracking_categories(budget_id)
    )


@router.post(
    "/{budget_id}/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED
)
async def create_account(
    budget_id: BudgetAccess,
    body: AccountCreate,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> AccountResponse:
    try:
        type_row = await resolve_type(account_repo.session, budget_id, body.account_type)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    try:
        acc = await account_repo.create(
            budget_id=budget_id,
            name=body.name,
            note=body.note,
            sort_order=body.sort_order,
            **apply_type(type_row, body.on_budget),
        )
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    # A liability-classified account gets its companion here, not on first
    # visit to the page: every consumer downstream may assume the row exists.
    await ensure_for_account(account_repo.session, acc)

    resp = AccountResponse.model_validate(acc)
    resp.balance = await account_repo.get_balance(acc.id)
    return resp


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: AccountAccess,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> AccountResponse:
    try:
        acc = await account_repo.get_or_raise(account_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    resp = AccountResponse.model_validate(acc)
    balance = await account_repo.get_balance(acc.id)
    cleared = await account_repo.get_cleared_balance(acc.id)
    resp.balance = balance
    resp.cleared_balance = cleared
    resp.uncleared_balance = balance - cleared
    resp.uncategorized_count = await account_repo.get_uncategorized_count(acc.id)
    return resp


@router.patch("/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: AccountAccess,
    body: AccountUpdate,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> AccountResponse:
    # exclude_unset (not exclude_none): fields the client omitted stay
    # untouched, while an explicit null still clears the one nullable field
    # (note); null on any non-nullable field is dropped, not written.
    changes = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k == "note"
    }
    try:
        if changes.get("account_type") is not None:
            existing = await account_repo.get_or_raise(account_id)
            type_row = await resolve_type(
                account_repo.session, existing.budget_id, changes["account_type"]
            )
            # Retyping re-derives the mirrors; on_budget only changes when the
            # client asked for it (the type default is a creation-time hint).
            changes.update(
                account_type_id=type_row.id,
                account_type=type_row.key,
                classification=type_row.classification,
            )
        acc = await account_repo.update(account_id, **changes)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    # Retyping can cross the asset/liability line in either direction, and the
    # companion has to follow — an account that became a loan needs one, and
    # one that stopped being a loan should not keep drawing a debt balance
    # from a ledger that no longer represents debt.
    if changes.get("account_type") is not None:
        if acc.classification == LIABILITY_CLASSIFICATION:
            await ensure_for_account(account_repo.session, acc)
        else:
            await release_for_account(account_repo.session, acc)

    resp = AccountResponse.model_validate(acc)
    resp.balance = await account_repo.get_balance(acc.id)
    return resp


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: AccountAccess,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    #: What becomes of the debt this account tracked. Defaults to keeping it —
    #: deleting an account is not a statement that a mortgage was repaid, and
    #: the non-destructive branch is the one that should happen by accident.
    liability: LiabilityDisposition = Query(default="keep"),
) -> None:
    try:
        await account_repo.soft_delete(account_id, liability_disposition=liability)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


class ScanDuplicatesResponse(BaseModel):
    created: int


@router.post("/accounts/{account_id}/scan-duplicates", response_model=ScanDuplicatesResponse)
async def scan_duplicates(
    account_id: AccountAccess,
    current_user: CurrentUser,
    matching_service: Annotated[
        TransactionMatchingService, Depends(get_transaction_matching_service)
    ],
) -> ScanDuplicatesResponse:
    created = await matching_service.scan_for_duplicates(account_id)
    return ScanDuplicatesResponse(created=created)
