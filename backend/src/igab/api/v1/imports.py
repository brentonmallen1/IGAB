import io
import json
import re
import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import TypedDict

import polars as pl
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, ValidationError

from igab.db.models import ChangeLog, new_uuid
from igab.dependencies import (
    AccountAccess,
    BudgetAccess,
    CurrentUser,
    get_account_repo,
    get_payee_repo,
    get_transaction_repo,
)
from igab.domain.account_types import BUILTIN_ACCOUNT_TYPE_KEYS
from igab.domain.import_identity import disambiguate_in_batch, generate_import_id
from igab.domain.money import parse_csv_amount
from igab.integrations.ynab.importer import ImportResult as YNABRunResult
from igab.integrations.ynab.importer import YNABImporter
from igab.integrations.ynab.parser import YNABParser
from igab.repositories.account_repo import AccountRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import snapshot

router = APIRouter()


class InsertRow(TypedDict):
    """One row of the bulk transaction insert.

    Typed so `r["import_id"]` narrows to str. Left as a bare dict the row
    infers as dict[str, UUID | date | Decimal | str | bool | None], and that
    union is neither a valid key for the seen_ids counter nor a valid element
    for get_existing_import_ids(..., list[str]).
    """

    id: uuid.UUID
    budget_id: uuid.UUID
    account_id: uuid.UUID
    date: date
    amount: Decimal
    payee_id: uuid.UUID | None
    category_id: uuid.UUID | None
    memo: str | None
    cleared: str
    approved: bool
    import_batch_id: uuid.UUID
    is_split: bool
    is_deleted: bool
    created_via: str
    import_id: str


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
    # Change-log batch covering the imported transactions, for undo
    batch_id: uuid.UUID | None = None


class YNABImportResult(BaseModel):
    accounts: int
    category_groups: int
    categories: int
    transactions: int
    skipped: int
    assignments: int
    #: Accounts the user chose to leave out (closed/archived YNAB accounts).
    accounts_skipped: int = 0
    #: Accounts imported in full and then closed at the user's request. Their
    #: transactions all arrived; only the account is hidden from pickers.
    accounts_closed: int = 0
    #: Register rows belonging to those accounts — deliberately excluded,
    #: distinct from `skipped` (dedup/errors).
    transactions_excluded: int = 0
    #: Transfer legs imported without their partner. Non-zero means some rows
    #: that are really internal movement could not be identified as such.
    transfer_legs_unpaired: int = 0
    #: Categories tagged Savings / Long-term expense from their names. A tag
    #: changes how that category's spending is classified, so the count is
    #: shown rather than applied quietly.
    categories_tagged: int = 0
    #: YNAB's Credit Card Payments reserves, left out on purpose: IGAB nets a
    #: card's balance against cash in Ready to Assign, so importing them
    #: would reserve the same debt twice. The money is what Ready to Assign
    #: keeps as a result.
    credit_card_payment_assignments_skipped: int = 0
    credit_card_payment_reserves_skipped: Decimal = Decimal("0")
    errors: list[str]


class YNABAccountPreview(BaseModel):
    name: str
    transaction_count: int
    suggested_type: str
    suggested_on_budget: bool
    #: The name gave no confident signal (or gave an ambiguous one), so the
    #: suggestion is a fallback. The mapping UI should ask the user to confirm
    #: rather than letting it through pre-filled — a tracked account slipping in
    #: as on-budget corrupts to_be_assigned for the whole budget.
    needs_review: bool = False
    #: Sum of the account's register rows, shown next to the type picker so the
    #: user can tell a house from its mortgage at a glance.
    implied_balance: Decimal = Decimal("0")
    #: Oldest and newest register dates. A YNAB export carries no closed-account
    #: marker, so an account dormant since 2019 is indistinguishable from a
    #: live one by name alone — and 14 of them arriving unannounced is what
    #: made a real import read as "accounts appearing from nowhere". The dates
    #: are already parsed on every row and were simply thrown away.
    first_activity: date | None = None
    last_activity: date | None = None
    #: Accounts sharing a leading name fragment — an institution's accounts, or
    #: an asset and the debt against it. A prompt to compare, never a merge
    #: suggestion: see `assign_related_groups`.
    related_group: str | None = None


