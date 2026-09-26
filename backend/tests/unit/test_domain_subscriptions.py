"""What one subscription costs a year — domain/subscriptions.py — and the
cadence rules it shares with the cash projection (domain/schedule.py).

Every case is a service's signed ledger rows (charges negative, refunds
positive) on a fixed reader's day, so the year is fixed too: the 12 complete
months 1 Sep 2025 – 31 Aug 2026.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.dates import add_months, complete_month_window
from igab.domain.schedule import Cadence, cadence_of, cycles_per_year, has_stopped
from igab.domain.subscriptions import Basis, service_cost

TODAY = date(2026, 9, 26)
YEAR_START, YEAR_END = complete_month_window(TODAY, 12)
D = Decimal


def cost(rows):
    return service_cost(rows, year_start=YEAR_START, year_end=YEAR_END, today=TODAY)


def monthly(amount: str, first: date, n: int) -> list[tuple[date, Decimal]]:
    """`n` charges of `amount`, a calendar month apart from `first`."""
    return [(add_months(first, i), -D(amount)) for i in range(n)]


def test_the_year_is_the_last_twelve_complete_months():
    assert (YEAR_START, YEAR_END) == (date(2025, 9, 1), date(2026, 8, 31))


class TestObserved:
    def test_a_monthly_service_costs_what_its_year_charged(self):
        c = cost(monthly("15.00", date(2025, 3, 5), 19))  # Mar 2025 – Sep 2026
        assert c.basis is Basis.OBSERVED
        assert c.charges_in_year == 12
        assert c.annual == D("180.00")
        assert c.monthly == D("15.00")

    def test_an_annual_bill_reads_its_price_not_four_times_it(self):
        """The audit's case. A $60-a-year bill charged each June read $20/mo
        in September — its one June charge divided by the three months since
        it, $240 a year — and the figure moved with the range picker. The year
        holds one charge, so the year costs $60."""
        c = cost([(date(2025, 6, 10), D("-60")), (date(2026, 6, 10), D("-60"))])
        assert c.basis is Basis.OBSERVED
        assert c.cadence is Cadence.YEARLY
        assert c.annual == D("60.00")
        assert c.monthly == D("5.00")

    def test_a_quarterly_service_is_its_four_charges(self):
        rows = [(add_months(date(2025, 1, 15), 3 * i), D("-30")) for i in range(7)]
        c = cost(rows)
        assert c.basis is Basis.OBSERVED
        assert c.charges_in_year == 4
        assert c.annual == D("120.00")
        assert c.monthly == D("10.00")

    def test_a_refund_inside_the_year_is_netted(self):
        """The rest of the spending reports net refunds; this one ignored
        them, so a refunded month still read as a month paid."""
        rows = monthly("15.00", date(2025, 3, 5), 19) + [(date(2026, 2, 20), D("15.00"))]
        c = cost(rows)
        assert c.refunded_in_year == D("15.00")
        assert c.annual == D("165.00")

    def test_a_refund_outside_the_year_is_not(self):
        rows = monthly("15.00", date(2025, 3, 5), 19) + [(date(2025, 5, 20), D("15.00"))]
        c = cost(rows)
        assert c.refunded_in_year == D("0.00")
        assert c.annual == D("180.00")

    def test_the_running_month_is_not_in_the_year(self):
        # 12 charges in the year plus this month's: the year still holds 12.
        c = cost(monthly("10.00", date(2025, 9, 3), 13))
        assert c.charges_in_year == 12
        assert c.annual == D("120.00")

    def test_a_payee_billing_several_plans_is_not_a_price_change(self):
        """Two plans on one payee alternate amounts. Reading the latest as a
        new price would project one plan's charge for a year."""
        rows = []
        for i in range(19):
            day = add_months(date(2025, 3, 5), i)
            rows += [(day, D("-2.99")), (day + timedelta(days=9), D("-9.99"))]
        c = cost(rows)
        assert c.basis is Basis.OBSERVED
        assert c.annual == D("155.76")  # 12 × (2.99 + 9.99)


class TestPriceChange:
    def test_a_new_price_projects_the_year_from_the_latest_charge(self):
        """Nine months at $15 and three at $18 blended to $189 (and a fourth $18
        has come this month); the service
        costs $216 a year from now on."""
        rows = monthly("15.00", date(2025, 3, 5), 15) + monthly("18.00", date(2026, 6, 5), 4)
        c = cost(rows)
        assert c.basis is Basis.PRICE_CHANGE
        assert c.latest_charge == D("18.00")
        assert c.annual == D("216.00")
        assert c.monthly == D("18.00")

    def test_a_new_price_charged_again_this_month_counts(self):
        rows = monthly("15.00", date(2025, 3, 5), 17) + monthly("18.00", date(2026, 8, 5), 2)
        c = cost(rows)
        assert c.basis is Basis.PRICE_CHANGE
        assert c.annual == D("216.00")

    def test_one_different_charge_is_not_yet_a_price(self):
        """An add-on billed beside the plan looked exactly like a new price:
        five $12 charges in the year and one $5 read as a $5 service, a year
        of $30 where the year had charged $65."""
        rows = [(add_months(date(2025, 2, 7), 2 * i), D("-12.00")) for i in range(9)]
        rows.append((date(2026, 8, 24), D("-5.00")))
        c = cost(rows)
        assert c.basis is Basis.OBSERVED
        assert c.charges_in_year == 6
        assert c.annual == D("65.00")

    def test_a_price_change_is_still_net_of_refunds(self):
        rows = (
            monthly("15.00", date(2025, 3, 5), 15)
            + monthly("18.00", date(2026, 6, 5), 4)
            + [(date(2026, 7, 9), D("18.00"))]
        )
        assert cost(rows).annual == D("198.00")

    def test_an_old_price_change_before_the_year_is_just_observed(self):
        rows = monthly("12.00", date(2024, 9, 5), 6) + monthly("15.00", date(2025, 3, 5), 19)
        c = cost(rows)
        assert c.basis is Basis.OBSERVED
        assert c.annual == D("180.00")


