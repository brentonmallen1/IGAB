"""One account's bank CSV, run through the same match ladder as the bank feed.

The file is a bank's word about transactions this account may already hold —
typed by hand, imported from another app, or synced. The import used to ask
only whether a line's import id (a hash over date, amount and payee string)
was already present. A history imported from another budgeting app carries
that app's cleaned payees ("Trader Joe's"), a bank export carries raw
descriptors ("TRADER JOE'S #552 SEATTLE WA"), so the two never collided: a
three-month export over three imported months came in as ~60 "new" rows,
nearly every one the twin of a row already there — same amount, a few days
apart.

Each line now ends in one of four outcomes:

- **already_imported** — this line's import id is held by a live row.
- **matched** — the ladder (`domain.matching.decide_match`) is confident a
  row already here is this line. Nothing is inserted. The row is confirmed by
  the bank's word — cleared, with the file's provenance — when `confirms`;
  see `file_confirms`.
- **review** — an exact-amount row is near but the ladder is not sure. The
  line is inserted and the pair queued for the review queue, exactly as the
  sync queues one.
- **new** — nothing near it.

`plan_csv_import` is called by both the preview and the import, so what the
preview promised is what lands, line by line.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal, TypedDict

from igab.db.models import Transaction
from igab.domain.bank_posting import FeedRecord
from igab.domain.csv_import import ParsedRow
from igab.domain.import_identity import disambiguate_in_batch, generate_import_id
from igab.domain.matching import (
    DEDUP_DATE_WINDOW_DAYS,
    MatchCandidate,
    decide_match,
    settles_in_strict_pass,
)
from igab.domain.merging import MergeSide
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import snapshot
from igab.services.projected_interest import ProjectedInterest
from igab.services.transaction_service import TransactionService

CsvOutcome = Literal["new", "already_imported", "matched", "review"]


@dataclass(frozen=True)
class CsvRowPlan:
    """What one parsed line of the file will do."""

    row: ParsedRow
    import_id: str
    outcome: CsvOutcome
    #: The existing row a `matched` or `review` line was paired with.
    candidate: Transaction | None = None
    score: float = 0.0
    #: A `matched` line clears its row (see `file_confirms`).
    confirms: bool = False

    @property
    def candidate_id(self) -> uuid.UUID | None:
        return self.candidate.id if self.candidate is not None else None

    @property
    def inserts(self) -> bool:
        return self.outcome in ("new", "review")


def file_confirms(row: Any) -> bool:
    """Whether a file line that matched `row` clears it.

    Only an `uncleared` row nothing bank-sourced has touched. A cleared or
    reconciled row has already been agreed with the bank, and a row the feed
    linked belongs to the feed: its next sync is what posts it, and a file
    writing provenance under it would be a second witness overwriting the
    first. Those lines still count as matched — the transaction is here —
    and the row is left exactly as it is.
    """
    return row.cleared == "uncleared" and not MergeSide.from_transaction(row).bank_sourced


def file_record(row: ParsedRow) -> FeedRecord:
    """A file line as the posting rule reads it: posted (a statement lists
    what the bank booked), no bank id, and no feed (`source=None`)."""
    descriptor = row.payee or None
    return FeedRecord(
        amount=row.amount,
        date=row.date,
        posted=True,
        payee=descriptor,
        description=descriptor,
        sync_id=None,
        source=None,
    )


def _import_ids(account_id: uuid.UUID, rows: Sequence[ParsedRow]) -> list[str]:
    """Each line's import id, twins within the file suffixed in file order —
    the same ids the insert writes, so a re-import recognises them."""
    holders: list[dict[str, str]] = [
        {"import_id": generate_import_id(account_id, r.date, r.amount, r.payee)} for r in rows
    ]
    disambiguate_in_batch(holders)
    return [h["import_id"] for h in holders]


async def plan_csv_import(
    txn_repo: TransactionRepository,
    budget_id: uuid.UUID,
    account_id: uuid.UUID,
    rows: Sequence[ParsedRow],
) -> list[CsvRowPlan]:
    """Decide every line's outcome. Reads only.

    In two passes, as the sync posts: every line that auto-matches a row on
    its own day claims it first, then the rest look wider
    (`settles_in_strict_pass`). An existing row is claimed at most once — by
    a match, a review, or by being the row a line is already imported as —
    so two identical charges on one day against one row are one match and
    one new row, never two matches.

    Candidates are offered in any bank state (`any_bank_state`): a row the
    sync already linked is exactly what a statement line most often
    describes.
    """
    import_ids = _import_ids(account_id, rows)
    held = await txn_repo.get_ids_by_import_id(budget_id, import_ids)
    consumed: set[uuid.UUID] = set(held.values())
    plans: list[CsvRowPlan | None] = [
        CsvRowPlan(row, iid, "already_imported") if iid in held else None
        for row, iid in zip(rows, import_ids, strict=True)
    ]

    for strict in (True, False):
        for index, row in enumerate(rows):
            if plans[index] is not None:
                continue
            found = await txn_repo.find_existing_match_candidates(
                account_id,
                row.amount,
                row.date,
                date_window_days=DEDUP_DATE_WINDOW_DAYS,
                exclude_ids=consumed,
                any_bank_state=True,
            )
            by_id = {txn.id: txn for txn, _ in found}
            decision = decide_match(
                row.payee or None,
                row.date,
                True,
                [MatchCandidate.from_row(txn, payee_name) for txn, payee_name in found],
            )
            if strict and not settles_in_strict_pass(decision):
                continue
            candidate = by_id.get(decision.candidate_id) if decision.candidate_id else None
            iid = import_ids[index]
            if candidate is None or decision.action == "create":
                plans[index] = CsvRowPlan(row, iid, "new")
                continue
            consumed.add(candidate.id)
            if decision.action == "auto":
                plans[index] = CsvRowPlan(
                    row,
                    iid,
                    "matched",
                    candidate,
                    decision.score,
                    confirms=file_confirms(candidate),
                )
            else:
                plans[index] = CsvRowPlan(row, iid, "review", candidate, decision.score)

    return [p for p in plans if p is not None]


class InsertRow(TypedDict):
    """One row of the bulk transaction insert.

    Typed so `r["import_id"]` narrows to str, rather than inferring a union
    of every value type the dict holds.
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
    import_description: str | None


