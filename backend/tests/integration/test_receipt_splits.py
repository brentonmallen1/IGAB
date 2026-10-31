"""A receipt the model split across envelopes is filed split.

The split used to be read, checked and then only offered — a button in the
desktop review — so a scan approved anywhere else landed in one envelope
whatever the receipt said. It is filed where the scan lands now, still
unapproved: the review is where a person checks it, not where it is built.

The split goes where the read's category would (`receipt_fields
.may_file_split`): a new row, the bank's uncategorized row, the scan's own
row on a fresh read — never over a category a row already has.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import CategoryGroup, Transaction
from igab.repositories.change_log_repo import ChangeLogRepository
from igab.tasks.ai_worker import process_one_job

from .factories import create_category, create_transaction
from .test_receipt_limbo import (  # noqa: F401 — fixtures are found by name
    _budget,
    _job,
    _remember,
    attachments_dir,
    extraction,
)

#: $24.00: $15.00 of plants for the garden, $9.00 of tools.
SPLIT = [{"category": "Garden", "amount": 15.00}, {"category": "Tools", "amount": 9.00}]


@pytest.fixture
async def budget(db_session, api_client, extraction):  # noqa: F811
    budget, checking, card, garden = await _budget(db_session, api_client.test_user)
    group = await db_session.get(CategoryGroup, garden.category_group_id)
    tools = await create_category(db_session, budget, group, "Tools")
    await db_session.flush()
    extraction.return_value = {**extraction.return_value, "suggested_split": SPLIT}
    return budget, checking, card, garden, tools


async def _lines(db_session, parent: Transaction) -> list[tuple[Decimal, object]]:
    rows = (
        await db_session.execute(
            select(Transaction)
            .where(Transaction.parent_transaction_id == parent.id)
            .order_by(Transaction.amount)
        )
    ).scalars()
    return [(row.amount, row.category_id) for row in rows]


async def test_a_new_row_is_filed_split_and_left_for_review(
    db_session,
    attachments_dir,  # noqa: F811
    budget,
):
    budget, checking, _, garden, tools = budget
    job = await _job(db_session, attachments_dir, budget, checking)
    await process_one_job(db_session, job)
    parent = await db_session.get(Transaction, job.transaction_id)
    assert (parent.is_split, parent.category_id, parent.approved) == (True, None, False)
    assert parent.amount == Decimal("-24.00")
    assert await _lines(db_session, parent) == [
        (Decimal("-15.00"), garden.id),
        (Decimal("-9.00"), tools.id),
    ]


async def test_a_bare_undo_does_not_take_the_scans_split_back(
    db_session,
    attachments_dir,  # noqa: F811
    budget,
):
    # create_split recorded every split as the person's own act, so the
    # worker's split would have been the next ⌘Z. It is the AI's, like the
    # unsplit rows a scan makes.
    budget, checking, *_ = budget
    job = await _job(db_session, attachments_dir, budget, checking)
    await process_one_job(db_session, job)
    assert await ChangeLogRepository(db_session).latest_live_undoable(budget.id) is None


async def test_a_split_naming_an_unknown_category_files_one_row(
    db_session,
    attachments_dir,  # noqa: F811
    budget,
    extraction,  # noqa: F811
):
    # Half a split would be a row the receipt never described.
    budget, checking, _, garden, _ = budget
    extraction.return_value = {
        **extraction.return_value,
        "suggested_split": [SPLIT[0], {"category": "Yacht", "amount": 9.00}],
    }
    job = await _job(db_session, attachments_dir, budget, checking)
    await process_one_job(db_session, job)
    txn = await db_session.get(Transaction, job.transaction_id)
    assert (txn.is_split, txn.category_id) == (False, garden.id)


async def test_the_banks_uncategorized_row_is_split_and_keeps_its_amount(
    db_session,
    attachments_dir,  # noqa: F811
    budget,
):
    budget, _, card, garden, tools = budget
    await _remember(db_session, budget, card)
    bank_row = await create_transaction(db_session, budget, card, "-24.00", date(2026, 9, 21))
    job = await _job(db_session, attachments_dir, budget)
    await process_one_job(db_session, job)
    assert job.transaction_id == bank_row.id
    await db_session.refresh(bank_row)
    assert (bank_row.is_split, bank_row.amount) == (True, Decimal("-24.00"))
    assert await _lines(db_session, bank_row) == [
        (Decimal("-15.00"), garden.id),
        (Decimal("-9.00"), tools.id),
    ]


async def test_a_bank_row_already_filed_keeps_its_category(
    db_session,
    attachments_dir,  # noqa: F811
    budget,
):
    budget, _, card, _, tools = budget
    await _remember(db_session, budget, card)
    bank_row = await create_transaction(
        db_session, budget, card, "-24.00", date(2026, 9, 21), category=tools
    )
    job = await _job(db_session, attachments_dir, budget)
    await process_one_job(db_session, job)
    await db_session.refresh(bank_row)
    assert (bank_row.is_split, bank_row.category_id) == (False, tools.id)


async def test_a_fresh_read_splits_the_scans_own_row(
    db_session,
    attachments_dir,  # noqa: F811
    budget,
):
    budget, checking, _, garden, tools = budget
    own = await create_transaction(
        db_session,
        budget,
        checking,
        "-24.00",
        date(2026, 9, 20),
        category=garden,
        approved=False,
        cleared="uncleared",
        created_via="ai_receipt",
    )
    job = await _job(db_session, attachments_dir, budget, checking)
    job.transaction_id = own.id
    await db_session.flush()
    await process_one_job(db_session, job)
    await db_session.refresh(own)
    assert (own.is_split, own.category_id) == (True, None)
    assert await _lines(db_session, own) == [
        (Decimal("-15.00"), garden.id),
        (Decimal("-9.00"), tools.id),
    ]
