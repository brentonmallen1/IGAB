"""A split of one line is not a split.

The phone's split sheet used to refuse to go below two lines, and a saved
split offered no way back to one category at all: the only exit was deleting
the transaction. Now a line can be removed down to one, and whichever path
receives a single line — create, convert, or replacing a saved split's lines
— stores the row it describes: filed where the line was, with no lines.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import ChangeLog, TransactionAttachment
from igab.domain.exceptions import InvariantViolation
from igab.services.transaction_service import SplitSpec, TransactionCreate
from igab.services.undo_service import UndoService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_financial_invariants

TXN_DATE = date(2026, 8, 1)


async def _setup(db_session, *, memo=None, cleared="uncleared"):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    household = await create_category(db_session, budget, group, "Household")
    services = make_services(db_session)
    txn = await create_transaction(
        db_session, budget, account, "-100.00", TXN_DATE, memo=memo, cleared=cleared
    )
    return budget, account, groceries, household, services, txn


async def _split(services, budget, txn, groceries, household):
    return await services.transactions.convert_to_split(
        budget.id,
        txn.id,
        [
            SplitSpec(amount=Decimal("-60.00"), category_id=groceries.id, memo="food"),
            SplitSpec(amount=Decimal("-40.00"), category_id=household.id, memo="soap"),
        ],
    )


async def test_replacing_a_saved_split_with_one_line_files_the_row_there(db_session):
    budget, account, groceries, household, services, txn = await _setup(db_session)
    parent = await _split(services, budget, txn, groceries, household)
    food = next(
        c for c in await services.transaction_repo.get_splits(parent.id) if c.memo == "food"
    )

    lines = await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [SplitSpec(id=food.id, amount=Decimal("-100.00"), category_id=groceries.id, memo="food")],
    )

    assert lines == []
    await db_session.refresh(parent)
    assert parent.is_split is False
    assert parent.category_id == groceries.id
    assert parent.amount == Decimal("-100.00")
    assert await services.transaction_repo.get_splits(parent.id) == []
    await assert_financial_invariants(db_session, budget.id)


async def test_the_row_keeps_its_own_memo_and_takes_the_lines_only_when_it_has_none(db_session):
    budget, account, groceries, household, services, txn = await _setup(db_session)
    parent = await _split(services, budget, txn, groceries, household)
    await services.transactions.replace_splits(
        budget.id, parent.id, [SplitSpec(amount=Decimal("-100.00"), memo="weekly shop")]
    )
    await db_session.refresh(parent)
    assert parent.memo == "weekly shop"

    budget, account, groceries, household, services, txn = await _setup(
        db_session, memo="Costco run"
    )
    parent = await _split(services, budget, txn, groceries, household)
    await services.transactions.replace_splits(
        budget.id, parent.id, [SplitSpec(amount=Decimal("-100.00"), memo="weekly shop")]
    )
    await db_session.refresh(parent)
    assert parent.memo == "Costco run"


async def test_a_removed_lines_receipt_moves_up_to_the_row(db_session):
    budget, account, groceries, household, services, txn = await _setup(db_session)
    parent = await _split(services, budget, txn, groceries, household)
    soap = next(
        c for c in await services.transaction_repo.get_splits(parent.id) if c.memo == "soap"
    )
    db_session.add(
        TransactionAttachment(
            transaction_id=soap.id,
            filename="r.webp",
            original_filename="r.webp",
            content_type="image/webp",
            file_size=10,
            storage_path=f"x/{soap.id}/r.webp",
        )
    )
    await db_session.flush()

    await services.transactions.replace_splits(
        budget.id, parent.id, [SplitSpec(amount=Decimal("-100.00"), category_id=groceries.id)]
    )

    assert len(await services.attachment_repo.get_for_transaction(parent.id)) == 1


async def test_one_undo_brings_the_split_back(db_session):
    budget, account, groceries, household, services, txn = await _setup(db_session)
    parent = await _split(services, budget, txn, groceries, household)
    before = {c.id for c in await services.transaction_repo.get_splits(parent.id)}

    await services.transactions.replace_splits(
        budget.id, parent.id, [SplitSpec(amount=Decimal("-100.00"), category_id=groceries.id)]
    )
    await db_session.flush()
    latest = (
        (
            await db_session.execute(
                select(ChangeLog)
                .where(ChangeLog.entity_id == parent.id)
                .order_by(ChangeLog.seq.desc())
            )
        )
        .scalars()
        .first()
    )
    await UndoService(db_session).undo_batch(budget.id, latest.batch_id)

    await db_session.refresh(parent)
    assert parent.is_split is True and parent.category_id is None
    assert {c.id for c in await services.transaction_repo.get_splits(parent.id)} == before
    await assert_financial_invariants(db_session, budget.id)


async def test_a_reconciled_split_can_go_back_to_one_category(db_session):
    budget, account, groceries, household, services, txn = await _setup(
        db_session, cleared="reconciled"
    )
    parent = await _split(services, budget, txn, groceries, household)
    await services.transactions.replace_splits(
        budget.id, parent.id, [SplitSpec(amount=Decimal("-100.00"), category_id=household.id)]
    )
    await db_session.refresh(parent)
    assert parent.cleared == "reconciled" and parent.amount == Decimal("-100.00")
    assert parent.category_id == household.id and parent.is_split is False


async def test_one_line_must_still_be_the_whole_amount(db_session):
    budget, account, groceries, household, services, txn = await _setup(db_session)
    parent = await _split(services, budget, txn, groceries, household)
    with pytest.raises(InvariantViolation, match="do not sum"):
        await services.transactions.replace_splits(
            budget.id, parent.id, [SplitSpec(amount=Decimal("-90.00"), category_id=groceries.id)]
        )
    await db_session.refresh(parent)
    assert parent.is_split is True, "a refused collapse writes nothing"


async def test_converting_with_one_line_just_files_the_row(db_session):
    budget, account, groceries, household, services, txn = await _setup(db_session)
    row = await services.transactions.convert_to_split(
        budget.id,
        txn.id,
        [SplitSpec(amount=Decimal("-100.00"), category_id=household.id)],
    )
    assert row.id == txn.id
    assert row.is_split is False and row.category_id == household.id
    assert await services.transaction_repo.get_splits(row.id) == []


async def test_creating_with_one_line_creates_a_plain_row(db_session):
    budget, account, groceries, household, services, txn = await _setup(db_session)
    row = await services.transactions.create_split(
        budget.id,
        TransactionCreate(account_id=account.id, date=TXN_DATE, amount=Decimal("-25.00")),
        [
            TransactionCreate(
                account_id=account.id,
                date=TXN_DATE,
                amount=Decimal("-25.00"),
                category_id=groceries.id,
                memo="bread",
            )
        ],
    )
    assert row.is_split is False
    assert row.category_id == groceries.id and row.memo == "bread"
    assert await services.transaction_repo.get_splits(row.id) == []
    await assert_financial_invariants(db_session, budget.id)


async def test_endpoint_put_of_one_line_returns_no_lines(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    household = await create_category(db_session, budget, group, "Household")
    services = make_services(db_session)
    txn = await create_transaction(db_session, budget, account, "-100.00", TXN_DATE)
    parent = await _split(services, budget, txn, groceries, household)

    put = await api_client.put(
        f"/api/v1/transactions/{parent.id}/splits",
        params={"budget_id": str(budget.id)},
        json={"splits": [{"amount": "-100.00", "category_id": str(groceries.id)}]},
    )
    assert put.status_code == 200, put.text
    assert put.json() == []
