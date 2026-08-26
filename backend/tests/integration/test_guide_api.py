"""The Guide's HTTP surface, and the boundaries it must not cross."""

from datetime import date, timedelta
from decimal import Decimal

from igab.domain.dates import add_months

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_liability,
    create_transaction,
)

TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)


async def _budget(db_session, api_client):
    return await create_budget(db_session, api_client.test_user)


def _concept(payload: dict, key: str) -> dict:
    return next(c for c in payload["concepts"] if c["key"] == key)


class TestOverview:
    async def test_returns_concepts_thresholds_and_defaults(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.get(f"/api/v1/{budget.id}/guide")
        assert r.status_code == 200
        body = r.json()
        keys = {c["key"] for c in body["concepts"]}
        assert "emergency_fund" in keys
        assert body["thresholds"]["high_interest_apr"] == 10
        # Both switches default on — the roadmap is far more useful knowing
        # the numbers, and every inference is explained and reversible.
        assert body["preferences"] == {"personalization": True, "checkup": True, "wishlist": True}
        assert body["progress"] == {}

    async def test_a_concept_says_what_it_may_be_bound_to(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        body = (await api_client.get(f"/api/v1/{budget.id}/guide")).json()
        ef = next(c for c in body["concepts"] if c["key"] == "emergency_fund")
        assert set(ef["binds_to"]) == {"category", "account"}
        assert ef["allows_external"] is True
        # Debt cannot be held "elsewhere" in a way that changes the advice.
        debt = next(c for c in body["concepts"] if c["key"] == "high_interest_debt")
        assert debt["allows_external"] is False


class TestSignals:
    async def test_detects_an_emergency_fund(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Savings")
        cat = await create_category(db_session, budget, group, "Emergency Fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "1200.00")

        body = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()
        ef = _concept(body, "emergency_fund")

        assert body["personalization"] is True
        assert Decimal(ef["value"]) == Decimal("1200.00")
        assert ef["source"] == "auto"
        assert ef["reason"]

    async def test_personalization_off_runs_no_detection(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Savings")
        cat = await create_category(db_session, budget, group, "Emergency Fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "1200.00")

        await api_client.put(
            f"/api/v1/{budget.id}/guide/preferences", json={"personalization": False}
        )
        body = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()

        assert body["personalization"] is False
        ef = _concept(body, "emergency_fund")
        # Off means off: no figure, not a hidden one.
        assert ef["value"] is None
        assert ef["source"] == "off"

    async def test_an_unknown_rate_surfaces_as_a_gap(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await create_liability(
            db_session, budget, "Mystery card",
            interest_rate=None, minimum_payment=None, manual_balance=Decimal("900"),
        )
        body = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()
        assert _concept(body, "high_interest_debt")["gaps"] == ["Mystery card"]


class TestBindings:
    async def test_pointing_a_concept_at_a_category(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Savings")
        decoy = await create_category(db_session, budget, group, "Emergency Fund")
        await create_budget_assignment(db_session, budget, decoy, THIS_MONTH, "1200.00")
        real = await create_category(db_session, budget, group, "House Cushion")
        await create_budget_assignment(db_session, budget, real, THIS_MONTH, "5000.00")

        r = await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
            json={"mode": "manual", "entity_ids": {"category": [str(real.id)]}},
        )
        assert r.status_code == 204

        body = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()
        ef = _concept(body, "emergency_fund")
        assert Decimal(ef["value"]) == Decimal("5000.00")
        assert ef["source"] == "manual"

    async def test_dismissing_stops_the_claim(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
            json={"mode": "dismissed", "note": "not for me"},
        )
        ef = _concept(
            (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json(), "emergency_fund"
        )
        assert ef["tracked"] is False
        assert ef["note"] == "not for me"

    async def test_resetting_to_auto_restores_detection(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Savings")
        cat = await create_category(db_session, budget, group, "Emergency Fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "1200.00")

        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund", json={"mode": "dismissed"}
        )
        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund", json={"mode": "auto"}
        )

        ef = _concept(
            (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json(), "emergency_fund"
        )
        # This is what lets the mapping grow with them: open a real account in
        # two years, reset, and detection picks it up again.
        assert ef["tracked"] is True
        assert ef["source"] == "auto"
        assert Decimal(ef["value"]) == Decimal("1200.00")

    async def test_an_answer_is_stored_for_what_no_budget_can_know(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/employer_match",
            json={"mode": "answer", "answer": True},
        )
        match = _concept(
            (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json(), "employer_match"
        )
        assert match["source"] == "answer"
        assert match["met"] is True

    async def test_answer_mode_requires_an_answer(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/employer_match", json={"mode": "answer"}
        )
        assert r.status_code == 422

    async def test_unknown_concepts_are_rejected(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/not_a_concept", json={"mode": "auto"}
        )
        assert r.status_code == 404


class TestExternal:
    async def test_external_adds_to_what_is_in_the_budget(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Savings")
        cat = await create_category(db_session, budget, group, "Emergency Fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "1240.00")

        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
            json={
                "mode": "manual",
                "entity_ids": {"category": [str(cat.id)]},
                "external": True,
                "external_amount": "9000",
                "note": "credit union",
            },
        )
        ef = _concept(
            (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json(), "emergency_fund"
        )

        # Half here and half elsewhere is the ordinary arrangement.
        assert Decimal(ef["value"]) == Decimal("10240.00")
        assert Decimal(ef["detected_value"]) == Decimal("1240.00")
        assert Decimal(ef["external_value"]) == Decimal("9000")
        assert ef["source"] == "manual+external"
        assert ef["external_as_of"] == TODAY.isoformat()

    async def test_external_without_a_figure_still_counts_as_handled(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
            json={"mode": "external", "external": True},
        )
        ef = _concept(
            (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json(), "emergency_fund"
        )
        assert ef["external_declared"] is True
        assert ef["external_value"] is None
        # Demanding a number invites an invented one, so no figure still means
        # the step is satisfied.
        assert ef["met"] is True

    async def test_self_reported_money_never_reaches_net_worth(self, db_session, api_client):
        """The boundary that keeps the ledger a ledger.

        A self-reported figure that could move a reported balance is how the
        reports stop being derived from transactions. Asserted rather than
        assumed.
        """
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, account_type="checking")
        await create_transaction(db_session, budget, account, "500.00", TODAY)

        before = (await api_client.get(f"/api/v1/{budget.id}/reports/net-worth")).json()

        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
            json={"mode": "external", "external": True, "external_amount": "250000"},
        )

        after = (await api_client.get(f"/api/v1/{budget.id}/reports/net-worth")).json()
        assert after == before

    async def test_self_reported_money_never_reaches_the_savings_rate(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, account_type="checking")
        await create_transaction(db_session, budget, account, "5000.00", TODAY)

        before = (await api_client.get(f"/api/v1/{budget.id}/reports/savings-rate")).json()
        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
            json={"mode": "external", "external": True, "external_amount": "250000"},
        )
        after = (await api_client.get(f"/api/v1/{budget.id}/reports/savings-rate")).json()
        assert after == before


class TestCandidates:
    async def test_offers_only_the_types_a_concept_accepts(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Savings")
        await create_category(db_session, budget, group, "Emergency Fund")
        await create_account(db_session, budget, account_type="savings")
        await create_liability(db_session, budget, "Visa")

        ef = (
            await api_client.get(f"/api/v1/{budget.id}/guide/candidates/emergency_fund")
        ).json()
        assert set(ef["options"]) == {"category", "account"}
        # The picker must never offer a liability as an emergency fund.
        assert "liability" not in ef["options"]

        debt = (
            await api_client.get(f"/api/v1/{budget.id}/guide/candidates/high_interest_debt")
        ).json()
        assert set(debt["options"]) == {"liability"}


class TestPreferencesAndProgress:
    async def test_turning_personalization_off_also_turns_off_the_checkup(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(
            f"/api/v1/{budget.id}/guide/preferences", json={"personalization": False}
        )
        # Health findings are built from the same signals — a checkup left on
        # would be a switch that does nothing.
        assert r.json() == {"personalization": False, "checkup": False, "wishlist": True}

    async def test_checkup_can_be_off_on_its_own(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(f"/api/v1/{budget.id}/guide/preferences", json={"checkup": False})
        assert r.json() == {"personalization": True, "checkup": False, "wishlist": True}

    async def test_marking_and_clearing_a_step(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await api_client.put(
            f"/api/v1/{budget.id}/guide/progress/employer-match", json={"state": "done"}
        )
        body = (await api_client.get(f"/api/v1/{budget.id}/guide")).json()
        assert body["progress"] == {"employer-match": "done"}

        await api_client.put(
            f"/api/v1/{budget.id}/guide/progress/employer-match", json={"state": None}
        )
        body = (await api_client.get(f"/api/v1/{budget.id}/guide")).json()
        assert body["progress"] == {}

    async def test_an_invalid_step_state_is_rejected(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(
            f"/api/v1/{budget.id}/guide/progress/employer-match", json={"state": "finished"}
        )
        assert r.status_code == 422


class TestIsolation:
    async def test_bindings_do_not_leak_between_budgets(self, db_session, api_client):
        a = await _budget(db_session, api_client)
        b = await _budget(db_session, api_client)
        await api_client.put(
            f"/api/v1/{a.id}/guide/bindings/emergency_fund", json={"mode": "dismissed"}
        )
        other = _concept(
            (await api_client.get(f"/api/v1/{b.id}/guide/signals")).json(), "emergency_fund"
        )
        assert other["tracked"] is True


class TestCheckup:
    """The health report: one computation, three surfaces, never pushed."""

    async def test_checkup_off_returns_disabled_and_runs_nothing(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await create_liability(
            db_session, budget, "Visa",
            interest_rate=Decimal("22.9000"), manual_balance=Decimal("3410.00"),
        )
        await api_client.put(f"/api/v1/{budget.id}/guide/preferences", json={"checkup": False})

        r = await api_client.get(f"/api/v1/{budget.id}/guide/checkup")

        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        # Off means off: not an empty result over a computed one.
        assert body["metrics"] == []
        assert body["findings"] == []

    async def test_run_stamps_last_run_and_get_reads_it_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        before = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()
        assert before["last_run"] is None

        r = await api_client.post(f"/api/v1/{budget.id}/guide/checkup/run")
        assert r.status_code == 200
        stamped = r.json()["last_run"]
        assert stamped is not None

        after = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()
        assert after["last_run"] == stamped

    async def test_run_is_refused_when_reviews_are_off(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await api_client.put(f"/api/v1/{budget.id}/guide/preferences", json={"checkup": False})

        r = await api_client.post(f"/api/v1/{budget.id}/guide/checkup/run")

        # A run that does nothing must not report success.
        assert r.status_code == 409
        assert (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()[
            "last_run"
        ] is None

    async def test_high_interest_debt_outranks_a_thin_emergency_fund(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        await create_liability(
            db_session, budget, "Visa",
            interest_rate=Decimal("22.9000"), manual_balance=Decimal("3410.00"),
        )
        group = await create_category_group(db_session, budget, "Savings")
        cat = await create_category(db_session, budget, group, "Emergency Fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "200.00")

        body = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()

        kinds = [f["kind"] for f in body["findings"]]
        assert kinds[:2] == ["high_interest_debt", "ef_below_starter"]
        assert Decimal(body["findings"][0]["value"]) == Decimal("3410.00")
        assert Decimal(body["findings"][1]["value"]) == Decimal("200.00")

    async def test_funded_count_matches_the_month_endpoint(self, db_session, api_client):
        """The checkup's "funded" is the budget page's pill, by construction."""
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Bills")
        funded = await create_category(db_session, budget, group, "Rent")
        short = await create_category(db_session, budget, group, "Power")
        await create_category(db_session, budget, group, "No target")
        for cat in (funded, short):
            r = await api_client.post(
                f"/api/v1/categories/{cat.id}/target",
                json={"target_type": "monthly_funding", "target_amount": "100.00"},
            )
            assert r.status_code in (200, 201), r.text
        await create_budget_assignment(db_session, budget, funded, THIS_MONTH, "100.00")

        month = (
            await api_client.get(f"/api/v1/{budget.id}/months/{THIS_MONTH.isoformat()}")
        ).json()
        statuses = [
            b["target_status"] for b in month["category_balances"] if b["target_status"]
        ]
        body = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()
        metric = next(m for m in body["metrics"] if m["key"] == "categories_funded")

        assert Decimal(metric["value"]) == sum(1 for s in statuses if s != "underfunded") == 1
        assert Decimal(metric["target"]) == len(statuses) == 2

    async def test_chronic_count_matches_the_plan_vs_reality_report(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, account_type="checking")
        group = await create_category_group(db_session, budget, "Fun")
        dining = await create_category(db_session, budget, group, "Dining Out")
        # Over in four of the last six months: chronic by the report's rule.
        for back in range(4):
            month = add_months(THIS_MONTH, -back)
            await create_budget_assignment(db_session, budget, dining, month, "100.00")
            await create_transaction(
                db_session, budget, account, "-150.00", month, category=dining
            )

        report = (await api_client.get(f"/api/v1/{budget.id}/reports/plan-vs-reality")).json()
        body = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()

        metric = next(m for m in body["metrics"] if m["key"] == "chronic_overspend")
        finding = next(f for f in body["findings"] if f["kind"] == "chronic_overspend")
        assert report["chronic_count"] == 1
        assert Decimal(metric["value"]) == 1
        assert finding["names"] == ["Dining Out"]

    async def test_self_reported_money_can_change_a_finding_but_never_a_report(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, account_type="checking")
        await create_transaction(db_session, budget, account, "500.00", TODAY)
        group = await create_category_group(db_session, budget, "Savings")
        cat = await create_category(db_session, budget, group, "Emergency Fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "200.00")

        before = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()
        assert "ef_below_starter" in [f["kind"] for f in before["findings"]]
        net_before = (await api_client.get(f"/api/v1/{budget.id}/reports/net-worth")).json()

        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
            json={
                "mode": "manual",
                "entity_ids": {"category": [str(cat.id)]},
                "external": True,
                "external_amount": "250000",
            },
        )

        after = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()
        assert not [f for f in after["findings"] if f["kind"].startswith("ef_")]
        net_after = (await api_client.get(f"/api/v1/{budget.id}/reports/net-worth")).json()
        assert net_after == net_before


class TestScenarios:
    """The calculators: arithmetic on typed inputs, nothing persisted."""

    async def test_payoff_plan_returns_both_strategies_and_a_baseline(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/guide/scenarios/payoff-plan",
            json={
                "debts": [
                    {"key": "visa", "name": "Visa", "balance": "3410", "annual_rate": "22.9",
                     "minimum_payment": "85"},
                    {"key": "car", "name": "Car", "balance": "14200", "annual_rate": "6.4",
                     "minimum_payment": "310"},
                ],
                "extra": "200",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for key in ("avalanche", "snowball", "minimums_only"):
            assert body[key]["debt_free_date"] is not None
            assert len(body[key]["debts"]) == 2
        # Avalanche attacks the 22.9% card first; the baseline costs the most.
        assert body["avalanche"]["debts"][0]["key"] == "visa"
        assert Decimal(body["minimums_only"]["total_interest"]) >= Decimal(
            body["avalanche"]["total_interest"]
        )
        assert body["avalanche"]["months"][0]["balances"].keys() == {"visa", "car"}

    async def test_payoff_plan_rejects_an_empty_list_and_duplicate_keys(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        url = f"/api/v1/{budget.id}/guide/scenarios/payoff-plan"
        assert (await api_client.post(url, json={"debts": [], "extra": "0"})).status_code == 422
        dup = {"key": "a", "name": "A", "balance": "1", "annual_rate": "1", "minimum_payment": "1"}
        assert (await api_client.post(url, json={"debts": [dup, dup]})).status_code == 422
        bad = {**dup, "annual_rate": "-1"}
        assert (await api_client.post(url, json={"debts": [bad]})).status_code == 422

    async def test_pay_vs_save_answers_with_a_breakeven(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/guide/scenarios/pay-vs-save",
            json={"balance": "3410", "annual_rate": "22.9", "minimum_payment": "85",
                  "extra": "100", "savings_apy": "4"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["favours"] == "pay"
        assert body["breakeven_apy"] is not None
        assert body["months_sooner"] > 0

    async def test_loan_compare_needs_a_term_or_a_payment(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        url = f"/api/v1/{budget.id}/guide/scenarios/loan-compare"
        r = await api_client.post(
            url,
            json={"loans": [
                {"name": "A", "principal": "10000", "annual_rate": "6", "term_months": 12},
                {"name": "B", "principal": "10000", "annual_rate": "5", "term_months": 12,
                 "fees": "500"},
            ]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["cheapest"] == "A"
        r = await api_client.post(
            url, json={"loans": [{"name": "A", "principal": "10000", "annual_rate": "6"}]}
        )
        assert r.status_code == 422

    async def test_emergency_fund_plan_uses_the_roadmap_figures(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, account_type="checking")
        bills = await create_category_group(db_session, budget, "Bills")
        rent = await create_category(db_session, budget, bills, "Rent")
        # 3,000 of spending over the last 90 days: essentials read 1,000 a month.
        await create_transaction(
            db_session, budget, account, "-3000.00", TODAY - timedelta(days=10), category=rent
        )
        savings = await create_category_group(db_session, budget, "Savings")
        ef = await create_category(db_session, budget, savings, "Emergency Fund")
        await create_budget_assignment(db_session, budget, ef, THIS_MONTH, "240.00")
        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
            json={"mode": "manual", "entity_ids": {"category": [str(ef.id)]},
                  "external": True, "external_amount": "500"},
        )
        net_before = (await api_client.get(f"/api/v1/{budget.id}/reports/net-worth")).json()

        r = await api_client.post(
            f"/api/v1/{budget.id}/guide/scenarios/emergency-fund",
            json={"months": 3, "monthly_contribution": "500"},
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert Decimal(body["essentials_monthly"]) == Decimal("1000.00")
        # 240 in the budget plus 500 declared elsewhere — the roadmap's number.
        assert Decimal(body["current"]) == Decimal("740.00")
        assert Decimal(body["target"]) == Decimal("3000.00")
        assert Decimal(body["gap"]) == Decimal("2260.00")
        assert body["months_to_fund"] == 5  # 2260 / 500 = 4.52 → 5
        assert body["funded_by"] == add_months(TODAY, 5).isoformat()
        # And the declared 500 still reaches no report.
        net_after = (await api_client.get(f"/api/v1/{budget.id}/reports/net-worth")).json()
        assert net_after == net_before

    async def test_emergency_fund_plan_with_no_essentials_reports_unknown(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/guide/scenarios/emergency-fund",
            json={"months": 6, "monthly_contribution": "100"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["target"] is None
        assert body["months_to_fund"] is None
        assert body["months"] == 6