@dataclass(frozen=True)
class CsvImportCounts:
    #: Rows written: `new` and `review` lines.
    imported: int
    already_imported: int
    matched: int
    #: Of `matched`, the rows the file cleared.
    confirmed: int
    review: int
    #: The change-log batch, or None when the import changed nothing.
    batch_id: uuid.UUID | None


async def apply_csv_plan(
    txn_service: TransactionService,
    budget_id: uuid.UUID,
    account_id: uuid.UUID,
    plans: Sequence[CsvRowPlan],
) -> CsvImportCounts:
    """Write what the plan says, as one undo batch.

    The batch id is also every inserted row's `import_batch_id`, which the
    dialog's Undo and ⌘Z both reach. Everything the import does is in it:
    the inserted rows (`import`), the rows it cleared (`update`, through
    `apply_bank_posting` — the one writer of bank-driven changes), and the
    review pairs it queued (`create`), so undo takes back all three and redo
    puts all three back. Recorded as the person's act (`source="import"`).
    """
    inserting = [p for p in plans if p.inserts]
    payee_ids = await txn_service.payee_repo.find_or_create_batch(
        budget_id, sorted({p.row.payee for p in inserting if p.row.payee})
    )
    # A category column names an EXISTING category; it never creates one. A
    # bank's idea of "Travel" is not this budget's envelope, and inventing
    # envelopes from a file is how a category list becomes unusable.
    category_ids: dict[str, uuid.UUID] = {}
    wanted = {p.row.category.lower() for p in inserting if p.row.category}
    if wanted:
        for cat in await txn_service.category_repo.get_all(budget_id):
            if cat.name.lower() in wanted:
                category_ids[cat.name.lower()] = cat.id

    batch_id = uuid.uuid4()
    inserts: list[tuple[CsvRowPlan, InsertRow]] = [
        (
            p,
            {
                "id": uuid.uuid4(),
                "budget_id": budget_id,
                "account_id": account_id,
                "date": p.row.date,
                "amount": p.row.amount,
                "payee_id": payee_ids.get(p.row.payee) if p.row.payee else None,
                "category_id": category_ids.get(p.row.category.lower()) if p.row.category else None,
                "memo": p.row.memo,
                "cleared": "cleared",
                "approved": False,
                "import_batch_id": batch_id,
                "is_split": False,
                "is_deleted": False,
                "created_via": "import",
                "import_id": p.import_id,
                # The bank's own words, kept beside the payee they resolved
                # to: what the next file — or the feed — is matched against.
                "import_description": p.row.payee or None,
            },
        )
        for p in inserting
    ]
    confirming = [p for p in plans if p.outcome == "matched" and p.confirms]

    reviews = [(p, r) for p, r in inserts if p.outcome == "review" and p.candidate is not None]
    match_repo = txn_service.match_repo
    if reviews and match_repo is None:
        # Never import a line as a plain new row when the ladder said it may
        # be a duplicate — that is the silent twin this module exists to stop.
        raise RuntimeError("CSV import needs a match repository to queue reviews")

    recorder = txn_service.changes
    with recorder.batch(batch_id=batch_id):
        await txn_service.transaction_repo.bulk_create([r for _, r in inserts])
        for _, r in inserts:
            await recorder.record(
                budget_id=budget_id,
                entity_type="transaction",
                entity_id=r["id"],
                action="import",
                after=snapshot("transaction", r),
                source="import",
            )
        for p in confirming:
            assert p.candidate is not None
            await txn_service.apply_bank_posting(
                p.candidate, file_record(p.row), confirmed=False, source="import"
            )
        for p, r in reviews:
            assert match_repo is not None and p.candidate is not None
            match = await match_repo.create(
                synced_transaction_id=r["id"],
                manual_transaction_id=p.candidate.id,
                confidence_score=p.score,
            )
            await recorder.record(
                budget_id=budget_id,
                entity_type="transaction_match",
                entity_id=match.id,
                action="create",
                after=snapshot("transaction_match", match),
                source="import",
            )
        # The inserted rows went in by bulk insert, past the service that
        # settles a loan's projected interest after each write — so settle
        # them here, in the import's own batch: a lender's interest row in
        # the file retires the projection it replaces, a payment in it
        # projects the month's interest, and undoing the import takes both
        # back. (The confirmations above settled themselves.)
        await ProjectedInterest(txn_service.session, recorder).settle(
            (account_id, r["date"]) for _, r in inserts
        )

    return CsvImportCounts(
        imported=len(inserts),
        already_imported=sum(1 for p in plans if p.outcome == "already_imported"),
        matched=sum(1 for p in plans if p.outcome == "matched"),
        confirmed=len(confirming),
        review=len(reviews),
        batch_id=batch_id if inserts or confirming else None,
    )
