import io
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal, TypedDict

import polars as pl
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from igab.api.route import CommitRoute
from igab.db.models import Budget, ChangeLog, new_uuid
from igab.db.session import get_session
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
from igab.domain.import_mapping import (
    RememberedChoice,
    account_key,
    assign_related_groups,
    resolve_account_suggestion,
)
from igab.domain.money import parse_csv_amount
from igab.integrations.ynab.importer import ImportResult as YNABRunResult
from igab.integrations.ynab.importer import YNABImporter
from igab.integrations.ynab.parser import YNABParser
from igab.repositories.account_repo import AccountRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match

router = APIRouter(route_class=CommitRoute)


class ImportSummaryOut(BaseModel):
    """What an import did, and whether anyone has looked at it yet.

    `summary` is null for a budget that was not created by a YNAB import, and
    for one imported before this was recorded. Both are ordinary cases, not
    errors — the review still opens, it just has nothing to report about the
    event and goes straight to what can still be changed.
    """

    summary: "YNABImportResult | None" = None
    reviewed_at: datetime | None = None


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


class YNABParityDifference(BaseModel):
    name: str
    igab: Decimal
    ynab: Decimal
    #: Uncleared rows this month. When it equals the gap, the difference is
    #: YNAB not having approved an import yet rather than a disagreement.
    pending: Decimal = Decimal("0")


class YNABExportConsistencyOut(BaseModel):
    """Whether the export's own numbers agree with each other.

    Parity holds IGAB's recomputed Available against the Available column
    YNAB shipped, and that only means something if the file hangs together.
    `carryover` checks each category's months against YNAB's own running
    balance; `activity` checks each Plan Activity cell against the register
    rows shipped beside it. When `self_consistent` is false the envelope
    differences describe the file, not the import, and should be read that
    way.
    """

    self_consistent: bool
    carryover_rows_checked: int
    carryover_rows_violating: int
    activity_cells_checked: int
    activity_cells_disagreeing: int


class YNABCardHistoryOut(BaseModel):
    """The first month a card's set-aside detached from YNAB's reserve.

    Every month of the plan is compared, not just the viewed one: on a
    long import "which month" is the actionable half — that month's
    register is a few dozen rows, the whole history is not."""

    name: str
    first_month: date
    igab: Decimal
    ynab: Decimal
    months_compared: int
    months_differing: int


class YNABParityOut(BaseModel):
    """How the imported budget compares with the export's own figures.

    `ynab_ready_to_assign` is what YNAB's numbers say; `expected` is that
    figure adjusted by unfiled cash rows (out of Ready to Assign here, out
    of the plan there); `igab` is what the budget actually shows — the two
    follow the same credit rules now, and `uncovered_card_debt` is the
    cards' expected Uncovered rather than a gap. `matches` means
    expected == igab AND every envelope's balance equals the Available
    column YNAB shipped.
    """

    month: date
    ynab_ready_to_assign: Decimal
    expected_ready_to_assign: Decimal
    igab_ready_to_assign: Decimal
    uncovered_card_debt: Decimal
    #: Uncategorized rows on budget accounts: out of Ready to Assign here
    #: until filed, out of YNAB's plan entirely.
    uncategorized_net: Decimal
    matches: bool
    categories_compared: int
    categories_differing: int
    #: Envelopes that differ from YNAB's Available by exactly their uncleared
    #: rows this month — YNAB counts imported rows only once approved.
    categories_pending: int
    #: Envelopes YNAB priced that no IGAB category answered to. Not compared;
    #: reported so `categories_compared` is explainable.
    categories_unmatched: int
    top_differences: list[YNABParityDifference]
    #: Card set-asides held against the per-card Credit Card Payments
    #: reserve YNAB shipped. A differing card is an envelope that detached
    #: from its ledger over the imported history — the import is when that
    #: drift is largest and least noticeable, so it is checked here.
    cards_compared: int
    cards_differing: int
    card_differences: list[YNABParityDifference]
    #: Cards with at least one divergent month, earliest first. Empty when
    #: every card agrees with the file in every month.
    card_history: list[YNABCardHistoryOut]
    #: YNAB's shipped CCP Available, per card (lowercased name, the way the
    #: importer matches cards) per plan month. The export zip is the only
    #: other place this series exists, and it is routinely gone by the time a
    #: reserve question comes up — persisting it here is what lets
    #: scripts/card_reserve_probe.py overlay IGAB's reserve against YNAB's
    #: own figures on a long-lived install, no zip required.
    ccp_available_history: dict[str, dict[date, Decimal]] = Field(default_factory=dict)
    consistency: YNABExportConsistencyOut