class TestNew:
    def test_a_service_younger_than_the_year_is_projected_from_its_cadence(self):
        c = cost(monthly("10.00", date(2026, 6, 12), 4))  # Jun – Sep 2026
        assert c.basis is Basis.NEW
        assert c.is_projected
        assert c.cadence is Cadence.MONTHLY
        assert c.annual == D("120.00")
        assert c.monthly == D("10.00")

    def test_one_charge_counts_once(self):
        """One charge has no cadence to observe. Read as monthly, a single
        $40 charge was $480 a year — most of the headline it sat in."""
        c = cost([(date(2026, 9, 2), D("-40.00"))])
        assert c.basis is Basis.NEW
        assert c.cadence_assumed
        assert c.new_this_month
        assert c.annual == D("40.00")
        assert not c.is_projected

    def test_two_charges_on_one_day_still_assume(self):
        c = cost([(date(2026, 9, 2), D("-9.00")), (date(2026, 9, 2), D("-9.00"))])
        assert c.cadence_assumed

    def test_a_weekly_service_is_365_over_7_charges_a_year(self):
        rows = [(date(2026, 8, 1) + timedelta(days=7 * i), D("-7.00")) for i in range(8)]
        c = cost(rows)
        assert c.basis is Basis.NEW
        assert c.cadence is Cadence.DAYS
        assert c.annual == D("365.00")

    def test_a_new_service_projects_its_latest_price(self):
        rows = [(date(2026, 8, 1), D("-1.00")), (date(2026, 9, 1), D("-12.00"))]
        assert cost(rows).annual == D("144.00")

    def test_new_this_month_is_the_first_charge_only(self):
        assert not cost(monthly("10.00", date(2026, 8, 12), 2)).new_this_month


class TestStopped:
    def test_a_monthly_service_quiet_past_one_and_a_half_cycles_stops(self):
        """Cancelled services stayed in Monthly, Annual and Active for the
        rest of the year."""
        last = TODAY - timedelta(days=46)
        c = cost(monthly("15.00", add_months(last, -14), 15))
        assert c.basis is Basis.STOPPED
        assert c.annual == D("0.00")
        assert c.monthly == D("0.00")
        # Still described: the page lists it with its last charge.
        assert c.last_charge_date == last
        assert c.charges_in_year > 0

    def test_a_monthly_service_is_live_on_the_last_day(self):
        last = TODAY - timedelta(days=45)
        rows = [(last - timedelta(days=30), D("-15.00")), (last, D("-15.00"))]
        assert cost(rows).basis is not Basis.STOPPED

    def test_a_single_old_charge_is_a_stopped_trial(self):
        c = cost([(date(2026, 6, 2), D("-9.00"))])
        assert c.basis is Basis.STOPPED
        assert c.annual == D("0.00")

    def test_an_annual_bill_is_live_for_a_year_and_a_half(self):
        rows = [(date(2024, 6, 10), D("-60")), (date(2025, 6, 10), D("-60"))]
        # 473 days since the last charge: under 1.5 × 365.
        c = cost(rows)
        assert c.basis is Basis.OBSERVED
        assert c.annual == D("0.00")  # nothing charged in the year itself


class TestNotAService:
    def test_a_refund_alone_is_not_a_service(self):
        assert cost([(date(2026, 3, 1), D("15.00"))]) is None

    def test_nothing_is_not_a_service(self):
        assert cost([]) is None

    def test_a_future_dated_charge_is_ignored(self):
        assert cost([(TODAY + timedelta(days=3), D("-15.00"))]) is None


class TestCadence:
    @pytest.mark.parametrize(
        ("days", "cadence"),
        [
            (24, Cadence.DAYS),
            (25, Cadence.MONTHLY),
            (35, Cadence.MONTHLY),
            (36, Cadence.DAYS),
            (349, Cadence.DAYS),
            (350, Cadence.YEARLY),
            (400, Cadence.YEARLY),
        ],
    )
    def test_the_calendar_bands(self, days, cadence):
        assert cadence_of(days) is cadence

    def test_cycles_per_year_counts_calendar_cadences_exactly(self):
        # A 31-day observed gap is a calendar month: 12, not 365 / 31 = 11.8.
        assert cycles_per_year(31) == 12
        assert cycles_per_year(365) == 1
        assert cycles_per_year(91) == D(365) / D(91)


class TestHasStopped:
    @pytest.mark.parametrize("interval", [8, 30, 365])
    def test_one_and_a_half_cycles_is_the_line(self, interval):
        at = TODAY - timedelta(days=interval * 3 // 2)
        assert not has_stopped(at, interval, TODAY)
        assert has_stopped(at - timedelta(days=1), interval, TODAY)

    def test_an_odd_interval_rounds_toward_live(self):
        # 1.5 × 7 = 10.5 days: ten and a half is not yet over.
        assert not has_stopped(TODAY - timedelta(days=10), 7, TODAY)
        assert has_stopped(TODAY - timedelta(days=11), 7, TODAY)
