"""The savings-rate dialog's contributors must add up to the card that opened it.

Asked for as "the savings rate card in reports should have an info modal or
something that indicates what's contributed to that rate value". A breakdown
that does not sum to the figure beside it is worse than none — it is a second
number the household has to reconcile by hand — so every test here is an
agreement test: the parts against their totals, and the totals against the
Overview card (`dashboard_metrics`) and the Savings Rate tab (`savings_rate`)
over the same rows.

Names are invented; amounts carry cents so a float anywhere in the chain
would show.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.activity_class import (
    REASON_LABEL,
    REASON_PRIORITY,
    REASON_TEXT,
    ActivityReason,
)
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_basics import NO_PAYEE, savings_contributors
from igab.services.report_service import ReportService
from tests.report_clock import report_today

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_transfer,
    create_user,
)

#: Mid-month, so a row later this month is a future-dated row the cards leave out.
TODAY = date(2026, 3, 15)
MONTH_START = date(2026, 3, 1)
MONTH_END = date(2026, 3, 31)


@pytest.fixture(autouse=True)
def _pinned_clock():
    with report_today(TODAY):
        yield


async def _tag(db_session, budget, category, key: str) -> None:
    tags = TagRepository(db_session)
    tag = await tags.get_system_tag(budget.id, key)
    await tags.set_category_tags(category.id, [tag.id])


async def _world(db_session) -> dict:
    """One budget holding every kind of row the dialog has to place or leave out."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await seed_system_tags(db_session, budget.id)
    w: dict = {"budget": budget}
    w["checking"] = await create_account(db_session, budget, "Checking", on_budget=True)
    w["buffer"] = await create_account(db_session, budget, "Buffer Savings", on_budget=True)
    w["hysa"] = await create_account(
        db_session, budget, "Cascade Point HYSA", account_type="savings", on_budget=False
    )
    w["brokerage"] = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    w["reserve"] = await create_account(
        db_session, budget, "Rainy Day Reserve", account_type="savings", on_budget=False
    )
    w["mortgage"] = await create_account(
        db_session, budget, "Harborstone Mortgage", account_type="mortgage", on_budget=False
    )
    everyday = await create_category_group(db_session, budget, "Everyday")
    goals = await create_category_group(db_session, budget, "Goals")
    w["groceries"] = await create_category(db_session, budget, everyday, "Groceries")
    w["vacation"] = await create_category(db_session, budget, goals, "Vacation Fund")
    w["to_hysa"] = await create_category(db_session, budget, goals, "Emergency Fund")
    w["housing"] = await create_category(db_session, budget, everyday, "Mortgage")
    w["student_loan"] = await create_category(db_session, budget, goals, "Student Loan")
    await _tag(db_session, budget, w["vacation"], "savings")
    await _tag(db_session, budget, w["to_hysa"], "savings")
    await _tag(db_session, budget, w["student_loan"], "debt_principal")
    w["payroll"] = await create_payee(db_session, budget, "Northwind Payserv")
    return w


async def _seed_month(db_session, w: dict, day: date) -> None:
    """Income 5,250.10; savings 1,834.20 across four destinations, one of them
    negative; debt principal 1,300.55; and three kinds of row that must not
    count. Written out so the expected figures below can be checked on paper."""
    b, checking = w["budget"], w["checking"]
    # Income: a paycheque and a payee-less deposit.
    await create_transaction(db_session, b, checking, "5000.00", day, payee=w["payroll"])
    await create_transaction(db_session, b, checking, "250.10", day)
    # An uncategorized transfer to a brokerage: saving, named by the account.
    await create_transfer(db_session, b, checking, w["brokerage"], "1000.00", day)
    # A savings-tagged envelope spent with no transfer: saving, named by category.
    await create_transaction(db_session, b, checking, "-310.25", day, category=w["vacation"])
    # The HYSA reached two ways — through a tagged envelope and bare — is one
    # destination, and the tag's rule speaks for it.
    await create_transfer(db_session, b, checking, w["hysa"], "400.00", day, category=w["to_hysa"])
    await create_transfer(db_session, b, checking, w["hysa"], "274.15", day)
    # Money drawn back out of tracked savings: a negative contributor.
    await create_transfer(db_session, b, w["reserve"], checking, "150.20", day)
    # Debt principal: a categorized transfer to the mortgage, and a tagged envelope.
    await create_transfer(
        db_session, b, checking, w["mortgage"], "1200.30", day, category=w["housing"]
    )
    await create_transaction(db_session, b, checking, "-100.25", day, category=w["student_loan"])
    # Not counted: spending, a move between two budget accounts, and market
    # growth inside the brokerage.
    await create_transaction(db_session, b, checking, "-812.40", day, category=w["groceries"])
    await create_transfer(db_session, b, checking, w["buffer"], "500.00", day)
    await create_transaction(db_session, b, w["brokerage"], "75.33", day)


