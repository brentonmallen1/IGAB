"""Liabilities whose contract terms are not on file.

A liability can now exist before anyone has entered an APR or a minimum
payment — the prerequisite for creating a companion liability alongside every
liability-classified account.

The hazard being pinned here is arithmetic, not cosmetic. `amortization_schedule`
treats a payment that fails to cover the month's interest as proof the debt
never retires, so terms defaulted to zero return `never_pays_off=True` on the
first iteration. That boolean does not stay on a page: it rides into the
Liabilities report beside a total-interest figure. "Not known" therefore has to
read as absent at every layer, never as zero.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.repositories.liability_repo import LiabilityRepository
from igab.services.amortization import amortization_schedule
from igab.services.liability_service import LiabilityService

from .factories import (
    create_account,
    create_budget,
    create_liability,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()
AS_OF = date(2026, 7, 25)


def make_liability_service(db_session, services) -> LiabilityService:
    return LiabilityService(
        LiabilityRepository(db_session),
        services.account_repo,
        services.category_repo,
        services.transaction_repo,
    )


async def _managed_loan(db_session, *, interest_rate=None, minimum_payment=None, balance="-9000.00"):
    """A loan account with a real ledger and a liability with the given terms."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(
        db_session, budget, "Car Loan", account_type="loan", on_budget=False
    )
    await create_transaction(db_session, budget, account, balance, date(2026, 1, 5))
    liability = await create_liability(
        db_session,
        budget,
        "Car Loan",
        liability_type="auto",
        linked_account_id=account.id,
        interest_rate=interest_rate,
        minimum_payment=minimum_payment,
    )
    return make_liability_service(db_session, services), budget, account, liability


class TestTheTrapThisGuards:
    def test_zero_terms_do_claim_the_debt_never_retires(self):
        """Why the None-vs-zero distinction is load-bearing.

        If a companion liability were ever created with zeroed terms instead of
        null ones, this is the answer the math gives — stated here so the
        rationale for every guard below is visible rather than folklore.
        """
        result = amortization_schedule(Decimal("9000.00"), Decimal("0"), Decimal("0"), AS_OF)

        assert result.never_pays_off is True
        assert result.payoff_date is None


class TestStatusWithoutTerms:
    async def test_no_baseline_schedule(self, db_session):
        svc, _, _, liability = await _managed_loan(db_session)

        status = await svc.get_status(liability, as_of=AS_OF)

        assert status.terms_complete is False
        assert status.baseline is None

    async def test_no_live_projection(self, db_session):
        """Payment velocity alone cannot date a payoff: without a rate we do
        not know how much of each payment the interest eats."""
        svc, budget, account, liability = await _managed_loan(db_session)
        for month in (3, 4, 5, 6):
            await create_transaction(db_session, budget, account, "400.00", date(2026, month, 10))

        status = await svc.get_status(liability, as_of=AS_OF)

        assert status.live is None

    async def test_observed_facts_survive(self, db_session):
        """Balance and payment history are measured, not derived from terms."""
        svc, budget, account, liability = await _managed_loan(db_session)
        for month in (3, 4, 5, 6):
            await create_transaction(db_session, budget, account, "400.00", date(2026, month, 10))

        status = await svc.get_status(liability, as_of=AS_OF)

        assert status.current_balance == Decimal("7400.00")
        assert status.balance_source == "ledger"
        assert sum(status.recent_payments) == Decimal("1600.00")

    async def test_average_payment_still_reported(self, db_session):
        """The pace is history, so it stands beside an empty terms form — the
        most useful thing there is to show while the fields are blank."""
        svc, budget, account, liability = await _managed_loan(db_session)
        for month in (4, 5, 6):
            await create_transaction(db_session, budget, account, "300.00", date(2026, month, 10))

        status = await svc.get_status(liability, as_of=AS_OF)

        assert status.average_payment == Decimal("300.00")
        assert status.live is None  # known pace, still no projection

    async def test_promo_outlook_absent(self, db_session):
        svc, budget, account, liability = await _managed_loan(db_session)
        liability.promo_end_date = date(2027, 1, 1)
        liability.promo_deferred_interest = True
        await db_session.flush()

        status = await svc.get_status(liability, as_of=AS_OF)

        assert status.promo is None

    @pytest.mark.parametrize(
        "interest_rate,minimum_payment",
        [
            (Decimal("6.5"), None),  # rate known, payment not
            (None, Decimal("250.00")),  # payment known, rate not
        ],
    )
    async def test_partial_terms_are_incomplete(self, db_session, interest_rate, minimum_payment):
        """Half the contract projects nothing. Both fields move together so
        consumers have one question to ask, not two."""
        svc, _, _, liability = await _managed_loan(
            db_session, interest_rate=interest_rate, minimum_payment=minimum_payment
        )

        status = await svc.get_status(liability, as_of=AS_OF)

        assert status.terms_complete is False
        assert status.baseline is None
        assert status.live is None

    async def test_complete_terms_still_project(self, db_session):
        """The control: nothing about the ordinary path changed."""
        svc, _, _, liability = await _managed_loan(
            db_session, interest_rate=Decimal("6.0"), minimum_payment=Decimal("400.00")
        )

        status = await svc.get_status(liability, as_of=AS_OF)

        assert status.terms_complete is True
        assert status.baseline is not None
        assert status.baseline.never_pays_off is False
        assert status.baseline.payoff_date is not None


