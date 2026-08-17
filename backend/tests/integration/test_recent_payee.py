"""Tests for TransactionRepository.get_most_recent_payee_for_category.

Powers the add-transaction payee prefill when adding from a category row.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from igab.repositories.transaction_repo import TransactionRepository

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
)


async def _setup(db_session: AsyncSession):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget)
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group)
    return budget, account, group, category


async def test_returns_most_recent_payee_by_date(db_session: AsyncSession):
    budget, account, _, category = await _setup(db_session)
    older = await create_payee(db_session, budget, "Old Grocer")
    newer = await create_payee(db_session, budget, "New Grocer")
    await create_transaction(
        db_session, budget, account, "-10.00", date(2026, 1, 5), category=category, payee=older
    )
    await create_transaction(
        db_session, budget, account, "-20.00", date(2026, 2, 5), category=category, payee=newer
    )

    result = await TransactionRepository(db_session).get_most_recent_payee_for_category(
        budget.id, category.id
    )

    assert result is not None
    assert result[0] == newer.id
    assert result[1] == "New Grocer"


async def test_ignores_other_categories_and_deleted(db_session: AsyncSession):
    budget, account, group, category = await _setup(db_session)
    other_category = await create_category(db_session, budget, group)
    right = await create_payee(db_session, budget, "Right Payee")
    wrong_cat = await create_payee(db_session, budget, "Wrong Category")
    deleted = await create_payee(db_session, budget, "Deleted Txn")
    await create_transaction(
        db_session, budget, account, "-10.00", date(2026, 1, 5), category=category, payee=right
    )
    await create_transaction(
        db_session,
        budget,
        account,
        "-20.00",
        date(2026, 2, 5),
        category=other_category,
        payee=wrong_cat,
    )
    await create_transaction(
        db_session,
        budget,
        account,
        "-30.00",
        date(2026, 3, 5),
        category=category,
        payee=deleted,
        is_deleted=True,
    )

    result = await TransactionRepository(db_session).get_most_recent_payee_for_category(
        budget.id, category.id
    )

    assert result is not None
    assert result[0] == right.id


async def test_excludes_transfer_payees(db_session: AsyncSession):
    budget, account, _, category = await _setup(db_session)
    other_account = await create_account(db_session, budget)
    merchant = await create_payee(db_session, budget, "Merchant")
    transfer = await create_payee(db_session, budget, "Transfer : Savings")
    transfer.transfer_account_id = other_account.id
    await db_session.flush()
    await create_transaction(
        db_session, budget, account, "-10.00", date(2026, 1, 5), category=category, payee=merchant
    )
    await create_transaction(
        db_session,
        budget,
        account,
        "-500.00",
        date(2026, 2, 5),
        category=category,
        payee=transfer,
    )

    result = await TransactionRepository(db_session).get_most_recent_payee_for_category(
        budget.id, category.id
    )

    assert result is not None
    assert result[0] == merchant.id


async def test_none_when_no_payee_transactions(db_session: AsyncSession):
    budget, account, _, category = await _setup(db_session)
    # A transaction with no payee at all must not produce a result
    await create_transaction(
        db_session, budget, account, "-10.00", date(2026, 1, 5), category=category
    )

    result = await TransactionRepository(db_session).get_most_recent_payee_for_category(
        budget.id, category.id
    )

    assert result is None