class YNABPreviewResult(BaseModel):
    accounts: list[YNABAccountPreview]
    transaction_count: int
    budget_entry_count: int


class YNABAccountTypeChoice(BaseModel):
    # Built-in registry keys only: the budget doesn't exist yet when the
    # mapping is chosen, so no custom types can — create those afterwards.
    account_type: str = Field(pattern=r"^[a-z0-9_]{1,30}$")
    on_budget: bool
    #: Leave this account (and every one of its register rows) out of the
    #: import entirely — YNAB exports carry archived accounts with no marker,
    #: so excluding them is a user decision made in the preview step.
    skip: bool = False
    #: Import everything, then close the account. Prefer this to `skip` for a
    #: dormant account: closing hides it from pickers and report filters while
    #: keeping every transaction, so net worth over time stays whole and its
    #: transfers still pair up. `skip` erases the history instead.
    close: bool = False


# YNAB register exports carry no account-type info — only names — so the
# mapping step suggests from name keywords and the user confirms per account.
# Where YNAB's own taxonomy lands in IGAB:
#   Checking → checking · Savings/Money Market → savings · Cash → cash
#   Credit Card / Line of Credit → credit_card
#   Mortgage → mortgage · Car/auto loans → auto_loan · Student → student_loan
#     · anything else owed → loan. All off budget, and all get their payoff
#     tracking automatically — the liability record comes with the account.
#   Asset tracking (brokerage, 401k, IRA, HSA, ESPP) → investment
#   Other tracking assets (crypto, treasury) → other_asset
#   Liability tracking → other_liability
#
# Matching is token-based, never substring: "ira" must not fire on "Admiral",
# "cc" must not fire on "Account", "mm" must not fire on "Summit". Multi-word
# keywords ("money market") match as adjacent tokens.
#
# Getting `on_budget` wrong is not a cosmetic error: to_be_assigned is
# `total_account_balance - total_category_balance - assigned_in_future`, so an
# account wrongly ON budget silently corrupts every budget number. Rules are
# therefore ordered most-specific first, and anything unrecognised is returned
# with needs_review set so the mapping UI can demand a decision.
_TYPE_HINTS: list[tuple[tuple[str, ...], str, bool]] = [
    # Explicit debt first — "Cedar Grove Property Loan" is a loan, not property.
    # Specific kinds before the generic, since "Student Loans" and "Car Loan"
    # both contain "loan": the first match wins, so the generic must be last.
    (("mortgage",), "mortgage", False),
    (("student",), "student_loan", False),
    (("loan", "heloc"), "loan", False),
    (
        ("credit", "card", "visa", "amex", "mastercard", "discover", "cc"),
        "credit_card",
        True,
    ),
    (
        (
            "invest",
            "brokerage",
            "401k",
            "401 k",
            "403b",
            "403 b",
            "457",
            "ira",
            "roth",
            "hsa",
            "retirement",
            "espp",
            "stock",
            "equity",
            "rollover",
            "pension",
            "annuity",
        ),
        "investment",
        False,
    ),
    (("crypto", "treasury"), "other_asset", False),
    (("checking", "chequing", "chk", "debit"), "checking", True),
    (("hysa", "money market", "mm", "saving", "savings", "emergency"), "savings", True),
    (("cash",), "cash", True),
]

# Names describing something owned or owed rather than a bank account. Which
# side it falls on cannot be read from the name — "Birchwood Property Ferry" is
# a mortgage while "Birchwood Property Ferry House" is the house — so the sign
# of the account's own register decides. Either way the account is OFF budget,
# which is the part that protects to_be_assigned; the asset/liability split
# only affects net-worth presentation, so a wrong guess there is cheap.
_TRACKED_HINTS: tuple[str, ...] = (
    "property",
    "house",
    "home",
    "real estate",
    "land",
    "condo",
    "apartment",
    "vehicle",
    "car",
    "truck",
    "boat",
    "motorcycle",
    "auto",
    "rv",
)