class YNABTaggedCategory(BaseModel):
    """One tag the import applied, and the name that made it."""

    category_id: uuid.UUID
    system_key: str
    matched_on: str


class YNABHeldOutFuture(BaseModel):
    """One register row dated after the import that became an upcoming
    transaction instead of a posted one. The review lists these so the
    cadence YNAB could not export can be set by hand."""

    scheduled_transaction_id: uuid.UUID
    account_name: str
    date: date
    payee: str
    amount: Decimal
    category_name: str | None = None
    is_transfer: bool = False
    #: Non-empty when the row was a split: a schedule has one category, so
    #: it was created uncategorized with the legs written into the memo.
    split_legs: list[str] = Field(default_factory=list)


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
    #: How many of those are one line of a split. Unpairable by design (money
    #: fields live on a split's parent), so a review can say which part of the
    #: total is worth chasing and which is not.
    transfer_legs_in_splits: int = 0
    #: Categories tagged Savings / Long-term expense from their names. A tag
    #: changes how that category's spending is classified, so the count is
    #: shown rather than applied quietly.
    categories_tagged: int = 0
    #: Which ones, and why. The count cannot answer "show me what you did",
    #: and nothing on the join table records that a tag was guessed.
    tagged_categories: list[YNABTaggedCategory] = Field(default_factory=list)
    #: YNAB's Credit Card Payments reserves whose card was never imported —
    #: the matched ones become the card's set-aside assignments. The money is
    #: what those cards are missing from their reserves as a result.
    credit_card_payment_assignments_skipped: int = 0
    credit_card_payment_reserves_skipped: Decimal = Decimal("0")
    #: Register rows on tracking accounts whose export line named a category,
    #: imported without one — off-budget activity is net-worth movement, and
    #: a category here would move the budget with no on-budget event.
    tracking_account_categories_stripped: int = 0
    #: Register rows filed to a Credit Card Payments category — a reserve,
    #: not a spending envelope — imported uncategorized. YNAB never writes
    #: such rows itself; a non-zero here means the file was unusual and the
    #: rows need filing by hand.
    credit_card_payment_categories_stripped: int = 0
    #: None when the check could not run; never a failed import.
    parity: YNABParityOut | None = None
    #: B — the budget's envelope math starts from YNAB's own position at the
    #: month before this (db.models.ImportAnchor). Top-level, not inside
    #: `parity`: parity is allowed to fail, the anchor is not conditional on
    #: it. None with `anchor_skipped_reason` set when the export could not be
    #: anchored (register-only, or no complete plan month).
    anchored_at: date | None = None
    anchor_skipped_reason: str | None = None
    #: Register rows dated after the import, each now a one-off scheduled
    #: transaction rather than a posted row. Defaulted, like every field
    #: added since summaries were first stored: the stored document is
    #: re-validated on read.
    held_out_future: list[YNABHeldOutFuture] = Field(default_factory=list)
    #: Of those, splits created uncategorized (legs in the memo) and transfer
    #: legs whose partner never appeared.
    held_out_splits_uncategorized: int = 0
    held_out_transfer_legs_unpaired: int = 0
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
    #: The disposition to arrive pre-selected. Both are sent on every row so
    #: the client seeds all four fields from here instead of hard-coding false
    #: — which is what threw away a remembered "leave this one out" on every
    #: import.
    suggested_skip: bool
    suggested_close: bool
    #: Which of the three sources supplied `suggested_type`/`suggested_on_budget`
    #: — not the disposition, which follows its own precedence. See
    #: `domain.import_mapping.resolve_account_suggestion`.
    suggestion_source: Literal["export", "remembered", "heuristic"]


class YNABPreviewResult(BaseModel):
    accounts: list[YNABAccountPreview]
    #: Posted rows only — the ones that will land in the register.
    transaction_count: int
    #: Rows dated after today, which will become upcoming transactions.
    held_out_future_count: int = 0
    budget_entry_count: int
    #: B — where this file will anchor if imported (integrations/ynab/models
    #: `plan_boundary`), so the preview can say "starts where YNAB left off"
    #: before anything is written. None for a register-only export, which
    #: imports unanchored.
    anchor_month: date | None = None


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


@dataclass(frozen=True)
class AccountMappingForm:
    """One decoding of the `account_types` field, four views of it.

    `choices` keeps every submitted account, including the skipped ones the
    other three deliberately drop. That is not redundancy: the type someone
    chose for an account they also skipped is still the type they chose, and
    it is what should come back if they un-skip it next time. Remembering from
    `type_map` instead would forget `auto_loan` on every skipped account and
    pre-fill `checking / on-budget` — the tracked-account-on-budget failure
    this whole step exists to prevent.
    """

    #: Every submitted account, normalized: `close` cleared wherever `skip` is
    #: set, so the two can never disagree downstream.
    choices: dict[str, YNABAccountTypeChoice]
    type_map: dict[str, tuple[str, bool]]
    skip_accounts: set[str]
    close_accounts: set[str]


