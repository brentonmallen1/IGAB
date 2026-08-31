import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from igab.api.route import CommitRoute
from igab.api.v1.schemas.transaction import (
    BudgetTransactionListResponse,
    BulkActionResult,
    BulkApprove,
    BulkCategorize,
    BulkClearedUpdate,
    BulkDelete,
    BulkItemFailure,
    ConvertToSplitRequest,
    DeleteTransactionResult,
    DuplicatePayeeEntry,
    DuplicatePayeeGroup,
    MergeTransactionsRequest,
    NearbyPayeeResponse,
    PayeeCreate,
    PayeeMergeRequest,
    PayeeMergeResult,
    PayeeResponse,
    PayeeUpdate,
    PayeeWithCount,
    PendingReviewCount,
    ReplaceSplitsRequest,
    SimilarTransactionResponse,
    TransactionClassification,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from igab.db.models import Category, Transaction
from igab.dependencies import (
    AccountAccess,
    BudgetAccess,
    CurrentUser,
    PayeeAccess,
    SessionDep,
    TransactionAccess,
    get_account_repo,
    get_ai_job_repo,
    get_change_recorder,
    get_payee_repo,
    get_transaction_repo,
    get_transaction_service,
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
from igab.repositories.account_repo import AccountRepository
from igab.repositories.ai_job_repo import AIJobRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
from igab.services.ownership import require_in_budget
from igab.services.transaction_service import (
    SplitSpec,
    TransactionService,
)
from igab.services.transaction_service import (
    TransactionCreate as SvcTxnCreate,
)
from igab.services.transaction_service import (
    TransactionUpdate as SvcTxnUpdate,
)
from igab.utils.geo import bounding_box, haversine_m

router = APIRouter(route_class=CommitRoute)


# ─── Transactions ─────────────────────────────────────────────────────────────


@router.get("/accounts/{account_id}/transactions", response_model=list[TransactionResponse])
async def list_account_transactions(
    account_id: AccountAccess,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    limit: int = Query(100, le=5000),
    offset: int = 0,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
    cleared: str | None = None,
    exclude_cleared: str | None = None,
    uncategorized: bool = False,
    unapproved: bool = False,
    is_or_mode: bool = False,
    category_ids: str | None = None,
    payee_ids: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    has_attachment: bool | None = None,
    direction: Literal["inflow", "outflow"] | None = None,
    is_transfer: bool | None = None,
    unpaired_transfers: bool = False,
) -> list[TransactionResponse]:
    parsed_cat_ids = [uuid.UUID(x) for x in category_ids.split(",") if x] if category_ids else None
    parsed_pay_ids = [uuid.UUID(x) for x in payee_ids.split(",") if x] if payee_ids else None
    txns = await txn_repo.get_for_account(
        account_id,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
        search=search,
        cleared=cleared,
        exclude_cleared=exclude_cleared,
        uncategorized=uncategorized,
        unapproved=unapproved,
        is_or_mode=is_or_mode,
        category_ids=parsed_cat_ids,
        payee_ids=parsed_pay_ids,
        amount_min=amount_min,
        amount_max=amount_max,
        has_attachment=has_attachment,
        direction=direction,
        is_transfer=is_transfer,
        unpaired_transfers=unpaired_transfers,
    )
    return [TransactionResponse.model_validate(t) for t in txns]


@router.get("/{budget_id}/transactions", response_model=BudgetTransactionListResponse)
async def list_budget_transactions(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
    category_ids: str | None = None,
    payee_ids: str | None = None,
    account_ids: str | None = None,
    scope: Literal["parent", "leaf"] = "parent",
    posted_only: bool = False,
    cash_flow_only: bool = False,
    #: Comma-separated activity classes, so a report drill-down lists exactly
    #: what the chart that opened it counted.
    activity_classes: str | None = Query(None),
    direction: Literal["inflow", "outflow"] | None = None,
    day_of_week: int | None = Query(None, ge=0, le=6),
    cleared: str | None = None,
    exclude_cleared: str | None = None,
    uncategorized: bool = False,
    unapproved: bool = False,
    is_or_mode: bool = False,
    amount_min: float | None = None,
    amount_max: float | None = None,
    has_attachment: bool | None = None,
    is_transfer: bool | None = None,
    #: Transfer legs whose partner never arrived. Not expressible via
    #: `is_transfer`, which tests transfer_id alone — this is what the account
    #: hygiene panel links to.
    unpaired_transfers: bool = False,
    order: Literal["date", "register"] = "date",
    limit: int = Query(200, le=5000),
    offset: int = 0,
    #: Ask for the account's balance as of each returned row. Honoured only
    #: for a listing scoped to exactly ONE account: a running total across
    #: accounts is not a balance of anything.
    running_balance: bool = False,
) -> BudgetTransactionListResponse:
    """Budget-wide transaction listing for report drill-downs and the
    all-accounts register.

    The filter semantics mirror the report aggregates: leaf scope for
    category-keyed drills, parent scope for payee/month drills; posted_only
    and cash_flow_only reproduce the POSTED / CASH_FLOW_ROW predicates.
    cleared/uncategorized/unapproved/amount filters and order="register"
    mirror the per-account listing so the all-accounts register behaves
    identically to a single account's.
    """
    txns, total_count, total_amount = await txn_repo.list_for_budget(
        budget_id,
        start_date=start_date,
        end_date=end_date,
        search=search,
        category_ids=_parse_uuid_list(category_ids),
        payee_ids=_parse_uuid_list(payee_ids),
        account_ids=_parse_uuid_list(account_ids),
        scope=scope,
        posted_only=posted_only,
        cash_flow_only=cash_flow_only,
        activity_classes=_parse_csv(activity_classes),
        direction=direction,
        day_of_week=day_of_week,
        cleared=cleared,
        exclude_cleared=exclude_cleared,
        uncategorized=uncategorized,
        unapproved=unapproved,
        is_or_mode=is_or_mode,
        amount_min=amount_min,
        amount_max=amount_max,
        has_attachment=has_attachment,
        is_transfer=is_transfer,
        unpaired_transfers=unpaired_transfers,
        order=order,
        limit=limit,
        offset=offset,
    )
    accounts = _parse_uuid_list(account_ids)
    running: dict[str, Decimal] = {}
    if running_balance and accounts and len(accounts) == 1:
        # Keyed by row rather than accumulated by the client: the server owns
        # the order the rows are drawn in, and a running total computed in a
        # different order is nonsense that reads as arithmetic. It is a window
        # over the account's whole ledger, so it stays correct under any
        # filter — the figures simply stop differing by the row amounts, the
        # way a filtered bank statement does.
        running = {
            str(row_id): total
            for row_id, total in (
                await txn_repo.running_balances(accounts[0], [t.id for t in txns])
            ).items()
        }
    return BudgetTransactionListResponse(
        transactions=[TransactionResponse.model_validate(t) for t in txns],
        total_count=total_count,
        total_amount=total_amount,
        running_balances=running,
    )


def _parse_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()] or None


def _parse_uuid_list(value: str | None) -> list[uuid.UUID] | None:
    """Parse a comma-separated id list, rejecting malformed entries with a 400.

    Unguarded `uuid.UUID()` turns a client-side id-construction slip into a
    500 from the catch-all handler, which reads as a server fault and tells
    nobody which value was wrong.
    """
    if not value:
        return None
    try:
        return [uuid.UUID(v.strip()) for v in value.split(",") if v.strip()]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Malformed id: {e}"
        ) from e


