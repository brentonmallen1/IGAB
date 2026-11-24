"""A split's lines are served and edited in place — never rebuilt.

The register lists parent rows only, so before this a split's lines were
invisible everywhere and the inline editor's save was create-new + delete
(dropping attachments, bank identity and provenance). One leg writer now
backs create_split, convert_to_split and replace_splits.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.db.models import TransactionAttachment
from igab.domain.exceptions import InvariantViolation
from igab.services.transaction_service import SplitSpec, TransactionUpdate
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


async def _setup(db_session, *, cleared="uncleared"):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    household = await create_category(db_session, budget, group, "Household")
    services = make_services(db_session)
    txn = await create_transaction(
        db_session,
        budget,
        account,
        "-100.00",
        TXN_DATE,
        cleared=cleared,
        sync_id="t-1",
        sync_source="simplefin",
    )
    parent = await services.transactions.convert_to_split(
        budget.id,
        txn.id,
        [
            SplitSpec(amount=Decimal("-60.00"), category_id=groceries.id, memo="food"),
            SplitSpec(amount=Decimal("-40.00"), category_id=household.id),
        ],
    )
    return budget, account, groceries, household, services, parent


def _by_amount(lines):
    """(the -60 'food' line, the -40 'home' line) — ids are random, so the
    listing order within one batch is not insertion order."""
    ordered = sorted(lines, key=lambda c: c.amount)  # -60, -40
    return ordered[0], ordered[1]


def _attach(db_session, txn, name="r.webp"):
    a = TransactionAttachment(
        transaction_id=txn.id,
        filename=name,
        original_filename=name,
        content_type="image/webp",
        file_size=10,
        storage_path=f"x/{txn.id}/{name}",
    )
    db_session.add(a)
    return a


async def test_lists_a_parents_lines_with_served_fields(db_session):
    budget, account, groceries, household, services, parent = await _setup(db_session)
    lines = await services.transaction_repo.get_splits(parent.id)
    # Lines written in one request share created_at; among those the order is
    # by id, so compare as a set.
    assert {c.amount for c in lines} == {Decimal("-60.00"), Decimal("-40.00")}
    assert all(isinstance(c.needs_category, bool) for c in lines)


async def test_replace_updates_creates_and_removes_lines_in_one_batch(db_session):
    budget, account, groceries, household, services, parent = await _setup(db_session)
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))

    lines = await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [
            SplitSpec(id=food.id, amount=Decimal("-50.00"), category_id=groceries.id, memo="food"),
            SplitSpec(amount=Decimal("-50.00"), category_id=household.id, memo="new"),
        ],
    )

    kept = next(c for c in lines if c.id == food.id)
    assert kept.amount == Decimal("-50.00"), "the named line kept its identity"
    fresh = next(c for c in lines if c.id != food.id)
    assert fresh.memo == "new" and fresh.parent_transaction_id == parent.id
    await db_session.refresh(home)
    assert home.is_deleted, "the unnamed line is gone"
    await db_session.refresh(parent)
    assert parent.amount == Decimal("-100.00") and parent.sync_id == "t-1"
    await assert_financial_invariants(db_session, budget.id)


async def test_replace_rejects_a_line_id_from_another_parent(db_session):
    budget, account, groceries, household, services, parent = await _setup(db_session)
    other = await create_transaction(db_session, budget, account, "-9.00", TXN_DATE)
    with pytest.raises(InvariantViolation, match="does not belong"):
        await services.transactions.replace_splits(
            budget.id,
            parent.id,
            [SplitSpec(id=other.id, amount=Decimal("-100.00"))],
        )
    await db_session.refresh(other)
    assert not other.is_deleted and other.parent_transaction_id is None


async def test_replace_rejects_unbalanced_lines(db_session):
    budget, account, groceries, household, services, parent = await _setup(db_session)
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))
    with pytest.raises(InvariantViolation):
        await services.transactions.replace_splits(
            budget.id, parent.id, [SplitSpec(id=food.id, amount=Decimal("-99.00"))]
        )
    await db_session.refresh(home)
    assert not home.is_deleted, "a refused replace writes nothing"


async def test_replace_on_a_reconciled_parent_mirrors_reconciled_onto_new_lines(db_session):
    budget, account, groceries, household, services, parent = await _setup(
        db_session, cleared="reconciled"
    )
    lines = await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [SplitSpec(amount=Decimal("-30.00")), SplitSpec(amount=Decimal("-70.00"))],
    )
    assert all(c.cleared == "reconciled" for c in lines)
    await db_session.refresh(parent)
    assert parent.cleared == "reconciled" and parent.amount == Decimal("-100.00")


async def test_replace_moves_a_removed_lines_attachments_to_the_parent(db_session):
    budget, account, groceries, household, services, parent = await _setup(db_session)
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))
    _attach(db_session, home)
    await db_session.flush()

    await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [SplitSpec(id=food.id, amount=Decimal("-60.00")), SplitSpec(amount=Decimal("-40.00"))],
    )

    assert len(await services.attachment_repo.get_for_transaction(parent.id)) == 1
    assert await services.attachment_repo.get_for_transaction(home.id) == []


async def test_undo_of_a_replace_restores_the_previous_lines(db_session):
    budget, account, groceries, household, services, parent = await _setup(db_session)
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))
    _attach(db_session, home)
    await db_session.flush()
    from sqlalchemy import select

    from igab.db.models import ChangeLog

    await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [SplitSpec(id=food.id, amount=Decimal("-55.00")), SplitSpec(amount=Decimal("-45.00"))],
    )
    await db_session.flush()
    latest = (
        (
            await db_session.execute(
                select(ChangeLog)
                .where(ChangeLog.entity_id == home.id)
                .order_by(ChangeLog.seq.desc())
            )
        )
        .scalars()
        .first()
    )
    assert latest is not None and latest.action == "delete"

    await UndoService(db_session).undo_batch(budget.id, latest.batch_id)

    lines = await services.transaction_repo.get_splits(parent.id)
    assert {c.id for c in lines} == {food.id, home.id}
    assert {c.amount for c in lines} == {Decimal("-60.00"), Decimal("-40.00")}
    assert len(await services.attachment_repo.get_for_transaction(home.id)) == 1
    await assert_financial_invariants(db_session, budget.id)


async def test_undo_may_remove_lines_under_a_reconciled_parent(db_session):
    budget, account, groceries, household, services, parent = await _setup(
        db_session, cleared="reconciled"
    )
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))
    from sqlalchemy import select

    from igab.db.models import ChangeLog

    new_line, _ = await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [SplitSpec(amount=Decimal("-70.00")), SplitSpec(amount=Decimal("-30.00"))],
    )
    await db_session.flush()
    created = (
        (await db_session.execute(select(ChangeLog).where(ChangeLog.entity_id == new_line.id)))
        .scalars()
        .first()
    )

    await UndoService(db_session).undo_batch(budget.id, created.batch_id)

    lines = await services.transaction_repo.get_splits(parent.id)
    assert {c.id for c in lines} == {food.id, home.id}
    assert all(c.cleared == "reconciled" for c in lines)


async def test_create_convert_and_replace_share_the_mirror_rule(db_session):
    """Lines carry the parent's date, cleared state and approval whichever
    path wrote them."""
    budget, account, groceries, household, services, parent = await _setup(db_session)
    await services.transactions.update(
        budget.id, parent.id, TransactionUpdate(date=date(2026, 8, 5), cleared="cleared")
    )
    lines = await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [SplitSpec(amount=Decimal("-70.00")), SplitSpec(amount=Decimal("-30.00"))],
    )
    assert lines[0].date == date(2026, 8, 5) and lines[0].cleared == "cleared"
    assert lines[0].approved == parent.approved


async def test_endpoint_round_trip_get_then_put(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    services = make_services(db_session)
    txn = await create_transaction(db_session, budget, account, "-100.00", TXN_DATE)
    parent = await services.transactions.convert_to_split(
        budget.id,
        txn.id,
        [SplitSpec(amount=Decimal("-60.00")), SplitSpec(amount=Decimal("-40.00"))],
    )

    got = await api_client.get(
        f"/api/v1/transactions/{parent.id}/splits", params={"budget_id": str(budget.id)}
    )
    assert got.status_code == 200, got.text
    lines = got.json()
    # Numbers, so this sorts numerically. The old spelling compared money
    # STRINGS, where "-40" sorts before "-60" — the same lexicographic trap
    # the wire format was springing on the client.
    assert sorted(line["amount"] for line in lines) == [-60.0, -40.0]
    assert all(isinstance(line["needs_category"], bool) for line in lines)

    put = await api_client.put(
        f"/api/v1/transactions/{parent.id}/splits",
        params={"budget_id": str(budget.id)},
        json={
            "splits": [
                {"id": lines[0]["id"], "amount": "-60.00", "category_id": str(cat.id)},
                {"amount": "-25.00"},
                {"amount": "-15.00", "memo": "tip"},
            ]
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert len(body) == 3
    kept = next(line for line in body if line["id"] == lines[0]["id"])
    assert kept["category_id"] == str(cat.id) and kept["amount"] == -60.0
    assert any(line["memo"] == "tip" and line["amount"] == -15.0 for line in body)


# --- Correcting a split's total -------------------------------------------
#
# A split's amount is its lines' sum, so `update` refuses to move it and the
# lines alone could not: a total typed in wrong was permanent short of
# deleting the split. The total now travels with the lines.


async def test_replace_corrects_the_total_with_the_lines(db_session):
    """Entered as $100, the receipt says $108: the extra goes on one line."""
    budget, account, groceries, household, services, parent = await _setup(db_session)
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))

    await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [
            SplitSpec(id=food.id, amount=Decimal("-68.00"), category_id=groceries.id),
            SplitSpec(id=home.id, amount=Decimal("-40.00"), category_id=household.id),
        ],
        total=Decimal("-108.00"),
    )

    await db_session.refresh(parent)
    assert parent.amount == Decimal("-108.00")
    assert parent.is_split and parent.sync_id == "t-1", "the row kept its identity"
    lines = await services.transaction_repo.get_splits(parent.id)
    assert {c.amount for c in lines} == {Decimal("-68.00"), Decimal("-40.00")}
    await assert_financial_invariants(db_session, budget.id)


async def test_a_corrected_total_the_lines_do_not_reach_writes_nothing(db_session):
    budget, account, groceries, household, services, parent = await _setup(db_session)
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))
    with pytest.raises(InvariantViolation, match="do not sum"):
        await services.transactions.replace_splits(
            budget.id,
            parent.id,
            [
                SplitSpec(id=food.id, amount=Decimal("-60.00"), category_id=groceries.id),
                SplitSpec(id=home.id, amount=Decimal("-40.00"), category_id=household.id),
            ],
            total=Decimal("-108.00"),
        )
    await db_session.refresh(parent)
    assert parent.amount == Decimal("-100.00")


async def test_the_same_total_is_not_a_change(db_session):
    """The editors send the total they show; an unchanged one must not trip
    the reconciled lock or write an empty update."""
    budget, account, groceries, household, services, parent = await _setup(
        db_session, cleared="reconciled"
    )
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))
    lines = await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [
            SplitSpec(id=food.id, amount=Decimal("-70.00"), category_id=groceries.id),
            SplitSpec(id=home.id, amount=Decimal("-30.00"), category_id=household.id),
        ],
        total=Decimal("-100.00"),
    )
    assert {c.amount for c in lines} == {Decimal("-70.00"), Decimal("-30.00")}


async def test_a_reconciled_splits_total_is_locked(db_session):
    budget, account, groceries, household, services, parent = await _setup(
        db_session, cleared="reconciled"
    )
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))
    with pytest.raises(InvariantViolation, match="reconciled"):
        await services.transactions.replace_splits(
            budget.id,
            parent.id,
            [
                SplitSpec(id=food.id, amount=Decimal("-68.00"), category_id=groceries.id),
                SplitSpec(id=home.id, amount=Decimal("-40.00"), category_id=household.id),
            ],
            total=Decimal("-108.00"),
        )
    await db_session.refresh(parent)
    assert parent.amount == Decimal("-100.00")


async def test_undo_of_a_corrected_total_restores_the_amount_and_the_lines(db_session):
    from sqlalchemy import select

    from igab.db.models import ChangeLog

    budget, account, groceries, household, services, parent = await _setup(db_session)
    food, home = _by_amount(await services.transaction_repo.get_splits(parent.id))
    await services.transactions.replace_splits(
        budget.id,
        parent.id,
        [
            SplitSpec(id=food.id, amount=Decimal("-68.00"), category_id=groceries.id),
            SplitSpec(id=home.id, amount=Decimal("-40.00"), category_id=household.id),
        ],
        total=Decimal("-108.00"),
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
    assert latest is not None

    await UndoService(db_session).undo_batch(budget.id, latest.batch_id)

    await db_session.refresh(parent)
    assert parent.amount == Decimal("-100.00")
    lines = await services.transaction_repo.get_splits(parent.id)
    assert {c.amount for c in lines} == {Decimal("-60.00"), Decimal("-40.00")}
    await assert_financial_invariants(db_session, budget.id)


async def test_endpoint_corrects_the_total(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    household = await create_category(db_session, budget, group, "Household")
    services = make_services(db_session)
    txn = await create_transaction(db_session, budget, account, "-100.00", TXN_DATE)
    await services.transactions.convert_to_split(
        budget.id,
        txn.id,
        [
            SplitSpec(amount=Decimal("-60.00"), category_id=groceries.id),
            SplitSpec(amount=Decimal("-40.00"), category_id=household.id),
        ],
    )
    await db_session.commit()
    params = {"budget_id": str(budget.id)}
    lines = (await api_client.get(f"/api/v1/transactions/{txn.id}/splits", params=params)).json()
    food = next(line for line in lines if line["amount"] == -60.0)
    home = next(line for line in lines if line["amount"] == -40.0)

    r = await api_client.put(
        f"/api/v1/transactions/{txn.id}/splits",
        params=params,
        json={
            "amount": "-108.00",
            "splits": [
                {"id": food["id"], "amount": "-68.00", "category_id": str(groceries.id)},
                {"id": home["id"], "amount": "-40.00", "category_id": str(household.id)},
            ],
        },
    )
    assert r.status_code == 200, r.text
    rows = (await api_client.get(f"/api/v1/accounts/{account.id}/transactions")).json()
    assert rows[0]["amount"] == -108.0
