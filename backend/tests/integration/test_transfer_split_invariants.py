"""Phase 3 spec: transfer pairs and splits are guarded as units.

Transfers stay zero-sum and date-aligned; a reconciled partner locks the
pair. Split children's money fields live on the parent; parent date/cleared
propagate down; children can never be deleted individually.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.services.transaction_service import TransactionCreate, TransactionUpdate

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_user,
    make_services,
)
from .invariants import assert_financial_invariants

TODAY = date(2026, 7, 10)


async def _transfer_pair(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")
    source = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("200.00"),
            transfer_account_id=savings.id,
            cleared="cleared",
        ),
    )
    partner = await services.transaction_repo.get_or_raise(source.transfer_id)
    return services, budget, checking, savings, source, partner


async def test_edit_transfer_amount_updates_partner_zero_sum(db_session):
    services, budget, checking, savings, source, partner = await _transfer_pair(db_session)

    await services.transactions.update(
        budget.id, source.id, TransactionUpdate(amount=Decimal("-250.00"))
    )

    await db_session.refresh(partner)
    assert partner.amount == Decimal("250.00")
    assert await services.account_repo.get_balance(checking.id) == Decimal("-250.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_edit_transfer_date_propagates_to_partner(db_session):
    services, budget, checking, savings, source, partner = await _transfer_pair(db_session)

    new_date = date(2026, 7, 15)
    await services.transactions.update(budget.id, source.id, TransactionUpdate(date=new_date))

    await db_session.refresh(partner)
    assert partner.date == new_date
    await assert_financial_invariants(db_session, budget.id)


async def test_transfer_sign_flip_rejected(db_session):
    services, budget, checking, savings, source, partner = await _transfer_pair(db_session)

    with pytest.raises(InvariantViolation, match="direction"):
        await services.transactions.update(
            budget.id, source.id, TransactionUpdate(amount=Decimal("100.00"))
        )


async def test_transfer_edit_blocked_when_partner_reconciled(db_session):
    services, budget, checking, savings, source, partner = await _transfer_pair(db_session)
    await services.transaction_repo.update(partner.id, cleared="reconciled")

    with pytest.raises(InvariantViolation, match="reconciled"):
        await services.transactions.update(
            budget.id, source.id, TransactionUpdate(amount=Decimal("-300.00"))
        )


async def test_transfer_delete_blocked_when_partner_reconciled(db_session):
    services, budget, checking, savings, source, partner = await _transfer_pair(db_session)
    await services.transaction_repo.update(partner.id, cleared="reconciled")

    with pytest.raises(InvariantViolation, match="reconciled"):
        await services.transactions.delete(budget.id, source.id)

    # Pair still intact
    await db_session.refresh(source)
    assert source.is_deleted is False


async def test_transfer_delete_removes_both_legs(db_session):
    services, budget, checking, savings, source, partner = await _transfer_pair(db_session)

    await services.transactions.delete(budget.id, source.id)

    await db_session.refresh(source)
    await db_session.refresh(partner)
    assert source.is_deleted and partner.is_deleted
    assert await services.account_repo.get_balance(checking.id) == Decimal("0")
    assert await services.account_repo.get_balance(savings.id) == Decimal("0")


async def test_transfer_cannot_be_categorized(db_session):
    services, budget, checking, savings, source, partner = await _transfer_pair(db_session)
    group = await create_category_group(db_session, budget, "G")
    cat = await create_category(db_session, budget, group, "C")

    with pytest.raises(InvariantViolation, match="categorized"):
        await services.transactions.update(
            budget.id, source.id, TransactionUpdate(category_id=cat.id)
        )


async def _split(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    gas = await create_category(db_session, budget, group, "Gas")

    header = TransactionCreate(
        account_id=checking.id, date=TODAY, amount=Decimal("-100.00"), cleared="cleared"
    )
    splits = [
        TransactionCreate(
            account_id=checking.id, date=TODAY, amount=Decimal("-60.00"), category_id=groceries.id
        ),
        TransactionCreate(
            account_id=checking.id, date=TODAY, amount=Decimal("-40.00"), category_id=gas.id
        ),
    ]
    parent = await services.transactions.create_split(budget.id, header, splits)
    children = await services.transaction_repo.get_splits(parent.id)
    return services, budget, checking, parent, children, groceries, gas


async def test_split_child_money_fields_locked(db_session):
    services, budget, checking, parent, children, groceries, gas = await _split(db_session)
    child = children[0]

    for bad in (
        TransactionUpdate(amount=Decimal("-70.00")),
        TransactionUpdate(date=date(2026, 7, 11)),
        TransactionUpdate(cleared="uncleared"),
    ):
        with pytest.raises(InvariantViolation, match="parent"):
            await services.transactions.update(budget.id, child.id, bad)

    await assert_financial_invariants(db_session, budget.id)


async def test_split_child_category_and_memo_editable(db_session):
    services, budget, checking, parent, children, groceries, gas = await _split(db_session)
    child = next(c for c in children if c.category_id == groceries.id)

    await services.transactions.update(
        budget.id, child.id, TransactionUpdate(category_id=gas.id, memo="re-tagged")
    )
    await db_session.refresh(child)
    assert child.category_id == gas.id
    assert child.memo == "re-tagged"
    await assert_financial_invariants(db_session, budget.id)


async def test_split_parent_amount_edit_rejected(db_session):
    services, budget, checking, parent, children, groceries, gas = await _split(db_session)

    with pytest.raises(InvariantViolation, match="sum"):
        await services.transactions.update(
            budget.id, parent.id, TransactionUpdate(amount=Decimal("-120.00"))
        )


async def test_split_parent_date_and_cleared_propagate(db_session):
    services, budget, checking, parent, children, groceries, gas = await _split(db_session)

    new_date = date(2026, 7, 20)
    await services.transactions.update(
        budget.id, parent.id, TransactionUpdate(date=new_date, cleared="uncleared")
    )

    for child in children:
        await db_session.refresh(child)
        assert child.date == new_date
        assert child.cleared == "uncleared"
    await assert_financial_invariants(db_session, budget.id)


async def test_split_child_delete_rejected(db_session):
    services, budget, checking, parent, children, groceries, gas = await _split(db_session)

    with pytest.raises(InvariantViolation, match="parent"):
        await services.transactions.delete(budget.id, children[0].id)


async def test_split_parent_delete_removes_children(db_session):
    services, budget, checking, parent, children, groceries, gas = await _split(db_session)

    await services.transactions.delete(budget.id, parent.id)

    await db_session.refresh(parent)
    assert parent.is_deleted
    for child in children:
        await db_session.refresh(child)
        assert child.is_deleted
    assert await services.account_repo.get_balance(checking.id) == Decimal("0")


async def test_uncategorize_via_explicit_null(db_session):
    """PATCH semantics: explicit null clears category; omitted leaves it."""
    services, budget, checking, parent, children, groceries, gas = await _split(db_session)
    child = children[0]

    await services.transactions.update(
        budget.id, child.id, TransactionUpdate(category_id=None)
    )
    await db_session.refresh(child)
    assert child.category_id is None

    # An update not mentioning category must leave it alone
    await services.transactions.update(budget.id, child.id, TransactionUpdate(memo="note"))
    await db_session.refresh(child)
    assert child.category_id is None
    assert child.memo == "note"