@router.get(
    "/accounts/{account_id}/transactions/similar",
    response_model=list[SimilarTransactionResponse],
)
async def find_similar_transactions(
    account_id: AccountAccess,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    amount: float = Query(...),
    date: date = Query(...),
    exclude_id: uuid.UUID | None = None,
) -> list[SimilarTransactionResponse]:
    txns = await txn_repo.find_similar_transactions(
        account_id,
        Decimal(str(amount)),
        date,
        exclude_id,
    )
    return [SimilarTransactionResponse.model_validate(t) for t in txns]


@router.post(
    "/{budget_id}/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    budget_id: BudgetAccess,
    body: TransactionCreate,
    current_user: CurrentUser,
    session: SessionDep,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    ai_job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
) -> TransactionResponse:
    # AI provenance is derived from the linked job — never from the client.
    created_via: str | None = None
    ai_job = None
    if body.ai_job_id is not None:
        ai_job = await ai_job_repo.get(body.ai_job_id)
        if ai_job is None or str(ai_job.budget_id) != str(budget_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI job not found")
        created_via = "ai_nl" if ai_job.kind == "nl_parse" else "ai_receipt"

    try:
        if body.splits:
            header = SvcTxnCreate(
                account_id=body.account_id,
                date=body.date,
                amount=body.amount,
                payee_id=body.payee_id,
                payee_name=body.payee_name,
                memo=body.memo,
                cleared=body.cleared,
                approved=body.approved,
                created_via=created_via,
                latitude=body.latitude,
                longitude=body.longitude,
            )
            splits = [
                SvcTxnCreate(
                    account_id=body.account_id,
                    date=body.date,
                    amount=s.amount,
                    payee_id=s.payee_id,
                    payee_name=s.payee_name,
                    category_id=s.category_id,
                    memo=s.memo,
                )
                for s in body.splits
            ]
            txn = await txn_service.create_split(budget_id, header, splits)
        else:
            svc_data = SvcTxnCreate(
                account_id=body.account_id,
                date=body.date,
                amount=body.amount,
                payee_id=body.payee_id,
                payee_name=body.payee_name,
                category_id=body.category_id,
                memo=body.memo,
                cleared=body.cleared,
                approved=body.approved,
                transfer_account_id=body.transfer_account_id,
                created_via=created_via,
                latitude=body.latitude,
                longitude=body.longitude,
            )
            txn = await txn_service.create(budget_id, svc_data)
    except InvariantViolation as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if ai_job is not None and ai_job.transaction_id is None:
        ai_job.transaction_id = txn.id
        session.add(ai_job)
        await session.flush()
    return TransactionResponse.model_validate(txn)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: TransactionAccess,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> TransactionResponse:
    try:
        txn = await txn_repo.get_or_raise(transaction_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


@router.get(
    "/transactions/{transaction_id}/classification",
    response_model=TransactionClassification,
)
async def get_transaction_classification(
    transaction_id: TransactionAccess,
    current_user: CurrentUser,
    session: SessionDep,
) -> TransactionClassification:
    """Why this row counts the way it does in reports.

    Its own endpoint rather than a field on TransactionResponse: the class is
    derived from correlated subqueries over the counterpart account and the
    category's tags, which is cheap for one row and wasteful for a list of a
    thousand. It is asked for when a user opens a transaction and wonders why
    it isn't in their spending — not on every render.
    """
    row = (
        await session.execute(
            # Transaction.id is unused; the class joins chain from it.
            apply_class_joins(
                select(Transaction.id, ACTIVITY_CLASS, ACTIVITY_REASON).where(
                    Transaction.id == transaction_id
                )
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    activity_class = ActivityClass(row[1])
    return TransactionClassification(
        activity_class=activity_class,
        label=CLASS_LABEL[activity_class],
        reason=row[2],
        explanation=explain(row[2]),
    )


@router.get(
    "/transactions/{transaction_id}/transfer-candidates",
    response_model=list[TransactionResponse],
)
async def get_transfer_candidates(
    transaction_id: TransactionAccess,
    account_id: uuid.UUID,
    current_user: CurrentUser,
    budget_id: BudgetAccess,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    date_tolerance_days: int = Query(0, ge=0, le=14),
) -> list[TransactionResponse]:
    """Rows in `account_id` that could be this transaction's missing far leg.

    Feeds the "which one is it?" picker, so it is deliberately broader than
    what the save path auto-links: any live, unlinked, opposite-amount row in
    range, whether or not its payee points back here. A bank-imported far leg
    usually has an ordinary payee — that is exactly the row a user needs
    offered, and exactly the row a blind create would duplicate.
    """
    txn = await txn_repo.get_or_raise(transaction_id)
    account = await account_repo.get(account_id)
    if account is None or str(account.budget_id) != str(budget_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    candidates = await txn_repo.find_transfer_candidates(
        account_id=account_id,
        amount=-txn.amount,
        on_date=txn.date,
        date_tolerance_days=date_tolerance_days,
    )
    return [TransactionResponse.model_validate(c) for c in candidates if c.id != transaction_id]


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: TransactionAccess,
    body: TransactionUpdate,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    budget_id: BudgetAccess,
) -> TransactionResponse:
    try:
        # Only fields the client actually sent: omitted fields stay untouched,
        # explicit nulls clear nullable fields (category/payee/memo).
        svc_data = SvcTxnUpdate(**body.model_dump(exclude_unset=True))
        txn = await txn_service.update(budget_id, transaction_id, svc_data)
    except (NotFoundError, InvariantViolation) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


@router.post("/transactions/{transaction_id}/split", response_model=TransactionResponse)
async def convert_transaction_to_split(
    transaction_id: TransactionAccess,
    body: ConvertToSplitRequest,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    budget_id: BudgetAccess,
) -> TransactionResponse:
    """Split an existing transaction in place (row becomes the parent),
    preserving attachments, AI links, and import/sync identity."""
    try:
        txn = await txn_service.convert_to_split(budget_id, transaction_id, _split_specs(body))
    except (NotFoundError, InvariantViolation) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


def _split_specs(body: ConvertToSplitRequest | ReplaceSplitsRequest) -> list[SplitSpec]:
    return [
        SplitSpec(
            amount=s.amount,
            category_id=s.category_id,
            payee_id=s.payee_id,
            payee_name=s.payee_name,
            memo=s.memo,
            id=s.id,
        )
        for s in body.splits
    ]


@router.get("/transactions/{transaction_id}/splits", response_model=list[TransactionResponse])
async def list_split_lines(
    transaction_id: TransactionAccess,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> list[TransactionResponse]:
    """A split's lines. The register lists parent rows only, so this is how
    a client sees — and then edits — what a split is made of."""
    return [
        TransactionResponse.model_validate(c) for c in await txn_repo.get_splits(transaction_id)
    ]


@router.put("/transactions/{transaction_id}/splits", response_model=list[TransactionResponse])
async def replace_split_lines(
    transaction_id: TransactionAccess,
    body: ReplaceSplitsRequest,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    budget_id: BudgetAccess,
) -> list[TransactionResponse]:
    """Edit a split's lines in place: named lines update, unnamed create,
    missing remove. The parent — its identity, receipts, amount — is untouched."""
    try:
        lines = await txn_service.replace_splits(budget_id, transaction_id, _split_specs(body))
    except (NotFoundError, InvariantViolation) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return [TransactionResponse.model_validate(c) for c in lines]


@router.delete("/transactions/{transaction_id}", response_model=DeleteTransactionResult)
async def delete_transaction(
    transaction_id: TransactionAccess,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    budget_id: BudgetAccess,
) -> DeleteTransactionResult:
    try:
        batch_id = await txn_service.delete(budget_id, transaction_id)
    except (NotFoundError, InvariantViolation) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return DeleteTransactionResult(batch_id=batch_id)


async def _run_bulk(
    txn_service: TransactionService, transaction_ids: list[uuid.UUID], action
) -> BulkActionResult:
    """Apply an action per id, reporting each failure instead of swallowing it.

    Every recorded change shares one change-log batch so the whole bulk
    action undoes as a unit; the batch id is omitted when nothing succeeded.
    """
    updated: list[uuid.UUID] = []
    failed: list[BulkItemFailure] = []
    with txn_service.changes.batch() as batch_id:
        for txn_id in transaction_ids:
            try:
                await action(txn_id)
                updated.append(txn_id)
            except (NotFoundError, InvariantViolation) as e:
                failed.append(BulkItemFailure(id=txn_id, reason=str(e)))
    return BulkActionResult(updated=updated, failed=failed, batch_id=batch_id if updated else None)


@router.patch("/{budget_id}/transactions/bulk-cleared", response_model=BulkActionResult)
async def bulk_update_cleared(
    budget_id: BudgetAccess,
    body: BulkClearedUpdate,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> BulkActionResult:
    return await _run_bulk(
        txn_service,
        body.transaction_ids,
        lambda txn_id: txn_service.update(budget_id, txn_id, SvcTxnUpdate(cleared=body.cleared)),
    )


@router.patch("/{budget_id}/transactions/bulk-categorize", response_model=BulkActionResult)
async def bulk_categorize(
    budget_id: BudgetAccess,
    body: BulkCategorize,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> BulkActionResult:
    return await _run_bulk(
        txn_service,
        body.transaction_ids,
        lambda txn_id: txn_service.update(
            budget_id, txn_id, SvcTxnUpdate(category_id=body.category_id)
        ),
    )


@router.post("/{budget_id}/transactions/bulk-delete", response_model=BulkActionResult)
async def bulk_delete(
    budget_id: BudgetAccess,
    body: BulkDelete,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> BulkActionResult:
    return await _run_bulk(
        txn_service, body.transaction_ids, lambda txn_id: txn_service.delete(budget_id, txn_id)
    )


@router.post("/transactions/{transaction_id}/approve", response_model=TransactionResponse)
async def approve_transaction(
    transaction_id: TransactionAccess,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    try:
        txn = await txn_service.approve(transaction_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


@router.post("/transactions/{transaction_id}/unreconcile", response_model=TransactionResponse)
async def unreconcile_transaction(
    transaction_id: TransactionAccess,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    budget_id: BudgetAccess,
) -> TransactionResponse:
    try:
        txn = await txn_service.unreconcile(budget_id, transaction_id)
    except (NotFoundError, InvariantViolation) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


@router.patch("/{budget_id}/transactions/bulk-approve", response_model=BulkActionResult)
async def bulk_approve(
    budget_id: BudgetAccess,
    body: BulkApprove,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> BulkActionResult:
    return await _run_bulk(
        txn_service, body.transaction_ids, lambda txn_id: txn_service.approve(txn_id, budget_id)
    )


@router.post("/{budget_id}/transactions/merge", response_model=TransactionResponse)
async def merge_transactions(
    budget_id: BudgetAccess,
    body: MergeTransactionsRequest,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    try:
        txn = await txn_service.merge(budget_id, body.transaction_ids, body.survivor_id)
    except (InvariantViolation, NotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


@router.get("/{budget_id}/transactions/pending-review-count", response_model=PendingReviewCount)
async def get_pending_review_count(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> PendingReviewCount:
    counts = await txn_repo.count_pending_review(budget_id)
    return PendingReviewCount(**counts)


@router.get("/accounts/{account_id}/pending-review-count", response_model=PendingReviewCount)
async def get_pending_review_count_for_account(
    account_id: AccountAccess,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> PendingReviewCount:
    counts = await txn_repo.count_pending_review_for_account(account_id)
    return PendingReviewCount(**counts)


# ─── Payees ───────────────────────────────────────────────────────────────────


@router.get("/{budget_id}/payees", response_model=list[PayeeWithCount])
async def list_payees(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
) -> list[PayeeWithCount]:
    rows = await payee_repo.get_all_with_counts(budget_id)
    return [
        PayeeWithCount(
            **PayeeResponse.model_validate(p).model_dump(),
            transaction_count=count,
            last_used=last_used,
        )
        for p, count, last_used in rows
    ]


@router.get("/{budget_id}/payees/duplicates", response_model=list[DuplicatePayeeGroup])
async def find_duplicate_payees(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
    threshold: int = Query(75, ge=60, le=90),
) -> list[DuplicatePayeeGroup]:
    """Find groups of similar payees that may be duplicates.

    Uses fuzzy string matching to identify payees with similar names.
    Groups are sorted by total transaction count descending.
    Threshold: 60-90 (higher = stricter matching, fewer but more confident results)
    """
    groups = await payee_repo.find_duplicate_groups(budget_id, threshold=threshold)
    return [
        DuplicatePayeeGroup(
            payees=[
                DuplicatePayeeEntry(
                    id=p["id"], name=p["name"], transaction_count=p["transaction_count"]
                )
                for p in g["payees"]
            ],
            similarity=g["similarity"],
        )
        for g in groups
    ]


@router.get("/{budget_id}/payees/nearby", response_model=list[NearbyPayeeResponse])
async def nearby_payees(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(500, ge=50, le=5000),
    limit: int = Query(8, ge=1, le=25),
) -> list[NearbyPayeeResponse]:
    """Payees the user has transacted with near a point, closest first.

    Bounding-box prefilter in SQL, exact haversine here — no PostGIS needed at
    household scale. Only opt-in located transactions contribute.
    """
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_m)
    rows = await payee_repo.get_located_visits(budget_id, min_lat, max_lat, min_lng, max_lng)

    grouped: dict[uuid.UUID, dict] = {}
    for payee_id, name, default_category_id, t_lat, t_lng, t_date in rows:
        dist = haversine_m(lat, lng, t_lat, t_lng)
        if dist > radius_m:
            continue
        entry = grouped.get(payee_id)
        if entry is None:
            grouped[payee_id] = {
                "id": payee_id,
                "name": name,
                "default_category_id": default_category_id,
                "distance_m": dist,
                "visit_count": 1,
                "last_date": t_date,
            }
        else:
            entry["distance_m"] = min(entry["distance_m"], dist)
            entry["visit_count"] += 1
            if t_date > entry["last_date"]:
                entry["last_date"] = t_date

    ranked = sorted(grouped.values(), key=lambda e: e["distance_m"])[:limit]
    return [NearbyPayeeResponse(**e) for e in ranked]


@router.post(
    "/{budget_id}/payees",
    response_model=PayeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payee(
    budget_id: BudgetAccess,
    body: PayeeCreate,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> PayeeResponse:
    # find-or-create: only log when a payee actually gets created
    existing = await payee_repo.find_by_name(budget_id, body.name)
    payee = existing or await payee_repo.create(budget_id=budget_id, name=body.name)
    if existing is None:
        await recorder.record(
            budget_id=budget_id,
            entity_type="payee",
            entity_id=payee.id,
            action="create",
            after=snapshot("payee", payee),
        )
    return PayeeResponse.model_validate(await payee_repo.get_with_tags(payee.id))


@router.patch("/payees/{payee_id}", response_model=PayeeResponse)
async def update_payee(
    payee_id: PayeeAccess,
    body: PayeeUpdate,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> PayeeResponse:
    # exclude_unset (not exclude_none) so an explicit null clears nullable
    # fields like mapping_samples and match_pattern; name stays required.
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name") is None:
        changes.pop("name", None)
    owner = await payee_repo.get(payee_id)
    if owner is not None and changes.get("default_category_id") is not None:
        await require_in_budget(
            payee_repo.session,
            Category,
            changes["default_category_id"],
            owner.budget_id,
            "Category",
        )
    before = snapshot("payee", owner) if owner is not None else None
    updated = await payee_repo.update(payee_id, **changes)
    if owner is not None and before is not None:
        after = snapshot("payee", updated)
        if snapshots_match(after, before):
            await recorder.record(
                budget_id=owner.budget_id,
                entity_type="payee",
                entity_id=payee_id,
                action="update",
                before=before,
                after=after,
            )
    return PayeeResponse.model_validate(await payee_repo.get_with_tags(payee_id))


@router.delete("/payees/{payee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payee(
    payee_id: PayeeAccess,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> None:
    payee = await payee_repo.get_or_raise(payee_id)
    before = snapshot("payee", payee)
    await payee_repo.delete(payee_id)
    await recorder.record(
        budget_id=payee.budget_id,
        entity_type="payee",
        entity_id=payee_id,
        action="delete",
        before=before,
    )


@router.post("/payees/{payee_id}/merge", response_model=PayeeMergeResult)
async def merge_payee(
    payee_id: PayeeAccess,
    body: PayeeMergeRequest,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> PayeeMergeResult:
    if payee_id == body.target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge a payee into itself",
        )
    source = await payee_repo.get_or_raise(payee_id)
    source_before = snapshot("payee", source)
    try:
        moved = await payee_repo.merge(payee_id, body.target_id)
    except InvariantViolation as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    change = await recorder.record(
        budget_id=source.budget_id,
        entity_type="payee",
        entity_id=payee_id,
        action="merge",
        before={**source_before, "_transaction_ids": [str(t) for t in moved]},
        after={"merged_into": str(body.target_id)},
    )
    return PayeeMergeResult(change_id=change.id)
