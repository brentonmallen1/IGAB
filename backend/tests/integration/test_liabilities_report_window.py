"""The Liabilities report reads the report window, marks arrivals, and says
why a cell is empty; the what-if never quotes a saving against a minimum
that never pays off.

The chart ignored the range and opened on the month the oldest debt began,
drawing every arrival as a cliff up from zero. "—" sat in the pace column
with no reason, and a mortgage whose payment carried escrow read as a loan
paid off years early with nothing saying its terms disagreed.

Every name and figure is invented.
"""

from datetime import date
from decimal import Decimal as D

from igab.domain.payee_names import STARTING_BALANCE_PAYEE
from igab.repositories.liability_repo import LiabilityRepository
from igab.services.liability_service import LiabilityService

from .factories import (
    create_account,
    create_budget,
    create_liability,
    create_liability_snapshot,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)

AS_OF = date(2026, 9, 15)
JUN, JUL, AUG, SEP = (date(2026, m, 1) for m in (6, 7, 8, 9))


def _service(db_session) -> LiabilityService:
    services = make_services(db_session)
    return LiabilityService(
        LiabilityRepository(db_session),
        services.account_repo,
        services.category_repo,
        services.transaction_repo,
    )


async def _three_debts(db_session, user=None):
    """
    Jane Doe Loan      manual: 5,000 Jan 10, 4,000 Jul 20 — older than the window
    Harborstone Note   manual: 2,000 Aug 5 — arrives in August
    Cedar Wagon Loan   account: Starting Balance -12,000 Jul 3 — arrives in July
    """
    budget = await create_budget(db_session, user or await create_user(db_session))
    old = await create_liability(db_session, budget, "Jane Doe Loan", manual_balance=D("4000"))
    await create_liability_snapshot(db_session, old, date(2026, 1, 10), D("5000"))
    await create_liability_snapshot(db_session, old, date(2026, 7, 20), D("4000"))
    note = await create_liability(db_session, budget, "Harborstone Note", manual_balance=D("2000"))
    await create_liability_snapshot(db_session, note, date(2026, 8, 5), D("2000"))
    account = await create_account(
        db_session, budget, "Cedar Wagon Loan", account_type="auto_loan", on_budget=False
    )
    opening = await create_payee(db_session, budget, STARTING_BALANCE_PAYEE)
    await create_transaction(db_session, budget, account, "-12000", date(2026, 7, 3), payee=opening)
    wagon = await create_liability(
        db_session, budget, "Cedar Wagon Loan", linked_account_id=account.id
    )
    await db_session.flush()
    return budget, old, note, wagon