def _by_name(contributors: list[dict]) -> dict[str, dict]:
    return {c["name"]: c for c in contributors}


def _assert_parts_sum(data: dict) -> None:
    assert sum((c["total"] for c in data["savings_contributors"]), Decimal("0")) == data["savings"]
    assert (
        sum((c["total"] for c in data["debt_contributors"]), Decimal("0")) == data["debt_principal"]
    )
    assert sum((s["total"] for s in data["income_sources"]), Decimal("0")) == data["income"]


class TestWhereTheSavingsWent:
    async def test_each_destination_is_named_with_its_rule(self, db_session):
        w = await _world(db_session)
        await _seed_month(db_session, w, date(2026, 3, 10))

        data = await savings_contributors(db_session, w["budget"].id, MONTH_START, MONTH_END)

        assert data["income"] == Decimal("5250.10")
        assert data["savings"] == Decimal("1834.20")
        assert data["debt_principal"] == Decimal("1300.55")
        _assert_parts_sum(data)

        savings = _by_name(data["savings_contributors"])
        assert set(savings) == {
            "Brokerage",
            "Vacation Fund",
            "Cascade Point HYSA",
            "Rainy Day Reserve",
        }
        assert savings["Brokerage"] | {"id": None} == {
            "kind": "account",
            "id": None,
            "name": "Brokerage",
            "reason": ActivityReason.TRANSFER_TO_TRACKED_ASSET.value,
            "reason_label": "transfer to a tracked account",
            "total": Decimal("1000.00"),
            "count": 1,
        }
        assert savings["Brokerage"]["id"] == w["brokerage"].id
        assert savings["Vacation Fund"]["kind"] == "category"
        assert savings["Vacation Fund"]["id"] == w["vacation"].id
        assert savings["Vacation Fund"]["reason"] == ActivityReason.TAGGED_SAVINGS.value
        assert savings["Vacation Fund"]["reason_label"] == "category tagged Savings"
        assert savings["Vacation Fund"]["total"] == Decimal("310.25")

    async def test_a_tagged_envelope_into_a_tracked_account_is_the_account(self, db_session):
        """Grouped by destination, not by envelope: the HYSA is one row however
        the money reached it, and the tag — first in the classifier's order —
        is the reason it gives."""
        w = await _world(db_session)
        await _seed_month(db_session, w, date(2026, 3, 10))

        data = await savings_contributors(db_session, w["budget"].id, MONTH_START, MONTH_END)
        hysa = _by_name(data["savings_contributors"])["Cascade Point HYSA"]

        assert hysa["kind"] == "account"
        assert hysa["total"] == Decimal("674.15")
        assert hysa["count"] == 2
        assert hysa["reason"] == ActivityReason.TAGGED_SAVINGS.value
        assert "Emergency Fund" not in _by_name(data["savings_contributors"])

    async def test_a_withdrawal_from_tracked_savings_is_a_negative_contributor(self, db_session):
        w = await _world(db_session)
        await _seed_month(db_session, w, date(2026, 3, 10))

        data = await savings_contributors(db_session, w["budget"].id, MONTH_START, MONTH_END)
        reserve = _by_name(data["savings_contributors"])["Rainy Day Reserve"]

        assert reserve["total"] == Decimal("-150.20")
        assert reserve["kind"] == "account"
        assert reserve["reason"] == ActivityReason.TRANSFER_TO_TRACKED_ASSET.value

    async def test_growth_spending_and_internal_moves_are_nowhere(self, db_session):
        w = await _world(db_session)
        await _seed_month(db_session, w, date(2026, 3, 10))

        data = await savings_contributors(db_session, w["budget"].id, MONTH_START, MONTH_END)
        named = {c["name"] for c in data["savings_contributors"] + data["debt_contributors"]} | {
            s["payee_name"] for s in data["income_sources"]
        }

        # Market growth (75.33 inside the brokerage) would make the brokerage
        # 1,075.33; the move to Buffer Savings and the groceries appear nowhere.
        assert _by_name(data["savings_contributors"])["Brokerage"]["total"] == Decimal("1000.00")
        assert not named & {"Buffer Savings", "Checking", "Groceries"}
        assert all(
            s["total"] in (Decimal("5000.00"), Decimal("250.10")) for s in data["income_sources"]
        )

    async def test_the_list_is_ordered_by_magnitude(self, db_session):
        w = await _world(db_session)
        await _seed_month(db_session, w, date(2026, 3, 10))

        data = await savings_contributors(db_session, w["budget"].id, MONTH_START, MONTH_END)

        assert [c["name"] for c in data["savings_contributors"]] == [
            "Brokerage",
            "Cascade Point HYSA",
            "Vacation Fund",
            "Rainy Day Reserve",
        ]


