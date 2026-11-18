"""The plausibility checks on a receipt's read — every edge by name."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.money import model_cents
from igab.domain.receipt_checks import (
    CHECKED_CONFIDENCE_CAP,
    LINE_ITEM_TAX_TOLERANCE,
    LOOPING_RUN,
    RECEIPT_DATE_WINDOW_DAYS,
    capped_confidence,
    checked_receipt_date,
    items_overshoot,
    line_items_mismatch,
    looping_items,
    named_for_payee,
    past_tomorrow,
    summary_line,
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


class TestLoopingItems:
    def item(self, name="SOAP", amount=1.99):
        return {"description": name, "amount": amount, "category": None}

    def test_a_run_of_eight_is_a_loop(self):
        assert looping_items([self.item("A"), *[self.item()] * LOOPING_RUN])

    def test_three_of_the_same_yogurt_is_a_receipt(self):
        assert not looping_items([self.item("YOGURT")] * 3 + [self.item("MILK")])

    def test_a_run_broken_by_another_item_starts_over(self):
        half = [self.item()] * (LOOPING_RUN - 1)
        assert not looping_items([*half, self.item("MILK"), *half])

    def test_the_same_name_at_another_price_is_not_a_repeat(self):
        assert not looping_items([self.item(amount=float(n)) for n in range(LOOPING_RUN)])

    def test_non_items_break_a_run(self):
        assert not looping_items(["x"] * LOOPING_RUN)

    def test_counting_up_is_still_a_loop(self):
        """Reported 2026-11-18: the same item with its code going up by one
        each time ran to the 80-item cap, because no two were identical."""
        counting = [self.item(f"0000392{n:02d} ITEM") for n in range(LOOPING_RUN)]
        assert looping_items(counting)

    def test_numbered_items_at_different_prices_are_a_receipt(self):
        priced = [self.item(f"KS WATER {n}PK", amount=n + 0.99) for n in range(LOOPING_RUN)]
        assert not looping_items(priced)


class TestItemsOvershoot:
    def items(self, *amounts):
        return [{"description": f"ITEM {n}", "amount": a} for n, a in enumerate(amounts)]

    def test_items_far_past_the_total_have_run_away(self):
        assert items_overshoot(self.items(30, 30, 30), 40)

    def test_a_discounted_receipt_has_not(self):
        """Items listed before a 40%-off coupon sum well past the total."""
        assert not items_overshoot(self.items(50, 50), 60)

    def test_negative_lines_count_against_the_sum(self):
        assert not items_overshoot(self.items(60, 60, -50), 40)

    @pytest.mark.parametrize("total", [None, 0, -12.5, "abc"])
    def test_no_usable_total_never_stops_a_read(self, total):
        assert not items_overshoot(self.items(500), total)


class TestNamedForPayee:
    @pytest.mark.parametrize(
        ("category", "payee"),
        [
            ("Northwind Club", "Northwind Club Wholesale"),
            ("Northwind Club Membership", "Northwind Club"),
            ("🛒 Harborstone", "HARBORSTONE MARKET"),
        ],
    )
    def test_every_word_of_one_in_the_other(self, category, payee):
        assert named_for_payee(category, payee)

    @pytest.mark.parametrize(
        ("category", "payee"),
        [
            ("Groceries", "Harborstone Market"),
            ("Club Dues", "Northwind Club"),
            ("Gas", None),
            ("", "X"),
        ],
    )
    def test_anything_less_is_not(self, category, payee):
        assert not named_for_payee(category, payee)


class TestSummaryLine:
    def line(self, description, amount=42.5):
        return [{"description": description, "amount": amount}]

    @pytest.mark.parametrize("words", ["Various items", "GROCERIES", "Misc. merchandise"])
    def test_general_words_for_the_whole_total(self, words):
        assert summary_line(self.line(words), D("42.50"))

    def test_a_named_item_is_an_item(self):
        assert not summary_line(self.line("KS OLIVE OIL 2L"), D("42.50"))

    def test_general_words_for_part_of_the_total_are_an_item(self):
        assert not summary_line(self.line("Various items", 10), D("42.50"))

    def test_two_lines_are_a_list(self):
        assert not summary_line(self.line("Items") * 2, D("42.50"))
