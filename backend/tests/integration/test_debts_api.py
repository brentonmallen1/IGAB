"""Debts API: CRUD, mode rules, snapshots, amortization, category linking.

Pins the mutual-exclusivity rules in both directions (category ↔ account
vs. debt; debt managed vs. manual), snapshot 422 on managed debts, and
ownership 404s on every route.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Category

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_debt,
    create_transaction,
    create_user,
)


async def _refetch_category(db_session, category_id) -> Category:
    result = await db_session.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one()


class TestDebtCrud:
    async def test_create_unmanaged_and_list(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/debts",
            json={
                "name": "Family Loan",
                "debt_type": "personal",
                "interest_rate": "4.5",
                "minimum_payment": "150.00",
                "manual_balance": "3600.00",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["mode"] == "unmanaged"
        assert Decimal(str(body["current_balance"])) == Decimal("3600.00")
        assert body["baseline_payoff_date"] is not None
        assert body["has_live_projection"] is False

        listed = await api_client.get(f"/api/v1/{budget.id}/debts")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        # Creation seeds an initial snapshot so history starts immediately
        snapshots = await api_client.get(
            f"/api/v1/{budget.id}/debts/{body['id']}/amortization",
            params={"from": "origination"},
        )
        assert len(snapshots.json()["history"]) == 1

    async def test_create_managed_resolves_balance_from_account(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-9480.00", date(2026, 1, 1))

        resp = await api_client.post(
            f"/api/v1/{budget.id}/debts",
            json={
                "name": "Car Loan",
                "debt_type": "auto",
                "interest_rate": "6.25",
                "minimum_payment": "275.00",
                "linked_account_id": str(loan.id),
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["mode"] == "managed"
        assert Decimal(str(body["current_balance"])) == Decimal("9480.00")

    async def test_create_rejects_both_modes(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(db_session, budget, "Loan", account_type="loan")

        resp = await api_client.post(
            f"/api/v1/{budget.id}/debts",
            json={
                "name": "Confused",
                "debt_type": "other",
                "interest_rate": "5",
                "minimum_payment": "100.00",
                "linked_account_id": str(loan.id),
                "manual_balance": "1000.00",
            },
        )
        assert resp.status_code == 422

    async def test_account_cannot_back_two_debts(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(db_session, budget, "Loan", account_type="loan")
        await create_debt(db_session, budget, "First", linked_account_id=loan.id)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/debts",
            json={
                "name": "Second",
                "debt_type": "other",
                "interest_rate": "5",
                "minimum_payment": "100.00",
                "linked_account_id": str(loan.id),
            },
        )
        assert resp.status_code == 422

    async def test_patch_switches_managed_to_unmanaged(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(db_session, budget, "Loan", account_type="loan")
        await create_transaction(db_session, budget, loan, "-5000.00", date(2026, 1, 1))
        debt = await create_debt(db_session, budget, linked_account_id=loan.id)

        resp = await api_client.patch(
            f"/api/v1/{budget.id}/debts/{debt.id}",
            json={"linked_account_id": None, "manual_balance": "4800.00"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mode"] == "unmanaged"
        assert Decimal(str(body["current_balance"])) == Decimal("4800.00")

    async def test_patch_rejects_manual_balance_on_managed(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(db_session, budget, "Loan", account_type="loan")
        debt = await create_debt(db_session, budget, linked_account_id=loan.id)

        resp = await api_client.patch(
            f"/api/v1/{budget.id}/debts/{debt.id}",
            json={"manual_balance": "1234.00"},
        )
        assert resp.status_code == 422

    async def test_delete_unlinks_category(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        group = await create_category_group(db_session, budget, "Debt")
        category = await create_category(db_session, budget, group, "Payment")
        debt = await create_debt(db_session, budget, manual_balance=Decimal("100.00"))
        category.linked_debt_id = debt.id
        await db_session.flush()

        resp = await api_client.delete(f"/api/v1/{budget.id}/debts/{debt.id}")
        assert resp.status_code == 204

        refreshed = await _refetch_category(db_session, category.id)
        assert refreshed.linked_debt_id is None
        listed = await api_client.get(f"/api/v1/{budget.id}/debts")
        assert listed.json() == []


class TestSnapshots:
    async def test_snapshot_updates_current_balance(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        debt = await create_debt(db_session, budget, manual_balance=Decimal("5000.00"))

        resp = await api_client.post(
            f"/api/v1/{budget.id}/debts/{debt.id}/balance-snapshots",
            json={"balance": "4750.00"},
        )
        assert resp.status_code == 201, resp.text

        listed = await api_client.get(f"/api/v1/{budget.id}/debts")
        assert Decimal(str(listed.json()[0]["current_balance"])) == Decimal("4750.00")

    async def test_backdated_snapshot_does_not_regress_balance(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        debt = await create_debt(db_session, budget, manual_balance=Decimal("4000.00"))
        await api_client.post(
            f"/api/v1/{budget.id}/debts/{debt.id}/balance-snapshots",
            json={"balance": "4000.00"},
        )

        resp = await api_client.post(
            f"/api/v1/{budget.id}/debts/{debt.id}/balance-snapshots",
            json={"balance": "5000.00", "date": "2026-01-15"},
        )
        assert resp.status_code == 201

        listed = await api_client.get(f"/api/v1/{budget.id}/debts")
        assert Decimal(str(listed.json()[0]["current_balance"])) == Decimal("4000.00")

    async def test_snapshot_on_managed_debt_is_422(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(db_session, budget, "Loan", account_type="loan")
        debt = await create_debt(db_session, budget, linked_account_id=loan.id)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/debts/{debt.id}/balance-snapshots",
            json={"balance": "100.00"},
        )
        assert resp.status_code == 422


class TestAmortizationEndpoint:
    async def test_baseline_and_extra_payment(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        debt = await create_debt(
            db_session,
            budget,
            manual_balance=Decimal("1000.00"),
            interest_rate=Decimal("12.0000"),
            minimum_payment=Decimal("400.00"),
        )

        resp = await api_client.get(
            f"/api/v1/{budget.id}/debts/{debt.id}/amortization",
            params={"extra_payment": "100.00"},
        )
        assert resp.status_code == 200
        body = resp.json()

        # Hand-computed case from test_debt_math: 3 payments at 400/mo
        assert len(body["baseline_schedule"]) == 3
        assert Decimal(str(body["baseline_total_interest"])) == Decimal("18.26")
        assert not body["baseline_never_pays_off"]
        # 500/mo: 10.00 + 5.10 + 0.15 interest, still 3 payments but cheaper
        assert len(body["extra_schedule"]) == 3
        assert Decimal(str(body["extra_total_interest"])) == Decimal("15.25")
        assert body["history"] == []

    async def test_origination_history_for_managed_debt(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-1000.00", date(2026, 5, 1))
        await create_transaction(db_session, budget, loan, "200.00", date(2026, 6, 10))
        debt = await create_debt(db_session, budget, linked_account_id=loan.id)

        resp = await api_client.get(
            f"/api/v1/{budget.id}/debts/{debt.id}/amortization",
            params={"from": "origination"},
        )
        assert resp.status_code == 200
        history = resp.json()["history"]
        by_date = {p["date"]: Decimal(str(p["balance"])) for p in history}
        assert by_date["2026-05-01"] == Decimal("1000.00")
        assert by_date["2026-06-01"] == Decimal("800.00")

    async def test_never_pays_off_reported(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        debt = await create_debt(
            db_session,
            budget,
            manual_balance=Decimal("10000.00"),
            interest_rate=Decimal("24.0000"),
            minimum_payment=Decimal("100.00"),  # 200/mo interest — hopeless
        )

        resp = await api_client.get(f"/api/v1/{budget.id}/debts/{debt.id}/amortization")
        body = resp.json()
        assert body["baseline_never_pays_off"] is True
        assert body["baseline_payoff_date"] is None


class TestLinkDebt:
    async def test_link_and_unlink(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        group = await create_category_group(db_session, budget, "Debt")
        category = await create_category(db_session, budget, group, "Payment")
        debt = await create_debt(db_session, budget, manual_balance=Decimal("100.00"))

        resp = await api_client.put(
            f"/api/v1/{budget.id}/categories/{category.id}/link-debt",
            json={"debt_id": str(debt.id)},
        )
        assert resp.status_code == 200, resp.text

        refreshed = await _refetch_category(db_session, category.id)
        assert refreshed.linked_debt_id == debt.id

        resp = await api_client.put(
            f"/api/v1/{budget.id}/categories/{category.id}/link-debt",
            json={"debt_id": None},
        )
        assert resp.status_code == 200
        refreshed = await _refetch_category(db_session, category.id)
        assert refreshed.linked_debt_id is None

    async def test_rejects_category_with_linked_account(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        card = await create_account(db_session, budget, "Visa", account_type="credit_card")
        group = await create_category_group(db_session, budget, "Debt")
        category = await create_category(db_session, budget, group, "Visa Payment")
        category.linked_account_id = card.id
        await db_session.flush()
        debt = await create_debt(db_session, budget, manual_balance=Decimal("100.00"))

        resp = await api_client.put(
            f"/api/v1/{budget.id}/categories/{category.id}/link-debt",
            json={"debt_id": str(debt.id)},
        )
        assert resp.status_code == 422

    async def test_relinking_moves_the_link(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        group = await create_category_group(db_session, budget, "Debt")
        first = await create_category(db_session, budget, group, "First")
        second = await create_category(db_session, budget, group, "Second")
        debt = await create_debt(db_session, budget, manual_balance=Decimal("100.00"))
        first.linked_debt_id = debt.id
        await db_session.flush()

        resp = await api_client.put(
            f"/api/v1/{budget.id}/categories/{second.id}/link-debt",
            json={"debt_id": str(debt.id)},
        )
        assert resp.status_code == 200

        assert (await _refetch_category(db_session, first.id)).linked_debt_id is None
        assert (await _refetch_category(db_session, second.id)).linked_debt_id == debt.id


class TestOwnership:
    async def test_404_on_every_route_for_foreign_budget(self, api_client, db_session):
        stranger = await create_user(db_session)
        other_budget = await create_budget(db_session, stranger)
        debt = await create_debt(db_session, other_budget, manual_balance=Decimal("100.00"))
        group = await create_category_group(db_session, other_budget, "G")
        category = await create_category(db_session, other_budget, group, "C")

        b = other_budget.id
        cases = [
            ("get", f"/api/v1/{b}/debts", {}),
            ("post", f"/api/v1/{b}/debts", {"json": {
                "name": "X", "debt_type": "other", "interest_rate": "5",
                "minimum_payment": "10.00", "manual_balance": "100.00",
            }}),
            ("patch", f"/api/v1/{b}/debts/{debt.id}", {"json": {"name": "Y"}}),
            ("delete", f"/api/v1/{b}/debts/{debt.id}", {}),
            ("post", f"/api/v1/{b}/debts/{debt.id}/balance-snapshots", {"json": {"balance": "1.00"}}),
            ("get", f"/api/v1/{b}/debts/{debt.id}/amortization", {}),
            ("put", f"/api/v1/{b}/categories/{category.id}/link-debt", {"json": {"debt_id": None}}),
        ]
        for method, url, kwargs in cases:
            resp = await getattr(api_client, method)(url, **kwargs)
            assert resp.status_code == 404, (method, url, resp.status_code)

    async def test_404_for_debt_from_another_budget(self, api_client, db_session):
        mine = await create_budget(db_session, api_client.test_user)
        stranger = await create_user(db_session)
        other_budget = await create_budget(db_session, stranger)
        foreign_debt = await create_debt(
            db_session, other_budget, manual_balance=Decimal("100.00")
        )

        resp = await api_client.get(
            f"/api/v1/{mine.id}/debts/{foreign_debt.id}/amortization"
        )
        assert resp.status_code == 404

        missing = uuid.uuid4()
        resp = await api_client.patch(
            f"/api/v1/{mine.id}/debts/{missing}", json={"name": "X"}
        )
        assert resp.status_code == 404