def parse_account_types_form(account_types: str | None) -> AccountMappingForm:
    """Decode the JSON `account_types` multipart form field:
    {"Account Name": {"account_type": "loan", "on_budget": false, "skip": false}, ...}

    Skip and close are mutually exclusive by construction — a skipped account
    is never created, so there is nothing to close, and `skip` wins if a caller
    sends both."""
    if not account_types:
        return AccountMappingForm(
            choices={}, type_map={}, skip_accounts=set(), close_accounts=set()
        )
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
    choices = {
        name: choice.model_copy(update={"close": choice.close and not choice.skip})
        for name, choice in parsed.items()
    }
    type_map = {
        name: (choice.account_type, choice.on_budget)
        for name, choice in choices.items()
        if not choice.skip
    }
    return AccountMappingForm(
        choices=choices,
        type_map=type_map,
        skip_accounts={name for name, choice in choices.items() if choice.skip},
        close_accounts={name for name, choice in choices.items() if choice.close},
    )


def build_ynab_preview(
    ynab_budget, *, remembered: Mapping[str, RememberedChoice]
) -> "YNABPreviewResult":
    """The mapping screen's account list.

    `remembered` is keyword-only and required on purpose: a caller that forgets
    it is a TypeError at import time, never a preview that silently guesses at
    accounts this person has already mapped. Keyed by
    `domain.import_mapping.account_key`, and passed in rather than read here so
    this stays sync and pure — the route does the I/O.
    """
    counts: dict[str, int] = {}
    balances: dict[str, Decimal] = {}
    first_seen: dict[str, date] = {}
    last_seen: dict[str, date] = {}
    # Held-out rows still name their account — one that appears only in the
    # future must still be offered for mapping — but count and balance from
    # posted rows only: those are what the register will hold.
    for txn in [*ynab_budget.transactions, *ynab_budget.held_out]:
        counts.setdefault(txn.account_name, 0)
        balances.setdefault(txn.account_name, Decimal("0"))
        prev_last = last_seen.get(txn.account_name)
        if prev_last is None or txn.date > prev_last:
            last_seen[txn.account_name] = txn.date
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

    related = assign_related_groups(sorted(counts))
    accounts = []
    for name in sorted(counts):
        implied = balances.get(name, Decimal("0"))
        # An IGAB export carries the real types in Accounts.csv, a previous
        # import carries what this person chose, and a plain YNAB export
        # carries neither — one ladder, in one place.
        suggestion = resolve_account_suggestion(
            name,
            implied,
            from_export=ynab_budget.account_types.get(account_key(name)),
            remembered=remembered.get(account_key(name)),
        )
        accounts.append(
            YNABAccountPreview(
                name=name,
                transaction_count=counts[name],
                suggested_type=suggestion.account_type,
                suggested_on_budget=suggestion.on_budget,
                needs_review=suggestion.needs_review,
                implied_balance=implied,
                first_activity=first_seen.get(name),
                last_activity=last_seen.get(name),
                related_group=related.get(name),
                suggested_skip=suggestion.skip,
                suggested_close=suggestion.close,
                suggestion_source=suggestion.source,
            )
        )
    from igab.integrations.ynab.models import anchor_month
    from igab.utils.clock import today_utc

    return YNABPreviewResult(
        accounts=accounts,
        transaction_count=len(ynab_budget.transactions),
        held_out_future_count=len(ynab_budget.held_out),
        budget_entry_count=len(ynab_budget.budget_entries),
        # `anchor_month`, not `plan_boundary`: the screen promises an anchor
        # only where `_write_anchor` will write one — same predicate, one
        # spelling, so the verdict cannot outrun the import.
        anchor_month=anchor_month(ynab_budget.plan_rows, today_utc()),
    )