class TestNeverPaysOffIsNotClaimed:
    """The regression this phase exists to prevent."""

    async def test_report_row_makes_no_payoff_claim(self, db_session):
        svc, budget, _, _ = await _managed_loan(db_session)

        report = await svc.liabilities_report(budget.id, as_of=AS_OF)
        (row,) = report["items"]

        assert row["terms_complete"] is False
        assert row["never_pays_off"] is False
        assert row["baseline_payoff_date"] is None
        assert row["total_interest_remaining"] is None
        assert row["interest_rate"] is None

    async def test_the_debt_itself_is_still_reported(self, db_session):
        """Missing terms hide the projection, never the balance — an unfilled
        form must not make a debt disappear from the rollup."""
        svc, budget, _, _ = await _managed_loan(db_session)

        report = await svc.liabilities_report(budget.id, as_of=AS_OF)

        assert report["total_balance"] == Decimal("9000.00")
        assert len(report["items"]) == 1


class TestReportTotals:
    async def test_interest_total_excludes_unknown_rows_and_says_so(self, db_session):
        """A partial total is fine; a partial total that looks complete is not."""
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)

        known_account = await create_account(
            db_session, budget, "Known Loan", account_type="loan", on_budget=False
        )
        await create_transaction(
            db_session, budget, known_account, "-5000.00", TODAY - timedelta(days=60)
        )
        await create_liability(
            db_session,
            budget,
            "Known",
            liability_type="auto",
            linked_account_id=known_account.id,
            interest_rate=Decimal("6.0"),
            minimum_payment=Decimal("300.00"),
        )

        blank_account = await create_account(
            db_session, budget, "Blank Loan", account_type="loan", on_budget=False
        )
        await create_transaction(
            db_session, budget, blank_account, "-4000.00", TODAY - timedelta(days=60)
        )
        await create_liability(
            db_session,
            budget,
            "Blank",
            liability_type="mortgage",
            linked_account_id=blank_account.id,
            interest_rate=None,
            minimum_payment=None,
        )

        svc = make_liability_service(db_session, services)
        report = await svc.liabilities_report(budget.id, as_of=TODAY)

        known = next(i for i in report["items"] if i["name"] == "Known")
        assert report["liabilities_missing_terms"] == 1
        assert report["total_interest_remaining"] == known["total_interest_remaining"]
        # Both debts count toward what is owed; only one can be projected.
        assert report["total_balance"] == Decimal("9000.00")

    async def test_no_missing_terms_reports_zero(self, db_session):
        svc, budget, _, _ = await _managed_loan(
            db_session, interest_rate=Decimal("6.0"), minimum_payment=Decimal("400.00")
        )

        report = await svc.liabilities_report(budget.id, as_of=AS_OF)

        assert report["liabilities_missing_terms"] == 0
        assert report["total_interest_remaining"] > Decimal("0")


