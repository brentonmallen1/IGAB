"""The plausibility checks on a receipt's read — every edge by name."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.money import model_cents
from igab.domain.receipt_checks import (
    CHECKED_CONFIDENCE_CAP,
    LINE_ITEM_TAX_TOLERANCE,
    RECEIPT_DATE_WINDOW_DAYS,
    capped_confidence,
    checked_receipt_date,
    line_items_mismatch,
    past_tomorrow,
    tender_disagrees,
)

TODAY = date(2026, 11, 16)
D = Decimal


class TestReceiptDate:
    def test_yesterday_stands(self):
        read = TODAY - timedelta(days=1)
        checked = checked_receipt_date(read, TODAY)
        assert checked.date == read and checked.read_as is None

    def test_the_last_day_of_the_window_stands(self):
        read = TODAY - timedelta(days=RECEIPT_DATE_WINDOW_DAYS)
        assert checked_receipt_date(read, TODAY).read_as is None

    def test_a_day_past_the_window_becomes_today(self):
        read = TODAY - timedelta(days=RECEIPT_DATE_WINDOW_DAYS + 1)
        checked = checked_receipt_date(read, TODAY)
        assert checked.date == TODAY and checked.read_as == read

    def test_two_years_back_becomes_today_and_keeps_the_read(self):
        """The reverse-video date line, read ~30 months early."""
        checked = checked_receipt_date(date(2024, 5, 10), TODAY)
        assert checked.date == TODAY
        assert checked.read_as == date(2024, 5, 10)

    def test_tomorrow_stands(self):
        assert checked_receipt_date(TODAY + timedelta(days=1), TODAY).read_as is None

    def test_far_future_becomes_today_and_is_flagged(self):
        checked = checked_receipt_date(date(2027, 1, 1), TODAY)
        assert checked.date == TODAY and checked.read_as == date(2027, 1, 1)

    def test_no_date_read_is_today_without_a_flag(self):
        checked = checked_receipt_date(None, TODAY)
        assert checked.date == TODAY and checked.read_as is None


class TestTender:
    def test_agreeing_tender(self):
        assert not tender_disagrees(D("84.30"), D("84.30"))

    def test_dropped_cents(self):
        """The TOTAL bar read as 84.00 while the card line says 84.30."""
        assert tender_disagrees(D("84.00"), D("84.30"))

    def test_no_payment_line(self):
        assert not tender_disagrees(D("84.00"), None)

    def test_sign_is_not_a_disagreement(self):
        assert not tender_disagrees(D("-12.00"), D("12.00"))


class TestLineItems:
    def test_items_plus_tax_inside_the_tolerance(self):
        assert line_items_mismatch(D("108.00"), [D("60.00"), D("40.00")]) is None

    def test_items_exactly_the_total(self):
        assert line_items_mismatch(D("100.00"), [D("60.00"), D("40.00")]) is None

    def test_discounts_negative_reconcile(self):
        assert line_items_mismatch(D("93.50"), [D("50.00"), D("50.00"), D("-6.50")]) is None

    def test_discounts_read_as_charges_disagree(self):
        """Discounts added as positive: the items come to more than was paid,
        and the sum is what the review names."""
        items = [D("80.00"), D("12.00"), D("2.30"), D("4.20")]
        assert line_items_mismatch(D("84.30"), items) == D("98.50")

    def test_a_cent_of_model_rounding_either_way(self):
        assert line_items_mismatch(D("100.00"), [D("100.01")]) is None

    def test_items_over_the_total_by_more_than_rounding(self):
        assert line_items_mismatch(D("100.00"), [D("100.02")]) is not None

    def test_total_beyond_the_tax_tolerance(self):
        items = D("100.00")
        over = items * (1 + LINE_ITEM_TAX_TOLERANCE) + D("0.02")
        assert line_items_mismatch(over, [items]) is not None

    def test_total_at_the_tax_tolerance(self):
        items = D("100.00")
        assert line_items_mismatch(items * (1 + LINE_ITEM_TAX_TOLERANCE), [items]) is None

    def test_no_items(self):
        assert line_items_mismatch(D("84.30"), []) is None


class TestFutureDates:
    def test_tomorrow_is_not_past_tomorrow(self):
        assert not past_tomorrow(TODAY + timedelta(days=1), TODAY)

    def test_the_day_after_is(self):
        assert past_tomorrow(TODAY + timedelta(days=2), TODAY)


class TestModelCents:
    @pytest.mark.parametrize(
        ("value", "cents"),
        [(5.499, D("5.50")), (0.1 + 0.2, D("0.30")), ("19.99", D("19.99")), (2.345, D("2.35"))],
    )
    def test_half_up_to_the_cent(self, value, cents):
        assert model_cents(value) == cents

    @pytest.mark.parametrize("bad", [None, True, False, "abc", "", [], {}, "nan", "inf"])
    def test_no_number_is_none(self, bad):
        assert model_cents(bad) is None


class TestConfidence:
    @pytest.mark.parametrize("checks", [["date"], ["amount"], ["date", "amount"]])
    def test_any_check_caps(self, checks):
        assert capped_confidence(1.0, checks) == CHECKED_CONFIDENCE_CAP

    def test_lower_confidence_is_kept(self):
        assert capped_confidence(0.2, ["date"]) == 0.2

    def test_no_check_leaves_it(self):
        assert capped_confidence(1.0, []) == 1.0
