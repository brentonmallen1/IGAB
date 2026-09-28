"""Card-bill reminders: the served payment date, and the shared dismissals.

The reminder rule itself is the client's (`frontend/src/utils/paymentDue.ts`,
`cardDueReminder`). What the server owes it is the two inputs the client
cannot know: when the card last took a payment, and which reminders somebody
in the household already dismissed.
"""

import uuid
from datetime import date
from decimal import Decimal

from .factories import (
    create_account,
    create_budget,
    create_liability,
    create_transaction,
    create_transfer,
)

TODAY = date(2026, 9, 27)


async def _card(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Everyday Checking")
    visa = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    await create_transaction(db_session, budget, visa, "-412.00", date(2026, 8, 12))
    await create_liability(
        db_session, budget, "Sapphire Visa", liability_type="credit_card", linked_account_id=visa.id
    )
    await db_session.commit()
    return budget, checking, visa


async def _last_payment(api_client, budget, today: date = TODAY):
    resp = await api_client.get(
        f"/api/v1/{budget.id}/liabilities", params={"today": today.isoformat()}
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    return rows[0]["last_payment_date"]


class TestLastPaymentDate:
    async def test_none_without_payments(self, db_session, api_client):
        budget, _, _ = await _card(db_session, api_client)
        assert await _last_payment(api_client, budget) is None

    async def test_the_latest_payment_from_cash(self, db_session, api_client):
        budget, checking, visa = await _card(db_session, api_client)
        await create_transfer(db_session, budget, checking, visa, "150.00", date(2026, 8, 29))
        await create_transfer(db_session, budget, checking, visa, "100.00", date(2026, 9, 14))
        await db_session.commit()

        assert await _last_payment(api_client, budget) == "2026-09-14"

    async def test_a_pending_payment_has_been_made(self, db_session, api_client):
        # Not POSTED, on purpose: this is a date, not a money aggregate, and a
        # payment the bank still shows as pending has been made.
        budget, checking, visa = await _card(db_session, api_client)
        await create_transfer(
            db_session, budget, checking, visa, "150.00", date(2026, 9, 25), cleared="pending"
        )
        await db_session.commit()

        assert await _last_payment(api_client, budget) == "2026-09-25"

    async def test_ignores_refunds(self, db_session, api_client):
        # A refund lowers what is owed, but nobody paid the bill with it.
        budget, checking, visa = await _card(db_session, api_client)
        await create_transfer(db_session, budget, checking, visa, "150.00", date(2026, 8, 29))
        await create_transaction(db_session, budget, visa, "38.00", date(2026, 9, 20))
        await db_session.commit()

        assert await _last_payment(api_client, budget) == "2026-08-29"

    async def test_ignores_money_from_an_off_budget_account(self, db_session, api_client):
        # The same predicate the card's envelope reads (CARD_PAYMENT_FROM_CASH):
        # a card paid off from a tracking account drew on nobody's set-aside.
        budget, _, visa = await _card(db_session, api_client)
        brokerage = await create_account(
            db_session,
            budget,
            "Cascade Point Brokerage",
            account_type="investment",
            on_budget=False,
        )
        await create_transfer(db_session, budget, brokerage, visa, "200.00", date(2026, 9, 20))
        await db_session.commit()

        assert await _last_payment(api_client, budget) is None

    async def test_a_payment_after_the_callers_today_has_not_landed(self, db_session, api_client):
        budget, checking, visa = await _card(db_session, api_client)
        await create_transfer(db_session, budget, checking, visa, "150.00", date(2026, 9, 14))
        await create_transfer(db_session, budget, checking, visa, "150.00", date(2026, 10, 2))
        await db_session.commit()

        assert await _last_payment(api_client, budget) == "2026-09-14"
        assert await _last_payment(api_client, budget, date(2026, 10, 2)) == "2026-10-02"

    async def test_none_for_a_debt_with_no_ledger(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        await create_liability(
            db_session, budget, "Harborstone Loan", manual_balance=Decimal("900")
        )
        await db_session.commit()

        assert await _last_payment(api_client, budget) is None

    async def test_every_mutation_serializes_it(self, db_session, api_client):
        # Required on the response: a path that forgot to compute it would
        # fail validation here rather than report a paid card as unpaid.
        budget, checking, visa = await _card(db_session, api_client)
        await create_transfer(db_session, budget, checking, visa, "150.00", date(2026, 8, 29))
        await db_session.commit()
        listed = (await api_client.get(f"/api/v1/{budget.id}/liabilities")).json()
        url = f"/api/v1/{budget.id}/liabilities/{listed[0]['id']}"

        resp = await api_client.patch(url, json={"payment_due_day": 3})
        assert resp.status_code == 200, resp.text
        assert resp.json()["last_payment_date"] == "2026-08-29"

        resp = await api_client.put(f"{url}/link-asset", json={"asset_id": None})
        assert resp.status_code == 200, resp.text
        assert resp.json()["last_payment_date"] == "2026-08-29"

        resp = await api_client.post(
            f"/api/v1/{budget.id}/liabilities",
            json={"name": "Harborstone Loan", "liability_type": "personal", "manual_balance": "5"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["last_payment_date"] is None


def _url(budget) -> str:
    return f"/api/v1/{budget.id}/card-due-dismissals"


async def _dismiss(api_client, budget, account_id, due_date, state="due", today="2026-09-27"):
    resp = await api_client.put(
        _url(budget),
        json={
            "account_id": str(account_id),
            "due_date": due_date,
            "state": state,
            "client_today": today,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestDismissals:
    async def test_round_trip(self, db_session, api_client):
        budget, _, visa = await _card(db_session, api_client)
        assert (await api_client.get(_url(budget))).json() == []

        returned = await _dismiss(api_client, budget, visa.id, "2026-10-03")
        listed = (await api_client.get(_url(budget))).json()

        expected = [{"account_id": str(visa.id), "due_date": "2026-10-03", "state": "due"}]
        assert returned == expected
        assert listed == expected

    async def test_due_and_past_due_are_separate(self, db_session, api_client):
        # Dismissing "due" must not hide the "past due" that follows for the
        # same date, and dismissing one date never silences the next.
        budget, _, visa = await _card(db_session, api_client)
        await _dismiss(api_client, budget, visa.id, "2026-10-03")
        rows = await _dismiss(api_client, budget, visa.id, "2026-10-03", state="past_due")

        assert {(r["due_date"], r["state"]) for r in rows} == {
            ("2026-10-03", "due"),
            ("2026-10-03", "past_due"),
        }

    async def test_prunes_dismissals_more_than_60_days_old(self, db_session, api_client):
        budget, _, visa = await _card(db_session, api_client)
        await _dismiss(api_client, budget, visa.id, "2026-07-03", today="2026-07-01")
        await _dismiss(api_client, budget, visa.id, "2026-07-29", today="2026-07-28")

        # 27 Sep less 60 days is 29 Jul: the 3 Jul one goes, the 29 Jul stays.
        rows = await _dismiss(api_client, budget, visa.id, "2026-10-03", today="2026-09-27")

        assert [r["due_date"] for r in rows] == ["2026-07-29", "2026-10-03"]

    async def test_leaves_other_guide_state_alone(self, db_session, api_client):
        budget, _, visa = await _card(db_session, api_client)
        r = await api_client.put(f"/api/v1/{budget.id}/guide/preferences", json={"checkup": False})
        assert r.status_code == 200, r.text

        await _dismiss(api_client, budget, visa.id, "2026-10-03")

        prefs = (await api_client.get(f"/api/v1/{budget.id}/guide/preferences")).json()
        assert prefs["checkup"] is False
        # The Guide reads the whole table for its progress; a dismissal key is
        # not a step and must not show up as one.
        overview = await api_client.get(f"/api/v1/{budget.id}/guide")
        assert overview.status_code == 200, overview.text
        assert overview.json()["progress"] == {}

    async def test_undo_brings_the_reminder_back(self, db_session, api_client):
        budget, _, visa = await _card(db_session, api_client)
        await _dismiss(api_client, budget, visa.id, "2026-10-03")

        r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert r.status_code == 200, r.text
        assert (r.json()["entity_type"], r.json()["action"]) == ("guide_state", "update")
        assert (await api_client.get(_url(budget))).json() == []

    async def test_undo_takes_back_the_prune_with_the_dismissal(self, db_session, api_client):
        budget, _, visa = await _card(db_session, api_client)
        await _dismiss(api_client, budget, visa.id, "2026-07-03", today="2026-07-01")
        await _dismiss(api_client, budget, visa.id, "2026-10-03", today="2026-09-27")

        r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert r.status_code == 200, r.text

        rows = (await api_client.get(_url(budget))).json()
        assert [r["due_date"] for r in rows] == ["2026-07-03"]

    async def test_refuses_an_account_from_another_budget(self, db_session, api_client):
        budget, _, _ = await _card(db_session, api_client)
        resp = await api_client.put(
            _url(budget),
            json={"account_id": str(uuid.uuid4()), "due_date": "2026-10-03", "state": "due"},
        )
        assert resp.status_code == 404

    async def test_refuses_an_unknown_state(self, db_session, api_client):
        budget, _, visa = await _card(db_session, api_client)
        resp = await api_client.put(
            _url(budget),
            json={"account_id": str(visa.id), "due_date": "2026-10-03", "state": "late"},
        )
        assert resp.status_code == 422