class TestDebtAndIncome:
    async def test_debt_principal_is_named_the_same_way(self, db_session):
        w = await _world(db_session)
        await _seed_month(db_session, w, date(2026, 3, 10))

        data = await savings_contributors(db_session, w["budget"].id, MONTH_START, MONTH_END)
        debt = _by_name(data["debt_contributors"])

        assert set(debt) == {"Harborstone Mortgage", "Student Loan"}
        assert debt["Harborstone Mortgage"]["kind"] == "account"
        assert debt["Harborstone Mortgage"]["reason"] == (
            ActivityReason.TRANSFER_TO_TRACKED_DEBT.value
        )
        assert debt["Harborstone Mortgage"]["total"] == Decimal("1200.30")
        assert debt["Student Loan"]["kind"] == "category"
        assert debt["Student Loan"]["reason"] == ActivityReason.TAGGED_DEBT.value
        assert debt["Student Loan"]["total"] == Decimal("100.25")

    async def test_income_is_grouped_by_payee_with_income_by_sources_name_for_none(
        self, db_session
    ):
        w = await _world(db_session)
        await _seed_month(db_session, w, date(2026, 3, 10))

        data = await savings_contributors(db_session, w["budget"].id, MONTH_START, MONTH_END)

        assert [(s["payee_name"], s["total"], s["count"]) for s in data["income_sources"]] == [
            ("Northwind Payserv", Decimal("5000.00"), 1),
            (NO_PAYEE, Decimal("250.10"), 1),
        ]
        assert data["income_sources"][0]["payee_id"] == w["payroll"].id
        assert data["income_sources"][1]["payee_id"] is None


