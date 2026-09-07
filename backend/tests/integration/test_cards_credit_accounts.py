"""Card limits and utilization, credit scores, and encrypted account numbers.

Fixtures are invented and rescaled: Sapphire Visa owes $2,690 on a $6,000
limit (44.8%), Harborstone Card owes $3,900 on $6,000 (65%).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.credit import utilization_percent
from igab.guide.findings import CheckupInputs, evaluate
from igab.services.account_hygiene import CARD_QUIET_DAYS, AccountHygieneService
from igab.utils.clock import today_utc

from .factories import (
    create_account,
    create_budget,
    create_liability,
    create_transaction,
)


class TestUtilization:
    def test_the_rule(self):
        assert utilization_percent(Decimal("2690"), Decimal("6000")) == Decimal("44.8")
        assert utilization_percent(Decimal("-20"), Decimal("6000")) == Decimal("0.0")
        assert utilization_percent(Decimal("100"), None) is None
        assert utilization_percent(Decimal("100"), Decimal("0")) is None

    async def test_served_on_the_liability_with_its_limit(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        liability = await create_liability(db_session, budget, name="Sapphire Visa")
        await db_session.commit()
        r = await api_client.patch(
            f"/api/v1/{budget.id}/liabilities/{liability.id}",
            json={"credit_limit": "6000.00", "manual_balance": "2690.00"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert Decimal(str(body["credit_limit"])) == Decimal("6000.00")
        assert Decimal(str(body["utilization"])) == Decimal("44.8")

    def test_the_checkup_names_a_card_over_the_thresholds(self):
        base = dict(
            signals={},
            essentials_monthly=None,
            chronic_count=0,
            chronic_names=[],
            funded=0,
            with_targets=0,
            unknown_rate_names=[],
            today=date(2026, 9, 6),
        )
        findings = evaluate(
            CheckupInputs(
                **base,
                card_utilization=[
                    ("Sapphire Visa", Decimal("44.8")),
                    ("Harborstone Card", Decimal("65.0")),
                    ("Cascade Card", Decimal("12.0")),
                ],
            )
        )
        kinds = [(f.kind, f.title) for f in findings]
        assert (
            "card_utilization_very_high",
            "Harborstone Card is using 65.0% of its limit",
        ) in kinds
        assert ("card_utilization_high", "Sapphire Visa is using 44.8% of its limit") in kinds
        assert all("Cascade" not in t for _, t in kinds)
        # The severe one sorts before the mild one.
        assert [k for k, _ in kinds] == ["card_utilization_very_high", "card_utilization_high"]

    def test_no_limit_means_no_finding(self):
        findings = evaluate(
            CheckupInputs(
                signals={},
                essentials_monthly=None,
                chronic_count=0,
                chronic_names=[],
                funded=0,
                with_targets=0,
                unknown_rate_names=[],
                today=date(2026, 9, 6),
            )
        )
        assert findings == []


class TestCardNoActivity:
    async def test_a_quiet_card_is_named_and_a_fresh_one_is_not(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        quiet = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card"
        )
        active = await create_account(
            db_session, budget, "Harborstone Card", account_type="credit_card"
        )
        fresh = await create_account(db_session, budget, "New Card", account_type="credit_card")
        await create_transaction(
            db_session, budget, quiet, "-40.00", today_utc() - timedelta(days=CARD_QUIET_DAYS + 5)
        )
        await create_transaction(
            db_session, budget, active, "-12.00", today_utc() - timedelta(days=3)
        )
        await db_session.commit()

        report = await AccountHygieneService(db_session).run(budget.id)
        finding = next(f for f in report.findings if f.kind == "card_no_activity")
        assert finding.account_ids == [quiet.id]
        assert "Sapphire Visa" in finding.title
        assert fresh.id not in finding.account_ids


class TestCreditScores:
    async def test_crud_round_trip_and_undo(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/credit-scores",
            json={"recorded_on": "2026-08-01", "score": 742, "bureau": "experian"},
        )
        assert r.status_code == 201, r.text
        score_id = r.json()["id"]
        r = await api_client.post(
            f"/api/v1/{budget.id}/credit-scores",
            json={"recorded_on": "2026-08-01", "score": 750, "bureau": "experian"},
        )
        assert r.status_code == 409
        r = await api_client.patch(
            f"/api/v1/{budget.id}/credit-scores/{score_id}",
            json={"score": 748, "note": "after paydown"},
        )
        assert r.status_code == 200 and r.json()["score"] == 748
        listed = (await api_client.get(f"/api/v1/{budget.id}/credit-scores")).json()
        assert [s["score"] for s in listed] == [748]

        r = await api_client.delete(f"/api/v1/{budget.id}/credit-scores/{score_id}")
        assert r.status_code == 204
        assert (await api_client.get(f"/api/v1/{budget.id}/credit-scores")).json() == []
        undone = (await api_client.post(f"/api/v1/{budget.id}/changes/undo")).json()
        assert (undone["entity_type"], undone["action"]) == ("credit_score", "delete")
        listed = (await api_client.get(f"/api/v1/{budget.id}/credit-scores")).json()
        assert [s["id"] for s in listed] == [score_id]

    async def test_out_of_range_scores_are_refused(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/credit-scores", json={"recorded_on": "2026-08-01", "score": 99}
        )
        assert r.status_code == 422


class TestAccountSecrets:
    @pytest.fixture(autouse=True)
    def _key(self, monkeypatch):
        from cryptography.fernet import Fernet

        from igab import config

        monkeypatch.setattr(
            config.settings, "SIMPLEFIN_ENCRYPTION_KEY", Fernet.generate_key().decode()
        )

    async def test_numbers_are_stored_encrypted_and_served_only_on_demand(
        self, db_session, api_client
    ):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        await db_session.commit()
        r = await api_client.patch(
            f"/api/v1/accounts/{checking.id}",
            json={"account_number": "000123456789", "routing_number": "011000015"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["account_number_last4"] == "6789"
        assert body["has_routing_number"] is True
        assert "account_number" not in body and "routing_number" not in body

        await db_session.refresh(checking)
        assert checking.account_number_encrypted not in (None, "000123456789")
        assert "000123456789" not in checking.account_number_encrypted

        r = await api_client.get(f"/api/v1/accounts/{checking.id}/secrets")
        assert r.status_code == 200, r.text
        assert r.json() == {"account_number": "000123456789", "routing_number": "011000015"}

        # Never in the change log.
        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()
        dumped = str(changes)
        assert "000123456789" not in dumped and "6789" not in dumped

    async def test_null_clears(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        await db_session.commit()
        await api_client.patch(f"/api/v1/accounts/{checking.id}", json={"account_number": "1234"})
        r = await api_client.patch(f"/api/v1/accounts/{checking.id}", json={"account_number": None})
        assert r.json()["account_number_last4"] is None
        assert (await api_client.get(f"/api/v1/accounts/{checking.id}/secrets")).json()[
            "account_number"
        ] is None

    async def test_without_a_key_the_server_says_so(self, db_session, api_client, monkeypatch):
        from igab import config

        monkeypatch.setattr(config.settings, "SIMPLEFIN_ENCRYPTION_KEY", "")
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        await db_session.commit()
        r = await api_client.patch(
            f"/api/v1/accounts/{checking.id}", json={"account_number": "1234"}
        )
        assert r.status_code == 503