class TestTheWindow:
    async def test_the_series_is_the_report_window(self, db_session):
        budget, old, note, wagon = await _three_debts(db_session)

        report = await _service(db_session).liabilities_report(budget.id, as_of=AS_OF, months=3)
        points = report["balance_over_time"]

        assert [p["date"] for p in points] == [JUN, JUL, AUG, SEP]
        # January's point stands in June: the window opens on the range, not
        # on the oldest debt, and reads what was known by then.
        assert points[0]["per_liability"] == {str(old.id): D("5000")}

    async def test_a_debt_is_absent_before_it_arrives_and_its_arrival_is_marked(self, db_session):
        budget, old, note, wagon = await _three_debts(db_session)

        report = await _service(db_session).liabilities_report(budget.id, as_of=AS_OF, months=3)
        points = report["balance_over_time"]

        assert [sorted(p["per_liability"]) for p in points] == [
            [str(old.id)],
            sorted([str(old.id), str(wagon.id)]),
            sorted([str(old.id), str(wagon.id), str(note.id)]),
            sorted([str(old.id), str(wagon.id), str(note.id)]),
        ]
        # Owed, positive, keyed to the liability.
        assert [p["entered"] for p in points] == [D("0"), D("12000"), D("2000"), D("0")]
        assert [(e["id"], e["name"]) for e in points[1]["entries"]] == [
            (str(wagon.id), "Cedar Wagon Loan")
        ]
        assert points[2]["entries"][0]["kind"] == "manual_debt"

    async def test_the_endpoint_takes_the_range(self, api_client, db_session):
        budget, *_ = await _three_debts(db_session, api_client.test_user)

        resp = await api_client.get(
            f"/api/v1/{budget.id}/reports/liabilities",
            params={"months": 3, "client_today": AS_OF.isoformat()},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [p["entered"] for p in body["balance_over_time"]] == [0, 12000, 2000, 0]
        assert body["carrying_balance_count"] == 3


class TestWhyACellIsEmpty:
    async def test_each_reason_by_name(self, db_session):
        budget = await create_budget(db_session, await create_user(db_session))
        await create_liability(
            db_session,
            budget,
            "No Terms",
            manual_balance=D("300"),
            interest_rate=None,
            minimum_payment=None,
        )
        await create_liability(db_session, budget, "Brand New", manual_balance=D("900"))
        # A loan paid by deposits typed straight onto it: they look like
        # payments and are counted as none, so there is no pace.
        account = await create_account(
            db_session, budget, "Typed Loan", account_type="loan", on_budget=False
        )
        opening = await create_payee(db_session, budget, STARTING_BALANCE_PAYEE)
        await create_transaction(
            db_session, budget, account, "-6000", date(2026, 1, 5), payee=opening
        )
        for month in (7, 8):
            await create_transaction(db_session, budget, account, "500", date(2026, month, 10))
        await create_liability(db_session, budget, "Typed Loan", linked_account_id=account.id)
        await db_session.flush()

        report = await _service(db_session).liabilities_report(budget.id, as_of=AS_OF)

        assert {i["name"]: i["pace_missing"] for i in report["items"]} == {
            "No Terms": "no_terms",
            "Brand New": "too_little_history",
            "Typed Loan": "payments_not_linked",
        }
        # The missing-terms caveat, in dollars.
        assert report["liabilities_missing_terms"] == 1
        assert report["missing_terms_balance"] == D("300")

    async def test_a_pace_leaves_no_reason(self, db_session):
        budget = await create_budget(db_session, await create_user(db_session))
        card = await create_liability(
            db_session,
            budget,
            "Sapphire Visa",
            manual_balance=D("1000"),
            interest_rate=D("12"),
            minimum_payment=D("50"),
        )
        for day, balance in ((date(2026, 6, 1), "1400"), (date(2026, 7, 1), "1200")):
            await create_liability_snapshot(db_session, card, day, D(balance))
        await create_liability_snapshot(db_session, card, date(2026, 8, 1), D("1000"))

        (item,) = (await _service(db_session).liabilities_report(budget.id, as_of=AS_OF))["items"]

        assert item["payoff_basis"] == "observed"
        assert item["pace_missing"] is None

    async def test_carrying_a_balance_counts_only_what_is_owed(self, db_session):
        budget = await create_budget(db_session, await create_user(db_session))
        await create_liability(db_session, budget, "Owing", manual_balance=D("50"))
        await create_liability(db_session, budget, "Paid Off", manual_balance=D("0"))

        report = await _service(db_session).liabilities_report(budget.id, as_of=AS_OF)

        assert report["carrying_balance_count"] == 1
        assert len(report["items"]) == 2


class TestTermsDisagree:
    async def test_an_escrow_inclusive_payment_is_flagged_on_both_pages(
        self, api_client, db_session
    ):
        """$300,000 at 6% over 30 years levels at $1,798.66; $2,400 carries
        about $600 of escrow."""
        budget = await create_budget(db_session, api_client.test_user)
        mortgage = await create_liability(
            db_session,
            budget,
            "Harborstone Mortgage",
            manual_balance=D("290000"),
            interest_rate=D("6"),
            minimum_payment=D("2400"),
            original_principal=D("300000"),
        )
        mortgage.term_months = 360
        honest = await create_liability(
            db_session,
            budget,
            "Maple St Mortgage",
            manual_balance=D("290000"),
            interest_rate=D("6"),
            minimum_payment=D("1798.66"),
            original_principal=D("300000"),
        )
        honest.term_months = 360
        await db_session.flush()

        report = await _service(db_session).liabilities_report(budget.id, as_of=AS_OF)
        listed = await api_client.get(f"/api/v1/{budget.id}/liabilities")

        assert {i["name"]: i["terms_disagree"] for i in report["items"]} == {
            "Harborstone Mortgage": True,
            "Maple St Mortgage": False,
        }
        assert listed.status_code == 200, listed.text
        (page,) = [row for row in listed.json() if row["id"] == str(mortgage.id)]
        assert page["terms_disagree"] is True
        assert page["level_payment"] == 1798.66


class TestTheServedPayoff:
    async def test_the_detail_states_the_reports_verdict(self, api_client, db_session):
        """Three client components chose "live, else minimum" themselves."""
        budget = await create_budget(db_session, api_client.test_user)
        await create_liability(
            db_session,
            budget,
            "Jane Doe Loan",
            manual_balance=D("1000"),
            interest_rate=D("12"),
            minimum_payment=D("400"),
        )
        await db_session.flush()

        (listed,) = (await api_client.get(f"/api/v1/{budget.id}/liabilities")).json()

        assert listed["payoff_basis"] == "minimum"
        assert listed["payoff_date"] == listed["baseline_payoff_date"]
        assert listed["payoff_never"] is False


class TestInterestSaved:
    async def test_a_saving_against_a_minimum_that_pays_off(self, api_client, db_session):
        """$1,000 at 12%: $18.26 of interest at $400, $15.25 at $500."""
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_liability(
            db_session,
            budget,
            manual_balance=D("1000"),
            interest_rate=D("12"),
            minimum_payment=D("400"),
        )

        body = (
            await api_client.get(
                f"/api/v1/{budget.id}/liabilities/{loan.id}/amortization",
                params={"extra_payment": "100"},
            )
        ).json()

        assert body["interest_saved"] == 3.01
        assert body["months_sooner"] == 0

    async def test_no_saving_is_quoted_against_a_minimum_that_never_pays_off(
        self, api_client, db_session
    ):
        """$10,000 at 24% on a $100 minimum: $200 of interest a month. The
        baseline stopped at its first uncovered month having counted $0, and
        the page quoted $0 less the faster schedule's interest — a negative
        "less interest"."""
        budget = await create_budget(db_session, api_client.test_user)
        card = await create_liability(
            db_session,
            budget,
            "Sapphire Visa",
            manual_balance=D("10000"),
            interest_rate=D("24"),
            minimum_payment=D("100"),
        )

        body = (
            await api_client.get(
                f"/api/v1/{budget.id}/liabilities/{card.id}/amortization",
                params={"extra_payment": "200"},
            )
        ).json()

        assert body["baseline_never_pays_off"] is True
        assert body["baseline_total_interest"] is None
        assert body["extra_never_pays_off"] is False
        assert body["extra_total_interest"] > 0
        assert body["interest_saved"] is None
        assert body["months_sooner"] is None