class TestAgreesWithTheCards:
    async def test_the_overview_card_over_its_range(self, db_session):
        """The Overview passes the picked range, which may run past today; its
        frame stops at today, and so do the contributors — a row later this
        month is in neither."""
        w = await _world(db_session)
        await _seed_month(db_session, w, date(2026, 3, 10))
        await create_transfer(
            db_session, w["budget"], w["checking"], w["brokerage"], "999.99", date(2026, 3, 20)
        )
        await create_transaction(
            db_session, w["budget"], w["checking"], "444.44", date(2026, 3, 20)
        )

        card = await ReportService(db_session).dashboard_metrics(
            w["budget"].id, MONTH_START, MONTH_END
        )
        data = await savings_contributors(db_session, w["budget"].id, MONTH_START, MONTH_END)

        assert data["end_date"] == TODAY
        assert data["income"] == card["income_this_month"]
        # The card serves its rate, not its numerator; the rate over the
        # contributors' totals is that rate exactly.
        assert card["savings_rate"] == float(data["savings"] / data["income"])
        assert data["debt_principal"] == card["debt_payments_this_month"]
        _assert_parts_sum(data)

    async def test_the_savings_rate_tab_over_its_served_window(self, db_session):
        """The tab serves the window its summary covers; asked for exactly that
        window, the contributors carry the summary's three figures."""
        w = await _world(db_session)
        await _seed_month(db_session, w, date(2026, 1, 20))
        await _seed_month(db_session, w, date(2026, 3, 10))
        # Before the three-month window: in neither.
        await create_transfer(
            db_session, w["budget"], w["checking"], w["hysa"], "777.77", date(2025, 12, 31)
        )

        tab = await ReportService(db_session).savings_rate(w["budget"].id, months=3)
        assert (tab["start_date"], tab["end_date"]) == (date(2026, 1, 1), TODAY)

        data = await savings_contributors(
            db_session, w["budget"].id, tab["start_date"], tab["end_date"]
        )
        summary = tab["summary"]
        assert data["income"] == summary["income"] == Decimal("10500.20")
        assert data["savings"] == summary["savings"] == Decimal("3668.40")
        assert data["debt_principal"] == summary["debt_principal"] == Decimal("2601.10")
        _assert_parts_sum(data)

    async def test_an_empty_window_is_zeros_and_empty_lists(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)

        data = await savings_contributors(db_session, budget.id, MONTH_START, MONTH_END)
        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, MONTH_END)

        assert data == {
            "start_date": MONTH_START,
            "end_date": TODAY,
            "income": Decimal("0"),
            "savings": Decimal("0"),
            "debt_principal": Decimal("0"),
            "savings_contributors": [],
            "debt_contributors": [],
            "income_sources": [],
        }
        assert card["income_this_month"] == data["income"]
        assert card["savings_rate"] is None


class TestReasonCopy:
    def test_every_reason_has_a_label_and_a_clause(self):
        assert set(REASON_LABEL) == set(ActivityReason)
        assert set(REASON_TEXT) == set(ActivityReason)

    def test_the_priority_is_every_reason_once(self):
        assert sorted(REASON_PRIORITY) == sorted(ActivityReason)
        assert REASON_PRIORITY.index(ActivityReason.TAGGED_SAVINGS) < REASON_PRIORITY.index(
            ActivityReason.TRANSFER_TO_TRACKED_ASSET
        )


class TestEndpoint:
    async def test_serves_the_breakdown(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        await create_transaction(db_session, budget, checking, "2000.00", date(2026, 3, 2))
        await create_transfer(db_session, budget, checking, brokerage, "500.00", date(2026, 3, 3))
        await db_session.flush()

        with report_today(TODAY):
            resp = await api_client.get(
                f"/api/v1/{budget.id}/reports/savings-contributors",
                params={"start_date": "2026-03-01", "end_date": "2026-03-31"},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["end_date"] == "2026-03-15"
        assert Decimal(body["savings"]) == Decimal("500.00")
        assert body["savings_contributors"][0]["name"] == "Brokerage"
        assert body["savings_contributors"][0]["reason_label"] == "transfer to a tracked account"
        assert body["income_sources"][0]["payee_name"] == NO_PAYEE

    async def test_both_dates_are_required(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        resp = await api_client.get(
            f"/api/v1/{budget.id}/reports/savings-contributors",
            params={"start_date": "2026-03-01"},
        )
        assert resp.status_code == 422

    async def test_the_savings_rate_endpoint_serves_its_window(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        with report_today(TODAY):
            resp = await api_client.get(
                f"/api/v1/{budget.id}/reports/savings-rate", params={"months": 2}
            )
        assert resp.status_code == 200, resp.text
        assert (resp.json()["start_date"], resp.json()["end_date"]) == ("2026-02-01", "2026-03-15")