async def ynab_parity_or_none(
    budget_service,
    category_repo,
    budget_id: uuid.UUID,
    ynab_budget,
    *,
    type_map: dict[str, tuple[str, bool]],
    skip_accounts: set[str],
    anchor: date | None = None,
) -> YNABParityOut | None:
    """The parity line for the import summary, or None if it cannot be
    computed. A failed check must never fail the import: the budget is
    already built, and the summary without the line is still the summary."""
    import logging

    from igab.domain.dates import month_start
    from igab.integrations.ynab.models import plan_boundary
    from igab.integrations.ynab.parity import check_parity
    from igab.utils.clock import today_utc

    try:
        # The last month the export knows about, or today's if it is older —
        # the same `plan_boundary` the anchor writer and the layout seed use,
        # with a register-month fallback that is parity's own: a file with no
        # plan cannot be anchored, but its register can still be compared.
        month = plan_boundary(ynab_budget.plan_rows, today_utc())
        if month is None:
            month = month_start(today_utc())
            register_months = [month_start(t.date) for t in ynab_budget.transactions]
            if register_months:
                month = min(month, max(register_months))
        skipped = {name.lower() for name in skip_accounts}
        kept = {
            t.account_name
            for t in ynab_budget.transactions
            if t.account_name.lower() not in skipped
        }
        cards = {name for name, (kind, _) in type_map.items() if kind == "credit_card"}
        # Unmapped accounts import as on-budget checking (importer default).
        tracking = {name for name in kept if not type_map.get(name, ("checking", True))[1]}
        report = await check_parity(
            budget_service,
            category_repo,
            budget_id,
            ynab_budget,
            month,
            accounts=kept,
            credit_card_accounts=cards,
            tracking_accounts=tracking,
            anchor=anchor,
        )
    except Exception:  # noqa: BLE001 — the summary is still the summary
        logging.getLogger(__name__).exception("YNAB parity check failed")
        return None
    return YNABParityOut(
        month=report.month,
        ynab_ready_to_assign=report.ynab_ready_to_assign,
        expected_ready_to_assign=report.expected_ready_to_assign,
        igab_ready_to_assign=report.igab_ready_to_assign,
        uncovered_card_debt=report.uncovered_card_debt,
        uncategorized_net=report.uncategorized_net,
        matches=report.matches,
        categories_compared=report.categories_compared,
        categories_differing=report.categories_differing,
        categories_pending=report.categories_pending,
        categories_unmatched=report.categories_unmatched,
        top_differences=[
            YNABParityDifference(name=d.name, igab=d.igab, ynab=d.ynab, pending=d.pending)
            for d in report.top_differences
        ],
        cards_compared=report.cards_compared,
        cards_differing=report.cards_differing,
        card_differences=[
            YNABParityDifference(name=d.name, igab=d.igab, ynab=d.ynab)
            for d in report.card_differences
        ],
        card_history=[
            YNABCardHistoryOut(
                name=d.name,
                first_month=d.first_month,
                igab=d.igab,
                ynab=d.ynab,
                months_compared=d.months_compared,
                months_differing=d.months_differing,
            )
            for d in report.card_history
        ],
        ccp_available_history=report.ccp_available_history,
        consistency=YNABExportConsistencyOut(
            self_consistent=report.consistency.self_consistent,
            carryover_rows_checked=report.consistency.carryover_rows_checked,
            carryover_rows_violating=report.consistency.carryover_rows_violating,
            activity_cells_checked=report.consistency.activity_cells_checked,
            activity_cells_disagreeing=report.consistency.activity_cells_disagreeing,
        ),
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


def parse_ynab_zip_path(path, today: date):
    """Parse a YNAB-shaped zip already on disk, turning reader complaints
    into 400s. The upload wrapper below and the unified import preview both
    funnel through here — and so does the hold-out of future-dated rows,
    exactly once, so the preview promises what the import writes."""
    from igab.integrations.ynab.models import hold_out_future

    try:
        return hold_out_future(YNABParser().parse_zip(path), today)
    except (ValueError, KeyError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


async def parse_uploaded_ynab_zip(file: UploadFile, today: date):
    import tempfile
    from pathlib import Path

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        return parse_ynab_zip_path(tmp_path, today)
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


@router.get("/{budget_id}/import-summary", response_model=ImportSummaryOut)
async def get_import_summary(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ImportSummaryOut:
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    summary = (
        YNABImportResult.model_validate(budget.import_summary)
        if budget.import_summary is not None
        else None
    )
    return ImportSummaryOut(summary=summary, reviewed_at=budget.import_reviewed_at)


@router.post("/{budget_id}/import-summary/reviewed", status_code=status.HTTP_204_NO_CONTENT)
async def mark_import_reviewed(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Stamp the review as seen, so it stops opening by itself.

    Idempotent on purpose: re-stamping moves the timestamp and nothing else.
    The review stays reachable afterwards — this only governs whether it
    appears unasked.
    """
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    before = snapshot("budget", budget)
    budget.import_reviewed_at = datetime.now(UTC)
    after = snapshot("budget", budget)
    if snapshots_match(after, before):  # re-stamping records a real move only
        recorder = ChangeRecorder(session)
        recorder.actor_user_id = current_user.id
        await recorder.record(
            budget_id=budget_id,
            entity_type="budget",
            entity_id=budget_id,
            action="update",
            before=before,
            after=after,
        )