#: A vehicle word ALONE names the asset — "Vehicle A" is the car, not the debt
#: against it — so only its co-occurrence with "loan" says auto loan. Handled
#: outside _TYPE_HINTS because the words need not be adjacent ("Vehicle A Loan",
#: "Car (2019) Loan") and a phrase list cannot express that. Boats and the like
#: stay on the generic `loan`; there is no account type for them to be specific
#: about.
_VEHICLE_WORDS: tuple[str, ...] = ("car", "auto", "vehicle", "truck", "motorcycle", "rv")

#: YNAB users commonly mark tracking accounts in the name itself. That is a
#: deliberate statement about budget membership, so it outranks any type
#: keyword that also happens to appear ("Lakeside Trust MM - tracked" is a
#: tracking account, not a money-market savings account).
_OFF_BUDGET_MARKERS: tuple[str, ...] = ("tracked", "tracking", "off budget")


def _normalize_for_match(name: str) -> str:
    """Lowercase, punctuation → single spaces, padded so " kw " matches on
    token boundaries at either end."""
    return " " + re.sub(r"[^a-z0-9]+", " ", name.lower()).strip() + " "


#: Keywords that also match inside a run-together name ("TreasuryDirect",
#: "SavingsPlus"). Listed explicitly rather than by length: a length rule lets
#: "discover" fire on "Discovery Fund". Every entry here must be a word that
#: cannot be the prefix of an unrelated one.
_CONCATENATION_SAFE: frozenset[str] = frozenset(
    {"treasury", "brokerage", "mortgage", "savings", "checking", "retirement"}
)


#: Keywords are stems, not whole words: "invest" has to reach "Investments",
#: "Investment Account" and "Investing". The move from substring to token
#: matching silently dropped every inflected form — "Investments" is a very
#: common YNAB account name, and it began importing as ON-BUDGET checking,
#: folding a brokerage balance straight into Ready to Assign. An explicit
#: suffix list restores that reach without the substring rule's false
#: positives ("invest" as substring also hits "investigation").
_STEM_SUFFIXES: tuple[str, ...] = ("", "s", "es", "ing", "ment", "ments")


def _matches(normalized: str, keywords: tuple[str, ...]) -> bool:
    for kw in keywords:
        for suffix in _STEM_SUFFIXES:
            if f" {kw}{suffix} " in normalized:
                return True
        if kw in _CONCATENATION_SAFE and kw in normalized:
            return True
    return False


def suggest_account_type(
    name: str, implied_balance: Decimal | None = None
) -> tuple[str, bool, bool]:
    """Guess (account_type, on_budget, needs_review) for a YNAB account name.

    `implied_balance` is the sum of the account's register rows. It is used only
    to pick asset vs liability for tracked-thing names, where the name alone is
    genuinely ambiguous.
    """
    normalized = _normalize_for_match(name)

    if _matches(normalized, _OFF_BUDGET_MARKERS):
        is_liability = implied_balance is not None and implied_balance < 0
        return ("other_liability" if is_liability else "other_asset"), False, True

    # Before the hint list, since the generic `loan` rule would otherwise claim
    # it. Mortgage and student still win — a name carrying both words is
    # describing the more specific thing.
    if (
        _matches(normalized, ("loan",))
        and _matches(normalized, _VEHICLE_WORDS)
        and not _matches(normalized, ("mortgage", "student"))
    ):
        return "auto_loan", False, False

    for keywords, account_type, on_budget in _TYPE_HINTS:
        if _matches(normalized, keywords):
            return account_type, on_budget, False

    if _matches(normalized, _TRACKED_HINTS):
        is_liability = implied_balance is not None and implied_balance < 0
        # Off budget either way; the side is a suggestion worth confirming.
        return ("other_liability" if is_liability else "other_asset"), False, True

    # Unrecognised. `checking` stays the convenient default, but the caller is
    # told not to trust it — silently importing an unknown account as on-budget
    # is exactly how a tracked account corrupts to_be_assigned.
    return "checking", True, True