class TestApiSurface:
    async def test_liability_out_nulls_terms_and_flags_them(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(
            db_session, budget, "Mortgage", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-250000.00", TODAY - timedelta(days=30))
        await create_liability(
            db_session,
            budget,
            "Mortgage",
            liability_type="mortgage",
            linked_account_id=loan.id,
            interest_rate=None,
            minimum_payment=None,
        )

        resp = await api_client.get(f"/api/v1/{budget.id}/liabilities")

        assert resp.status_code == 200, resp.text
        (body,) = resp.json()
        assert body["terms_complete"] is False
        assert body["interest_rate"] is None
        assert body["minimum_payment"] is None
        assert body["monthly_interest_now"] is None
        assert body["baseline_payoff_date"] is None
        assert body["baseline_never_pays_off"] is False
        assert Decimal(str(body["current_balance"])) == Decimal("250000.00")

    async def test_implied_term_not_computed_without_terms(self, api_client, db_session):
        """Origination date and original principal are not enough on their own —
        the implied-term trap detector needs the payment it is checking."""
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(
            db_session, budget, "Mortgage", account_type="loan", on_budget=False
        )
        await create_liability(
            db_session,
            budget,
            "Mortgage",
            liability_type="mortgage",
            linked_account_id=loan.id,
            interest_rate=None,
            minimum_payment=None,
            origination_date=date(2020, 6, 1),
            original_principal=Decimal("300000.00"),
        )

        resp = await api_client.get(f"/api/v1/{budget.id}/liabilities")

        (body,) = resp.json()
        assert body["implied_term_months"] is None
        assert body["implied_never_pays_off"] is None

    async def test_amortization_returns_an_empty_state_not_an_error(self, api_client, db_session):
        """A liability waiting for its terms is an ordinary state. A 4xx here
        would make the page render a failure instead of an invitation."""
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-9000.00", TODAY - timedelta(days=30))
        liability = await create_liability(
            db_session,
            budget,
            "Loan",
            linked_account_id=loan.id,
            interest_rate=None,
            minimum_payment=None,
        )

        resp = await api_client.get(
            f"/api/v1/{budget.id}/liabilities/{liability.id}/amortization"
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["terms_complete"] is False
        assert body["baseline_schedule"] == []
        assert body["baseline_never_pays_off"] is False
        assert body["baseline_total_interest"] is None
        assert Decimal(str(body["current_balance"])) == Decimal("9000.00")

    async def test_extra_payment_without_terms_is_inert(self, api_client, db_session):
        """"What if I paid $200 more?" has no answer without a rate to save
        interest against — the arm sits out rather than treating null as zero."""
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-9000.00", TODAY - timedelta(days=30))
        liability = await create_liability(
            db_session,
            budget,
            "Loan",
            linked_account_id=loan.id,
            interest_rate=None,
            minimum_payment=None,
        )

        resp = await api_client.get(
            f"/api/v1/{budget.id}/liabilities/{liability.id}/amortization",
            params={"extra_payment": "200.00"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["extra_schedule"] is None
        assert body["extra_never_pays_off"] is False

    async def test_liabilities_report_endpoint_survives_blank_terms(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-9000.00", TODAY - timedelta(days=30))
        await create_liability(
            db_session,
            budget,
            "Loan",
            linked_account_id=loan.id,
            interest_rate=None,
            minimum_payment=None,
        )

        resp = await api_client.get(f"/api/v1/{budget.id}/reports/liabilities")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["liabilities_missing_terms"] == 1
        (row,) = body["items"]
        assert row["never_pays_off"] is False
        assert row["total_interest_remaining"] is None
