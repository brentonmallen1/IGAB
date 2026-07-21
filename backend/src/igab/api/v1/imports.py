import hashlib
import io
import uuid
from datetime import date
from decimal import Decimal

import polars as pl
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.session import get_session
from igab.dependencies import (
    AccountAccess,
    BudgetAccess,
    CurrentUser,
    get_account_repo,
    get_assignment_repo,
    get_category_group_repo,
    get_category_repo,
    get_payee_repo,
    get_transaction_repo,
    get_transaction_service,
)
from igab.domain.money import parse_csv_amount
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


def _generate_import_id(account_id: uuid.UUID, txn_date: date, amount: Decimal, payee: str) -> str:
    content = f"{account_id}|{txn_date.isoformat()}|{amount}|{payee}"
    return f"csv:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


class YNABImportResult(BaseModel):
    accounts: int
    category_groups: int
    categories: int
    transactions: int
    skipped: int
    assignments: int
    errors: list[str]


@router.post("/{budget_id}/import/ynab", response_model=YNABImportResult)
async def import_ynab(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    account_repo: AccountRepository = Depends(get_account_repo),
    category_group_repo: CategoryGroupRepository = Depends(get_category_group_repo),
    category_repo: CategoryRepository = Depends(get_category_repo),
    payee_repo: PayeeRepository = Depends(get_payee_repo),
    transaction_repo: TransactionRepository = Depends(get_transaction_repo),
    assignment_repo: BudgetAssignmentRepository = Depends(get_assignment_repo),
    txn_service: TransactionService = Depends(get_transaction_service),
) -> YNABImportResult:
    import tempfile
    from pathlib import Path

    content = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        parser = YNABParser()
        try:
            ynab_budget = parser.parse_zip(tmp_path)
        except (ValueError, KeyError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

        importer = YNABImporter(
            session=session,
            budget_id=budget_id,
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

    return YNABImportResult(
        accounts=result.accounts_imported,
        category_groups=result.category_groups_imported,
        categories=result.categories_imported,
        transactions=result.transactions_imported,
        skipped=result.transactions_skipped,
        assignments=result.assignments_imported,
        errors=result.errors,
    )


@router.post("/{budget_id}/import/csv", response_model=ImportResult)
async def import_csv(
    budget_id: BudgetAccess,
    account_id: AccountAccess,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    account_repo: AccountRepository = Depends(get_account_repo),
    payee_repo: PayeeRepository = Depends(get_payee_repo),
    transaction_repo: TransactionRepository = Depends(get_transaction_repo),
) -> ImportResult:
    """
    Import transactions from CSV.
    Expected columns (case-insensitive): Date, Payee, Amount, Memo
    Amount: positive = inflow, negative = outflow
    """
    account = await account_repo.get_or_raise(account_id)
    if str(account.budget_id) != str(budget_id):
        raise HTTPException(status_code=400, detail="Account does not belong to this budget")

    content = await file.read()

    try:
        df = pl.read_csv(io.BytesIO(content), try_parse_dates=True, infer_schema_length=0)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot parse CSV: {e}") from e

    if df.is_empty():
        raise HTTPException(status_code=400, detail="Empty CSV file")

    # Normalize column names: strip whitespace and lowercase
    df = df.rename({c: c.strip().lower() for c in df.columns})

    for required in ("date", "amount"):
        if required not in df.columns:
            raise HTTPException(status_code=400, detail=f"Missing required column: '{required}'")

    errors: list[str] = []
    skipped = 0

    # Parse date column
    if df["date"].dtype != pl.Date:
        date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"]
        parsed = None
        for fmt in date_formats:
            try:
                parsed = df["date"].str.to_date(fmt, strict=False)
                if parsed.null_count() < df.height:
                    break
            except Exception:
                continue
        if parsed is None:
            raise HTTPException(status_code=400, detail="Cannot parse date column")
        df = df.with_columns(parsed.alias("date"))

    # Drop rows with null dates or amounts
    null_date_mask = df["date"].is_null()
    null_amount_mask = df["amount"].is_null() | (df["amount"].cast(pl.String) == "")
    bad_mask = null_date_mask | null_amount_mask
    bad_count = bad_mask.sum()
    if bad_count:
        skipped += int(bad_count)
        df = df.filter(~bad_mask)

    if df.is_empty():
        return ImportResult(imported=0, skipped=skipped, errors=errors)

    # Amounts are parsed string→Decimal in the row loop below (never through
    # float — exactness is the point of a budgeting app).
    df = df.with_columns(df["amount"].cast(pl.String).alias("amount_str"))

    # Resolve payees in batch
    payee_col = "payee" if "payee" in df.columns else None
    payee_names: list[str] = []
    if payee_col:
        payee_names = df[payee_col].drop_nulls().cast(pl.String).unique().to_list()
        payee_names = [p.strip() for p in payee_names if p.strip()]

    payee_map: dict[str, str] = {}
    if payee_names:
        id_map = await payee_repo.find_or_create_batch(budget_id, payee_names)
        payee_map = {name: str(pid) for name, pid in id_map.items()}

    # Build insert rows
    batch_id = uuid.uuid4()
    rows_to_insert = []
    df_iter = df.iter_rows(named=True)
    for row in df_iter:
        payee_name = (row.get("payee") or "").strip() if payee_col else ""
        payee_id = payee_map.get(payee_name) if payee_name else None
        memo = (row.get("memo") or "").strip() or None

        txn_date = row["date"]
        try:
            amount = parse_csv_amount(row["amount_str"])
        except ValueError as e:
            errors.append(str(e))
            skipped += 1
            continue
        rows_to_insert.append(
            {
                "id": uuid.uuid4(),
                "budget_id": budget_id,
                "account_id": account_id,
                "date": txn_date,
                "amount": amount,
                "payee_id": uuid.UUID(payee_id) if payee_id else None,
                "category_id": None,
                "memo": memo,
                "cleared": "cleared",
                "approved": False,
                "import_batch_id": batch_id,
                "is_split": False,
                "is_deleted": False,
                "import_id": _generate_import_id(account_id, txn_date, amount, payee_name),
            }
        )

    # Two identical rows in one file (a real double charge) hash to the same
    # import_id; suffix ":N" so both import and the unique index holds. The
    # suffixing is order-stable, so re-importing the same file still dedups.
    seen_ids: dict[str, int] = {}
    for r in rows_to_insert:
        base_id = r["import_id"]
        count = seen_ids.get(base_id, 0)
        if count > 0:
            r["import_id"] = f"{base_id}:{count}"
        seen_ids[base_id] = count + 1

    # Deduplicate against existing import_ids before inserting
    all_import_ids = [r["import_id"] for r in rows_to_insert if r.get("import_id")]
    existing_ids = await transaction_repo.get_existing_import_ids(budget_id, all_import_ids)
    new_rows = [r for r in rows_to_insert if r.get("import_id") not in existing_ids]
    skipped += len(rows_to_insert) - len(new_rows)

    imported = await transaction_repo.bulk_create(new_rows)
    return ImportResult(imported=imported, skipped=skipped, errors=errors)
