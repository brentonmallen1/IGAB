"""A drill-down must total what the chart that opened it totalled.

Once the charts moved onto the activity-class partition, an "Expenses" bar
meant SPENDING while its drill-down still listed every negative row — so an
$800 bar opened a panel totalling $1,800, showing the user a list that
contradicts the number they clicked. The drill path had no class parameter, so
this could not be fixed on the client.
"""

from datetime import date
from decimal import Decimal

from igab.repositories.transaction_repo import TransactionRepository
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
)

TODAY = date.today()
MONTH_START = TODAY.replace(day=1)


async def _world(db_session, owner=None):
    user = owner or await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking", on_budget=True)
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
    rta = await create_category(db_session, budget, inflow, "Ready to Assign")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    investing = await create_category(db_session, budget, everyday, "Investing")

    await create_transaction(db_session, budget, checking, "5000.00", TODAY, category=rta)
    await create_transaction(db_session, budget, checking, "-800.00", TODAY, category=groceries)
    out = await create_transaction(
        db_session, budget, checking, "-1000.00", TODAY, category=investing
    )
    into = await create_transaction(db_session, budget, brokerage, "1000.00", TODAY)
    out.transfer_id, into.transfer_id = into.id, out.id
    await db_session.flush()
    return budget


async def _drill_total(db_session, budget, **kw) -> Decimal:
    rows, _, _ = await TransactionRepository(db_session).list_for_budget(
        budget.id,
        start_date=MONTH_START,
        end_date=TODAY,
        posted_only=True,
        cash_flow_only=True,
        **kw,
    )
    return abs(sum((r.amount for r in rows), Decimal("0")))


class TestExpensesDrillMatchesTheBar:
    async def test_without_the_class_filter_the_panel_overstates(self, db_session):
        """Pins the mechanism: the old behaviour is what the parameter fixes."""
        budget = await _world(db_session)
        unfiltered = await _drill_total(db_session, budget, scope="leaf", direction="outflow")
        assert unfiltered == Decimal("1800.00"), "every negative row, savings included"

    async def test_with_it_the_panel_matches_the_expenses_bar(self, db_session):
        budget = await _world(db_session)
        months = await ReportService(db_session).income_vs_expense(budget.id, months=1)

        drilled = await _drill_total(
            db_session, budget, scope="leaf", direction="outflow",
            activity_classes=["spending"],
        )

        assert drilled == months[-1]["expenses"] == Decimal("800.00")

    async def test_the_income_drill_matches_the_income_bar(self, db_session):
        budget = await _world(db_session)
        months = await ReportService(db_session).income_vs_expense(budget.id, months=1)

        drilled = await _drill_total(
            db_session, budget, scope="leaf", direction="inflow",
            activity_classes=["income"],
        )

        assert drilled == months[-1]["income"] == Decimal("5000.00")

    async def test_including_savings_matches_the_toggled_chart(self, db_session):
        budget = await _world(db_session)
        drilled = await _drill_total(
            db_session, budget, scope="leaf", direction="outflow",
            activity_classes=["spending", "savings", "debt_principal"],
        )
        assert drilled == Decimal("1800.00")

    async def test_no_classes_given_means_no_class_filter(self, db_session):
        """The parameter is opt-in; the register and other callers are
        unaffected by its introduction."""
        budget = await _world(db_session)
        a = await _drill_total(db_session, budget, scope="leaf", direction="outflow")
        b = await _drill_total(
            db_session, budget, scope="leaf", direction="outflow", activity_classes=None
        )
        assert a == b == Decimal("1800.00")


class TestThroughTheApi:
    async def test_activity_classes_reaches_the_query(self, api_client, db_session):
        budget = await _world(db_session, api_client.test_user)

        resp = await api_client.get(
            f"/api/v1/{budget.id}/transactions",
            params={
                "start_date": MONTH_START.isoformat(),
                "end_date": TODAY.isoformat(),
                "scope": "leaf",
                "direction": "outflow",
                "posted_only": "true",
                "cash_flow_only": "true",
                "activity_classes": "spending",
            },
        )

        assert resp.status_code == 200
        total = sum(abs(Decimal(t["amount"])) for t in resp.json()["transactions"])
        assert total == Decimal("800.00")

    async def test_a_malformed_id_is_a_client_error_not_a_fault(self, api_client, db_session):
        budget = await _world(db_session, api_client.test_user)

        resp = await api_client.get(
            f"/api/v1/{budget.id}/transactions",
            params={"category_ids": "not-a-uuid_also-not-one"},
        )

        assert resp.status_code == 400
