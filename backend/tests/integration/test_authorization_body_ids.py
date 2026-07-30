"""IDOR regressions: body-supplied object ids must be scoped to the budget.

Route dependency guards only cover ids in the URL path. Ids passed in a request
*body* (category_id, payee_id, transfer_account_id, target_id, category_group_id,
default_category_id, scheduled account/category/payee) previously reached the DB
unchecked, letting one budget reference — or write into — another budget's
objects. Each test drives an endpoint scoped to the caller's OWN budget while
smuggling a foreign object's id in the body, and asserts it is rejected.

`api_client` is authenticated as `test_user`; `_stranger_fixtures` builds
resources under a different user. The ownership checks reject on budget_id, so a
foreign object is refused regardless of who owns it.
"""

from datetime import date

from igab.db.models import TransactionAttachment

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
)

TODAY = date(2026, 7, 10)


async def _stranger_fixtures(db_session):
    stranger = await create_user(db_session)
    budget = await create_budget(db_session, stranger)
    account = await create_account(db_session, budget, "Their Checking")
    group = await create_category_group(db_session, budget, "Their Group")
    category = await create_category(db_session, budget, group, "Their Category")
    payee = await create_payee(db_session, budget, "Their Payee")
    return budget, account, group, category, payee


async def _my_fixtures(db_session, api_client):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "My Checking")
    group = await create_category_group(db_session, budget, "My Group")
    category = await create_category(db_session, budget, group, "My Category")
    payee = await create_payee(db_session, budget, "My Payee")
    return budget, account, group, category, payee


async def test_create_transaction_rejects_foreign_category(api_client, db_session):
    _, _, _, their_category, _ = await _stranger_fixtures(db_session)
    my_budget, my_account, _, _, _ = await _my_fixtures(db_session, api_client)

    resp = await api_client.post(
        f"/api/v1/{my_budget.id}/transactions",
        json={
            "account_id": str(my_account.id),
            "date": "2026-07-10",
            "amount": "-5.00",
            "category_id": str(their_category.id),
        },
    )
    assert resp.status_code == 400


async def test_create_transaction_rejects_foreign_payee(api_client, db_session):
    _, _, _, _, their_payee = await _stranger_fixtures(db_session)
    my_budget, my_account, _, _, _ = await _my_fixtures(db_session, api_client)

    resp = await api_client.post(
        f"/api/v1/{my_budget.id}/transactions",
        json={
            "account_id": str(my_account.id),
            "date": "2026-07-10",
            "amount": "-5.00",
            "payee_id": str(their_payee.id),
        },
    )
    assert resp.status_code == 400


async def test_transfer_rejects_foreign_destination_account(api_client, db_session):
    """Finding 4: a transfer must not write a row into another budget's account."""
    their_budget, their_account, _, _, _ = await _stranger_fixtures(db_session)
    my_budget, my_account, _, _, _ = await _my_fixtures(db_session, api_client)

    resp = await api_client.post(
        f"/api/v1/{my_budget.id}/transactions",
        json={
            "account_id": str(my_account.id),
            "date": "2026-07-10",
            "amount": "-5.00",
            "transfer_account_id": str(their_account.id),
        },
    )
    assert resp.status_code == 400

    # No transaction should have landed in the stranger's account.
    resp = await api_client.get(f"/api/v1/accounts/{their_account.id}/transactions")
    assert resp.status_code == 404  # not even readable by us


async def test_update_transaction_rejects_foreign_category(api_client, db_session):
    _, _, _, their_category, _ = await _stranger_fixtures(db_session)
    my_budget, my_account, _, _, _ = await _my_fixtures(db_session, api_client)
    my_txn = await create_transaction(db_session, my_budget, my_account, "-5.00", TODAY)

    resp = await api_client.patch(
        f"/api/v1/transactions/{my_txn.id}?budget_id={my_budget.id}",
        json={"category_id": str(their_category.id)},
    )
    assert resp.status_code == 400


async def test_bulk_categorize_rejects_foreign_category(api_client, db_session):
    _, _, _, their_category, _ = await _stranger_fixtures(db_session)
    my_budget, my_account, _, _, _ = await _my_fixtures(db_session, api_client)
    my_txn = await create_transaction(db_session, my_budget, my_account, "-5.00", TODAY)

    resp = await api_client.patch(
        f"/api/v1/{my_budget.id}/transactions/bulk-categorize",
        json={"transaction_ids": [str(my_txn.id)], "category_id": str(their_category.id)},
    )
    # The bulk runner reports per-item failures rather than a top-level 400.
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == []
    assert len(body["failed"]) == 1
    # And the transaction keeps no foreign category.
    await db_session.refresh(my_txn)
    assert my_txn.category_id is None


