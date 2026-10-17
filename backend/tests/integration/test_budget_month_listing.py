"""The listing's `budget_month` and `card_reserving` filters — the lists behind
an envelope's Activity and a card's Set aside.

Activity buckets by `txn_filters.BUDGET_MONTH`, not by calendar date: a late
arrival dated in the import month B−1 counts in B. The Activity peek asked for
a calendar window, so on the month after an import the figure counted a row
the list behind it did not show, and the month before listed a row its figure
never counted. Built on the hand-made anchored budget (B−1 = June, B = July).
"""

from datetime import date
from decimal import Decimal

from igab.services.transaction_service import TransactionCreate

from .anchored_budget import build_anchored_budget

JUN, JUL = date(2026, 6, 1), date(2026, 7, 1)
D = Decimal


async def _list(api_client, budget, **params) -> dict:
    resp = await api_client.get(
        f"/api/v1/{budget.id}/transactions", params={"scope": "leaf", **params}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _late(b, account, amount: str, category, day=date(2026, 6, 28)):
    """A row typed in after the import, dated in B−1 — a late arrival."""
    return await b.services.transactions.create(
        b.budget.id,
        TransactionCreate(
            account_id=account.id,
            date=day,
            amount=D(amount),
            category_id=category.id,
            cleared="cleared",
        ),
    )


async def test_the_activity_list_holds_a_late_arrival_where_activity_counts_it(
    db_session, api_client
):
    """A 40 grocery run dated June 28, typed in after the import, is July's
    Activity. The list behind July's figure has it and totals the figure;
    June's list does not, though the row is dated in June. The calendar
    window the peek used to ask for got both of those backwards."""
    b = await build_anchored_budget(db_session, user=api_client.test_user)
    late = await _late(b, b.checking, "-40.00", b.groceries)

    july = await _list(
        api_client, b.budget, category_ids=str(b.groceries.id), budget_month=JUL.isoformat()
    )
    assert [t["id"] for t in july["transactions"]] == [str(late.id)]
    summary = await b.services.budgets.get_budget_summary(b.budget.id, JUL)
    activity = next(
        c.activity for c in summary.category_balances if c.category_id == b.groceries.id
    )
    assert D(str(july["total_amount"])) == activity == D("-40")

    june = await _list(
        api_client, b.budget, category_ids=str(b.groceries.id), budget_month=JUN.isoformat()
    )
    assert str(late.id) not in {t["id"] for t in june["transactions"]}

    # The calendar window, for contrast: it puts the row in June.
    calendar = await _list(
        api_client,
        b.budget,
        category_ids=str(b.groceries.id),
        start_date="2026-06-01",
        end_date="2026-06-30",
    )
    assert str(late.id) in {t["id"] for t in calendar["transactions"]}


async def test_a_late_card_charge_reserves_in_the_month_the_list_names(db_session, api_client):
    """The same on a card: a 30 Dining charge dated June 28 and typed in late
    reserves in July, so July's card-reserve list carries it."""
    b = await build_anchored_budget(db_session, user=api_client.test_user)
    late = await _late(b, b.visa, "-30.00", b.dining)

    july = await _list(
        api_client,
        b.budget,
        card_reserving="true",
        account_ids=str(b.visa.id),
        budget_month=JUL.isoformat(),
    )
    assert [t["id"] for t in july["transactions"]] == [str(late.id)]
    assert D(str(july["total_amount"])) == D("-30")


async def test_card_reserving_leaves_out_what_no_envelope_claims(db_session, api_client):
    """Only a spending envelope's rows: a payment from checking and a charge
    filed nowhere move the card, and neither is in the list. A cash row filed
    to Groceries is not on a card at all."""
    b = await build_anchored_budget(db_session, user=api_client.test_user)
    filed = await b.services.transactions.create(
        b.budget.id,
        TransactionCreate(
            account_id=b.visa.id,
            date=date(2026, 7, 5),
            amount=D("-25.00"),
            category_id=b.dining.id,
            cleared="cleared",
        ),
    )
    await b.services.transactions.create(
        b.budget.id,
        TransactionCreate(
            account_id=b.visa.id, date=date(2026, 7, 6), amount=D("-60.00"), cleared="cleared"
        ),
    )
    await b.services.transactions.create(
        b.budget.id,
        TransactionCreate(
            account_id=b.checking.id,
            date=date(2026, 7, 7),
            amount=D("-15.00"),
            category_id=b.groceries.id,
            cleared="cleared",
        ),
    )

    listed = await _list(
        api_client,
        b.budget,
        card_reserving="true",
        account_ids=str(b.visa.id),
        budget_month=JUL.isoformat(),
    )
    assert [t["id"] for t in listed["transactions"]] == [str(filed.id)]


async def test_budget_month_must_be_a_month(db_session, api_client):
    b = await build_anchored_budget(db_session, user=api_client.test_user)
    resp = await api_client.get(
        f"/api/v1/{b.budget.id}/transactions", params={"budget_month": "2026-07-15"}
    )
    assert resp.status_code == 422


async def test_card_reserving_refuses_parent_rows(db_session, api_client):
    """A split parent carries no category, so on parent scope the list would
    drop every split charge and come up short of the figure — refused rather
    than served short."""
    b = await build_anchored_budget(db_session, user=api_client.test_user)
    resp = await api_client.get(
        f"/api/v1/{b.budget.id}/transactions",
        params={"card_reserving": "true", "scope": "parent"},
    )
    assert resp.status_code == 422
