"""Phase 3 spec: scheduled transfers create both legs, payee category memory
is learned once (never silently overwritten), and bulk endpoints report
per-item failures instead of swallowing them."""

from datetime import date
from decimal import Decimal

from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.services.scheduled_transaction_service import (
    ScheduledTransactionService,
)
from igab.services.transaction_service import TransactionCreate, TransactionUpdate

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_financial_invariants

TODAY = date.today()


async def test_scheduled_transfer_creates_both_legs(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")

    sched_repo = ScheduledTransactionRepository(db_session)
    sched_service = ScheduledTransactionService(sched_repo, services.transactions)
    sched = await sched_repo.create(
        budget_id=budget.id,
        account_id=checking.id,
        amount=Decimal("150.00"),
        frequency="monthly",
        start_date=TODAY,
        next_occurrence_date=TODAY,
        transfer_account_id=savings.id,
    )

    await sched_service.enter_now(sched.id, budget.id)

    checking_balance = await services.account_repo.get_balance(checking.id)
    savings_balance = await services.account_repo.get_balance(savings.id)
    assert checking_balance == Decimal("-150.00")
    assert savings_balance == Decimal("150.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_payee_default_learned_once_not_overwritten(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    dining = await create_category(db_session, budget, group, "Dining")
    payee = await create_payee(db_session, budget, "Corner Market")

    # First categorization teaches the default
    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("-20.00"),
            payee_id=payee.id,
            category_id=groceries.id,
        ),
    )
    await db_session.refresh(payee)
    assert payee.default_category_id == groceries.id

    # Recategorizing one transaction must NOT poison the memory
    await services.transactions.update(
        budget.id, txn.id, TransactionUpdate(category_id=dining.id)
    )
    await db_session.refresh(payee)
    assert payee.default_category_id == groceries.id, (
        "one-off recategorization overwrote the payee default"
    )

    # New uncategorized transactions still auto-fill from the learned default
    auto = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("-25.00"),
            payee_id=payee.id,
        ),
    )
    assert auto.category_id == groceries.id


async def test_bulk_cleared_reports_per_item_failures(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    editable = await create_transaction(
        db_session, budget, account, "-10.00", TODAY, cleared="uncleared"
    )
    locked = await create_transaction(
        db_session, budget, account, "-20.00", TODAY, cleared="reconciled"
    )

    resp = await api_client.patch(
        f"/api/v1/{budget.id}/transactions/bulk-cleared",
        json={
            "transaction_ids": [str(editable.id), str(locked.id)],
            "cleared": "cleared",
        },
    )

    assert resp.status_code == 200
    result = resp.json()
    assert [str(editable.id)] == result["updated"]
    assert len(result["failed"]) == 1
    assert result["failed"][0]["id"] == str(locked.id)
    assert "reconciled" in result["failed"][0]["reason"]

    await db_session.refresh(editable)
    assert editable.cleared == "cleared"


async def test_unreconcile_endpoint(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    locked = await create_transaction(
        db_session, budget, account, "-20.00", TODAY, cleared="reconciled"
    )

    resp = await api_client.post(
        f"/api/v1/transactions/{locked.id}/unreconcile",
        params={"budget_id": str(budget.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["cleared"] == "cleared"

    # Second call: no longer reconciled → 400 with a clear message
    resp = await api_client.post(
        f"/api/v1/transactions/{locked.id}/unreconcile",
        params={"budget_id": str(budget.id)},
    )
    assert resp.status_code == 400
