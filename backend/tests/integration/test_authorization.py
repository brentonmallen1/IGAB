"""Phase 7 spec: every resource-scoped endpoint 404s for another user's data.

The household will have two users; nothing may leak or mutate across them.
404 (not 403) so foreign ids don't even confirm existence.
"""

from datetime import date

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


async def _foreign_fixtures(db_session):
    """Resources owned by a DIFFERENT user than api_client's."""
    stranger = await create_user(db_session)
    budget = await create_budget(db_session, stranger)
    account = await create_account(db_session, budget, "Their Checking")
    group = await create_category_group(db_session, budget, "Their Group")
    category = await create_category(db_session, budget, group, "Their Category")
    payee = await create_payee(db_session, budget, "Their Payee")
    txn = await create_transaction(db_session, budget, account, "-10.00", TODAY)
    return budget, account, group, category, payee, txn


async def test_foreign_resources_return_404(api_client, db_session):
    budget, account, group, category, payee, txn = await _foreign_fixtures(db_session)

    checks = [
        ("get", f"/api/v1/accounts/{account.id}/transactions", None),
        ("get", f"/api/v1/{budget.id}/transactions", None),
        ("get", f"/api/v1/transactions/{txn.id}", None),
        (
            "patch",
            f"/api/v1/transactions/{txn.id}?budget_id={budget.id}",
            {"memo": "hacked"},
        ),
        ("delete", f"/api/v1/transactions/{txn.id}?budget_id={budget.id}", None),
        ("post", f"/api/v1/transactions/{txn.id}/approve", None),
        (
            "post",
            f"/api/v1/{budget.id}/transactions",
            {"account_id": str(account.id), "date": "2026-07-10", "amount": "-5.00"},
        ),
        ("get", f"/api/v1/accounts/{account.id}/reconcile/status", None),
        (
            "post",
            f"/api/v1/accounts/{account.id}/reconcile/finish",
            {"statement_balance": "0.00"},
        ),
        ("get", f"/api/v1/{budget.id}/payees", None),
        ("get", f"/api/v1/{budget.id}/payees/nearby?lat=40.0&lng=-75.0", None),
        ("delete", f"/api/v1/payees/{payee.id}", None),
        ("delete", f"/api/v1/categories/{category.id}", None),
        ("delete", f"/api/v1/category-groups/{group.id}", None),
        ("get", f"/api/v1/{budget.id}/reports/spending", None),
        ("get", f"/api/v1/budgets/{budget.id}", None),
    ]

    for method, url, body in checks:
        resp = await api_client.request(method, url, json=body)
        assert resp.status_code == 404, (
            f"{method.upper()} {url} returned {resp.status_code}; foreign "
            "resources must 404"
        )
        # Guard against vacuous passes: a mistyped route also 404s, but with
        # FastAPI's generic {"detail": "Not Found"} rather than our
        # "<Resource> not found" from the ownership dependency.
        assert resp.json()["detail"] != "Not Found", (
            f"{method.upper()} {url} hit no route at all — fix the test URL"
        )

    # The foreign transaction must be untouched by the attempted writes
    await db_session.refresh(txn)
    assert txn.memo != "hacked"
    assert txn.is_deleted is False
    assert txn.approved is True


async def test_own_resources_still_accessible(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "My Checking")
    txn = await create_transaction(db_session, budget, account, "-10.00", TODAY)

    resp = await api_client.get(f"/api/v1/transactions/{txn.id}")
    assert resp.status_code == 200

    resp = await api_client.get(f"/api/v1/accounts/{account.id}/transactions")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