def parse_account_types_form(
    account_types: str | None,
) -> tuple[dict[str, tuple[str, bool]], set[str], set[str]]:
    """Decode the JSON `account_types` multipart form field:
    {"Account Name": {"account_type": "loan", "on_budget": false, "skip": false}, ...}

    Returns (type_map, skip_accounts, close_accounts): the type/on-budget
    mapping for accounts being imported, the set to exclude entirely, and the
    set to import and then close. Skip and close are mutually exclusive by
    construction — a skipped account is never created, so there is nothing to
    close, and `skip` wins if a caller sends both."""
    if not account_types:
        return {}, set(), set()
    try:
        raw = json.loads(account_types)
        parsed = {name: YNABAccountTypeChoice.model_validate(v) for name, v in raw.items()}
    except (ValueError, ValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid account_types mapping: {e}",
        ) from e
    unknown = {c.account_type for c in parsed.values() if not c.skip} - BUILTIN_ACCOUNT_TYPE_KEYS
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown account type(s): {', '.join(sorted(unknown))}. "
                f"Valid types: {', '.join(sorted(BUILTIN_ACCOUNT_TYPE_KEYS))}"
            ),
        )
    type_map = {
        name: (choice.account_type, choice.on_budget)
        for name, choice in parsed.items()
        if not choice.skip
    }
    skip_accounts = {name for name, choice in parsed.items() if choice.skip}
    close_accounts = {name for name, choice in parsed.items() if choice.close and not choice.skip}
    return type_map, skip_accounts, close_accounts


#: How many leading tokens may form a related-account group.
#:
#: One is too coarse and two is the natural size of a thing's name: "Employer
#: A", "Union Ridge", "Cedar Grove", "Vehicle A". At one token the two
#: employers in a real export merge into a nine-account pile; unbounded, a
#: six-account employer shatters into "Employer A ESPP", "Employer A HSA" and
#: a remainder, which is grouping by product line rather than by the thing the
#: user recognises.
_RELATED_GROUP_MAX_TOKENS = 2


def _tokens_preserving_case(name: str) -> list[str]:
    """Same split as `_normalize_for_match`, with the original casing kept.

    Aligns token-for-token with the normalized form, so a group matched on
    "brightpath hsa" can be labelled from the source as "Brightpath HSA"
    rather than title-cased into "Brightpath Hsa"."""
    return [t for t in re.split(r"[^A-Za-z0-9]+", name) if t]


def assign_related_groups(names: Sequence[str]) -> dict[str, str | None]:
    """Group accounts sharing a leading name fragment: name → group label.

    **Related, never duplicate, and never a merge suggestion.** Measured on a
    real export, `rapidfuzz.token_set_ratio` returns 100 for "vehicle a" vs
    "vehicle a loan", "redwood" vs "redwood cc" and "harborstone" vs
    "harborstone savings" — every pair a legitimately distinct account. Acting
    on similarity here would tell someone to destroy real data. A shared
    leading fragment says only "these are probably about the same thing, look
    at them together": an institution's accounts, or an asset and the debt
    secured against it. Comparing those balances is exactly how a house typed
    as a mortgage gets caught.

    Longest shared prefix wins within the cap, so "Vehicle A" pairs with
    "Vehicle A Loan" rather than landing in a bucket with "Vehicle B".
    """
    tokens = {name: _normalize_for_match(name).split() for name in names}
    prefix_members: dict[tuple[str, ...], list[str]] = {}
    for name, toks in tokens.items():
        for k in range(1, min(len(toks), _RELATED_GROUP_MAX_TOKENS) + 1):
            prefix_members.setdefault(tuple(toks[:k]), []).append(name)

    groups: dict[str, str | None] = {}
    for name, toks in tokens.items():
        best: tuple[str, ...] | None = None
        for k in range(min(len(toks), _RELATED_GROUP_MAX_TOKENS), 0, -1):
            prefix = tuple(toks[:k])
            if len(prefix_members[prefix]) > 1:
                best = prefix
                break
        if best is None:
            groups[name] = None
            continue
        # Label from whichever member spells it out, so acronyms survive.
        source = min(prefix_members[best])
        groups[name] = " ".join(_tokens_preserving_case(source)[: len(best)])
    return groups


