"""Where a scanned receipt lands.

A receipt is scanned against an account, or against none. With none it
waits — status `unplaced`, image kept in staging, no transaction, so no
balance, envelope or Ready to Assign moves — until something says where it
belongs:

- the card that paid (`card_last4`) is on file for an account: it is placed
  there, unapproved, when it is read (`card_ending_owner`);
- the bank's own row for it already exists: the receipt goes ON that row
  rather than beside it as a duplicate (`bank_match`);
- a person picks the account, or the row, from the review list.

The worker and the place endpoint both finish through `create_in` and
`attach_to`, so a receipt placed at extraction and one placed a week later
end up the same shape.

A description (typed or dictated, job kind `nl_parse`) lands the same way,
minus what only a photo has: there is no image to keep, and no card ending
to place it by — it waits for a person, or goes on the bank's row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, AIJob, Transaction
from igab.domain.matching import DATE_WINDOW_DAYS
from igab.domain.receipt_fields import (
    CREATED_VIA,
    STUB_MEMO,
    ExistingRow,
    ReceiptRead,
    receipt_changes,
    writable_fields,
)
from igab.repositories.card_ending_repo import card_ending_owner
from igab.repositories.txn_filters import RECEIPT_CANDIDATE_ROW

if TYPE_CHECKING:
    from igab.services.ai_draft_service import AIDraft

#: A receipt scanned against no account, waiting for one. Not 'done' — the
#: retention pass deletes done jobs and their staged image with them.
UNPLACED = "unplaced"


async def open_account(
    session: AsyncSession, budget_id: uuid.UUID, account_id: uuid.UUID | None
) -> Account | None:
    if account_id is None:
        return None
    account = await session.get(Account, account_id)
    if account is None or account.budget_id != budget_id or account.is_closed:
        return None
    return account


async def card_account(
    session: AsyncSession, budget_id: uuid.UUID, last4: str | None
) -> Account | None:
    """The open account whose card paid, or None. A closed account keeps its
    endings for the record but is never somewhere a new receipt lands."""
    if not last4:
        return None
    owner = await session.scalar(card_ending_owner(budget_id, last4))
    return await open_account(session, budget_id, owner)


async def bank_match(
    session: AsyncSession,
    budget_id: uuid.UUID,
    amount: Decimal,
    on: date,
    *,
    account_id: uuid.UUID | None = None,
) -> Transaction | None:
    """The one row a receipt could be the paper for: the exact amount, dated
    within `DATE_WINDOW_DAYS` — the same window the sync's own matching uses
    for "two postings of one purchase". Two candidates is no answer; a
    receipt is never pinned to a guess."""
    window = timedelta(days=DATE_WINDOW_DAYS)
    stmt = (
        select(Transaction)
        .where(
            Transaction.budget_id == budget_id,
            RECEIPT_CANDIDATE_ROW,
            Transaction.amount == amount,
            Transaction.date.between(on - window, on + window),
        )
        .limit(2)
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    rows = list((await session.execute(stmt)).scalars().all())
    return rows[0] if len(rows) == 1 else None


async def create_in(
    svcs: dict, job: AIJob, account_id: uuid.UUID, draft: AIDraft | None
) -> Transaction:
    """A new unapproved transaction for the job's read. No draft (the read
    failed) makes the $0 stub the failure path has always made, so the entry
    is still somewhere a person can finish it."""
    from igab.services.transaction_service import TransactionCreate

    if draft is not None:
        return await svcs["drafts"].create_transaction(
            job.budget_id, account_id, draft, created_via=CREATED_VIA[job.kind]
        )
    payload = job.payload or {}
    today = (
        date.fromisoformat(payload["client_today"])
        if payload.get("client_today")
        else datetime.now(UTC).date()
    )
    return await svcs["transactions"].create(
        job.budget_id,
        TransactionCreate(
            account_id=account_id,
            date=today,
            amount=Decimal("0"),
            memo=STUB_MEMO[job.kind],
            approved=False,
            created_via=CREATED_VIA[job.kind],
        ),
    )


async def attach_to(svcs: dict, job: AIJob, txn: Transaction, draft: AIDraft | None) -> None:
    """Put the receipt on an existing row: the bank's date and amount stand,
    and only what the row is missing — a payee, a category, a memo — comes
    from the receipt (`domain.receipt_fields`)."""
    if draft is None:
        return
    await apply_read(svcs, job, txn, draft, refresh=False)


async def apply_read(
    svcs: dict, job: AIJob, txn: Transaction, draft: AIDraft, *, refresh: bool
) -> Transaction:
    """Write a read onto an existing row, under the one rule in
    `domain.receipt_fields`: `refresh` overwrites what the read resolved,
    otherwise only what the row is missing is filled. Recorded through
    TransactionService, so ⌘Z takes it back."""
    from igab.services.transaction_service import TransactionUpdate

    row = ExistingRow(
        own=txn.created_via in CREATED_VIA.values(),
        confirmed=bool(txn.approved) or txn.cleared != "uncleared",
        is_split=bool(txn.is_split),
        is_transfer=txn.transfer_id is not None,
        has_payee=txn.payee_id is not None,
        has_category=txn.category_id is not None,
        memo=txn.memo,
    )
    fields = writable_fields(row, refresh=refresh)
    txn_svc = svcs["transactions"]
    # Resolve only what may be written: resolving a payee name creates the
    # payee when it is new, and a row that keeps its own must not leave one.
    payee = (
        await txn_svc._resolve_payee(job.budget_id, None, draft.payee_name)
        if "payee_id" in fields
        else None
    )
    category_id = (
        await svcs["drafts"].resolve_category(job.budget_id, draft.category_name)
        if "category_id" in fields
        else None
    )
    read = ReceiptRead(
        date=draft.date,
        amount=draft.amount,
        payee_id=payee.id if payee is not None else None,
        category_id=category_id,
        memo=draft.memo,
    )
    changes = receipt_changes(row, read, refresh=refresh)
    if not changes:
        return txn
    return await txn_svc.update(job.budget_id, txn.id, TransactionUpdate(**changes))