async def test_create_category_rejects_foreign_group(api_client, db_session):
    _, _, their_group, _, _ = await _stranger_fixtures(db_session)
    my_budget, _, _, _, _ = await _my_fixtures(db_session, api_client)

    resp = await api_client.post(
        f"/api/v1/{my_budget.id}/categories",
        json={"name": "Sneaky", "category_group_id": str(their_group.id)},
    )
    assert resp.status_code == 400


async def test_update_payee_rejects_foreign_default_category(api_client, db_session):
    _, _, _, their_category, _ = await _stranger_fixtures(db_session)
    _, _, _, _, my_payee = await _my_fixtures(db_session, api_client)

    resp = await api_client.patch(
        f"/api/v1/payees/{my_payee.id}",
        json={"default_category_id": str(their_category.id)},
    )
    assert resp.status_code == 400


async def test_merge_payee_rejects_foreign_target(api_client, db_session):
    """Finding 5: merging must not re-point my transactions onto a foreign payee."""
    _, _, _, _, their_payee = await _stranger_fixtures(db_session)
    my_budget, my_account, _, _, my_payee = await _my_fixtures(db_session, api_client)
    my_txn = await create_transaction(
        db_session, my_budget, my_account, "-5.00", TODAY, payee=my_payee
    )

    resp = await api_client.post(
        f"/api/v1/payees/{my_payee.id}/merge",
        json={"target_id": str(their_payee.id)},
    )
    assert resp.status_code == 400
    # My transaction still points at my payee, and my payee is not deleted.
    await db_session.refresh(my_txn)
    assert my_txn.payee_id == my_payee.id


async def test_create_scheduled_rejects_foreign_account(api_client, db_session):
    _, their_account, _, _, _ = await _stranger_fixtures(db_session)
    my_budget, _, _, _, _ = await _my_fixtures(db_session, api_client)

    resp = await api_client.post(
        f"/api/v1/{my_budget.id}/scheduled-transactions",
        json={
            "account_id": str(their_account.id),
            "amount": "-5.00",
            "frequency": "monthly",
            "start_date": "2026-07-10",
        },
    )
    assert resp.status_code == 400


async def test_category_history_rejects_foreign_category(api_client, db_session):
    """Finding 3: history for a foreign category must not be readable."""
    _, _, _, their_category, _ = await _stranger_fixtures(db_session)
    my_budget, _, _, _, _ = await _my_fixtures(db_session, api_client)

    resp = await api_client.get(f"/api/v1/{my_budget.id}/categories/{their_category.id}/history")
    assert resp.status_code == 400

    resp = await api_client.post(
        f"/api/v1/{my_budget.id}/categories/history/batch",
        json={"category_ids": [str(their_category.id)]},
    )
    assert resp.status_code == 400


async def test_check_attachments_hides_foreign_transactions(api_client, db_session):
    """Finding 6: attachment existence must only be reported for my transactions."""
    their_budget, their_account, _, _, _ = await _stranger_fixtures(db_session)
    their_txn = await create_transaction(db_session, their_budget, their_account, "-9.00", TODAY)
    db_session.add(
        TransactionAttachment(
            transaction_id=their_txn.id,
            filename="secret.webp",
            original_filename="secret.webp",
            content_type="image/webp",
            file_size=123,
        )
    )

    my_budget, my_account, _, _, _ = await _my_fixtures(db_session, api_client)
    my_txn = await create_transaction(db_session, my_budget, my_account, "-9.00", TODAY)
    db_session.add(
        TransactionAttachment(
            transaction_id=my_txn.id,
            filename="mine.webp",
            original_filename="mine.webp",
            content_type="image/webp",
            file_size=123,
        )
    )
    await db_session.flush()

    resp = await api_client.post(
        "/api/v1/transactions/attachments/check",
        json=[str(their_txn.id), str(my_txn.id)],
    )
    assert resp.status_code == 200
    body = resp.json()
    # Mine is visible; the stranger's is masked as no-attachment.
    assert body[str(my_txn.id)] is True
    assert body[str(their_txn.id)] is False


async def test_own_body_ids_still_work(api_client, db_session):
    """Positive control: same-budget ids must still be accepted."""
    my_budget, my_account, my_group, my_category, my_payee = await _my_fixtures(
        db_session, api_client
    )

    resp = await api_client.post(
        f"/api/v1/{my_budget.id}/transactions",
        json={
            "account_id": str(my_account.id),
            "date": "2026-07-10",
            "amount": "-5.00",
            "category_id": str(my_category.id),
            "payee_id": str(my_payee.id),
        },
    )
    assert resp.status_code == 201

    resp = await api_client.post(
        f"/api/v1/{my_budget.id}/categories",
        json={"name": "Groceries", "category_group_id": str(my_group.id)},
    )
    assert resp.status_code == 201