def build_ynab_preview(ynab_budget) -> "YNABPreviewResult":
    counts: dict[str, int] = {}
    balances: dict[str, Decimal] = {}
    first_seen: dict[str, date] = {}
    last_seen: dict[str, date] = {}
    for txn in ynab_budget.transactions:
        counts[txn.account_name] = counts.get(txn.account_name, 0) + 1
        # Split parents carry the full amount and their legs are nested, so
        # summing top-level rows gives the account balance without double count.
        balances[txn.account_name] = balances.get(txn.account_name, Decimal("0")) + txn.amount
        # min/max rather than first/last row: a YNAB export is not guaranteed
        # to be in date order, and one out-of-order row would otherwise report
        # a live account as dormant.
        prev_first = first_seen.get(txn.account_name)
        if prev_first is None or txn.date < prev_first:
            first_seen[txn.account_name] = txn.date
        prev_last = last_seen.get(txn.account_name)
        if prev_last is None or txn.date > prev_last:
            last_seen[txn.account_name] = txn.date

    related = assign_related_groups(sorted(counts))
    accounts = []
    for name in sorted(counts):
        implied = balances.get(name, Decimal("0"))
        suggested_type, suggested_on_budget, needs_review = suggest_account_type(name, implied)
        accounts.append(
            YNABAccountPreview(
                name=name,
                transaction_count=counts[name],
                suggested_type=suggested_type,
                suggested_on_budget=suggested_on_budget,
                needs_review=needs_review,
                implied_balance=implied,
                first_activity=first_seen.get(name),
                last_activity=last_seen.get(name),
                related_group=related.get(name),
            )
        )
    return YNABPreviewResult(
        accounts=accounts,
        transaction_count=len(ynab_budget.transactions),
        budget_entry_count=len(ynab_budget.budget_entries),
    )


async def run_ynab_import(importer: YNABImporter, ynab_budget) -> YNABRunResult:
    """Run the import, converting database-level failures into a readable 400.

    Bulk inserts run outside the per-row error capture; without this an
    IntegrityError surfaced as a generic 500 with the real reason visible
    only in server logs."""
    from sqlalchemy.exc import DBAPIError

    try:
        return await importer.import_budget(ynab_budget)
    except DBAPIError as e:
        reason = str(getattr(e, "orig", e) or e).strip().splitlines()[0][:300]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Import failed at the database: {reason}",
        ) from e


async def parse_uploaded_ynab_zip(file: UploadFile):
    import tempfile
    from pathlib import Path

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        try:
            return YNABParser().parse_zip(tmp_path)
        except (ValueError, KeyError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e
    finally:
        tmp_path.unlink(missing_ok=True)


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
    rows_to_insert: list[InsertRow] = []
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
                "created_via": "import",
                "import_id": generate_import_id(account_id, txn_date, amount, payee_name),
            }
        )

    disambiguate_in_batch(rows_to_insert)

    # Deduplicate against existing import_ids before inserting
    all_import_ids = [r["import_id"] for r in rows_to_insert if r.get("import_id")]
    existing_ids = await transaction_repo.get_existing_import_ids(budget_id, all_import_ids)
    new_rows = [r for r in rows_to_insert if r.get("import_id") not in existing_ids]
    skipped += len(rows_to_insert) - len(new_rows)

    imported = await transaction_repo.bulk_create(new_rows)

    # One change-log row per imported transaction, grouped under the import
    # batch id so the whole import can be undone as a unit.
    transaction_repo.session.add_all(
        [
            ChangeLog(
                id=new_uuid(),
                budget_id=budget_id,
                entity_type="transaction",
                entity_id=r["id"],
                action="import",
                after=snapshot("transaction", r),
                batch_id=batch_id,
                source="import",
            )
            for r in new_rows
        ]
    )
    return ImportResult(
        imported=imported,
        skipped=skipped,
        errors=errors,
        batch_id=batch_id if new_rows else None,
    )
