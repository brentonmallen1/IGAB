"""parse_extraction() is the single mapping from model JSON to transaction
drafts — every amount/date/category/split edge case is exercised here."""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.domain.receipt_checks import CHECKED_CONFIDENCE_CAP, LOOPING_RUN, ReceiptCheck
from igab.services.ai_draft_service import RAW_CUT_SHORT, parse_extraction

TODAY = date(2026, 8, 2)
CATEGORIES = {"Groceries", "Household Supplies", "Dining Out"}


def receipt(**overrides) -> dict:
    base = {
        "payee": "Whole Foods",
        "total": 42.50,
        "date": "2026-08-01",
        "category": "Groceries",
        "confidence": 0.9,
        "memo": None,
    }
    base.update(overrides)
    return base


class TestReceiptAmounts:
    def test_positive_total_becomes_outflow(self):
        draft = parse_extraction(
            receipt(total=42.50), kind="receipt", client_today=TODAY, category_names=CATEGORIES
        )
        assert draft.amount == Decimal("-42.50")

    def test_negative_total_is_refund_inflow(self):
        draft = parse_extraction(
            receipt(total=-12.00), kind="receipt", client_today=TODAY, category_names=CATEGORIES
        )
        assert draft.amount == Decimal("12.00")

    def test_rounding_half_up(self):
        draft = parse_extraction(
            receipt(total=5.499), kind="receipt", client_today=TODAY, category_names=CATEGORIES
        )
        assert draft.amount == Decimal("-5.50")

    def test_string_total_parses(self):
        draft = parse_extraction(
            receipt(total="19.99"), kind="receipt", client_today=TODAY, category_names=CATEGORIES
        )
        assert draft.amount == Decimal("-19.99")

    def test_float_precision_artifacts_quantized(self):
        draft = parse_extraction(receipt(total=0.1 + 0.2), kind="receipt", client_today=TODAY)
        assert draft.amount == Decimal("-0.30")

    @pytest.mark.parametrize(
        "bad", [0, 0.0, "0.00", None, "abc", "", [], {}, True, False, "NaN", "inf"]
    )
    def test_zero_or_garbage_total_raises(self, bad):
        with pytest.raises(InvariantViolation):
            parse_extraction(
                receipt(total=bad), kind="receipt", client_today=TODAY, category_names=CATEGORIES
            )


class TestNLAmounts:
    def nl(self, **overrides) -> dict:
        base = {
            "payee": "Starbucks",
            "amount": 5.50,
            "direction": "outflow",
            "date": "2026-08-01",
            "category": "Dining Out",
            "confidence": 0.8,
            "memo": None,
        }
        base.update(overrides)
        return base

    def test_outflow_negative(self):
        draft = parse_extraction(
            self.nl(), kind="nl_parse", client_today=TODAY, category_names=CATEGORIES
        )
        assert draft.amount == Decimal("-5.50")

    def test_inflow_positive(self):
        draft = parse_extraction(
            self.nl(direction="inflow", amount=100),
            kind="nl_parse",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.amount == Decimal("100.00")

    def test_negative_amount_with_outflow_direction_still_outflow(self):
        # Model sometimes pre-negates; sign comes from direction alone.
        draft = parse_extraction(self.nl(amount=-5.50), kind="nl_parse", client_today=TODAY)
        assert draft.amount == Decimal("-5.50")

    def test_missing_direction_defaults_outflow(self):
        draft = parse_extraction(self.nl(direction=None), kind="nl_parse", client_today=TODAY)
        assert draft.amount == Decimal("-5.50")

    def test_unknown_kind_raises(self):
        with pytest.raises(InvariantViolation):
            parse_extraction(self.nl(), kind="mystery", client_today=TODAY)


class TestDates:
    def test_iso_date(self):
        draft = parse_extraction(receipt(date="2026-07-14"), kind="receipt", client_today=TODAY)
        assert draft.date == date(2026, 7, 14)

    def test_us_format_fallback(self):
        draft = parse_extraction(receipt(date="07/14/2026"), kind="receipt", client_today=TODAY)
        assert draft.date == date(2026, 7, 14)

    def test_european_format_fallback(self):
        draft = parse_extraction(receipt(date="14.07.2026"), kind="receipt", client_today=TODAY)
        assert draft.date == date(2026, 7, 14)

    def test_non_padded_iso(self):
        # date.fromisoformat handles 2026-7-3 on 3.11+
        draft = parse_extraction(receipt(date="2026-7-3"), kind="receipt", client_today=TODAY)
        assert draft.date == date(2026, 7, 3)

    @pytest.mark.parametrize("bad", ["yesterday", "not a date", "", None, 20260714])
    def test_garbage_falls_back_to_today(self, bad):
        draft = parse_extraction(receipt(date=bad), kind="receipt", client_today=TODAY)
        assert draft.date == TODAY

    def test_far_future_clamped_to_today(self):
        draft = parse_extraction(receipt(date="2027-01-01"), kind="receipt", client_today=TODAY)
        assert draft.date == TODAY

    def test_tomorrow_allowed(self):
        # One day of slack for timezone skew between client and receipt
        draft = parse_extraction(receipt(date="2026-08-03"), kind="receipt", client_today=TODAY)
        assert draft.date == date(2026, 8, 3)

    def test_two_years_back_is_today_with_a_check(self):
        """A reverse-video date line read ~2 years early (reported 2026-11-17):
        the draft takes today, flags the date, and keeps what was read."""
        draft = parse_extraction(
            receipt(date="2024-08-01", confidence=1.0), kind="receipt", client_today=TODAY
        )
        assert draft.date == TODAY
        assert draft.checks == ["date"]
        assert draft.date_read == date(2024, 8, 1)
        assert draft.confidence == CHECKED_CONFIDENCE_CAP

    def test_a_recent_date_is_not_flagged(self):
        draft = parse_extraction(receipt(date="2026-07-14"), kind="receipt", client_today=TODAY)
        assert draft.checks == [] and draft.date_read is None

    def test_unreadable_date_is_today_without_a_check(self):
        draft = parse_extraction(receipt(date=None), kind="receipt", client_today=TODAY)
        assert draft.date == TODAY and draft.checks == []

    def test_a_description_keeps_an_old_date(self):
        """A person typing a date long past means it — the window is a
        receipt's."""
        draft = parse_extraction(
            {"amount": 20, "direction": "outflow", "date": "2024-08-01"},
            kind="nl_parse",
            client_today=TODAY,
        )
        assert draft.date == date(2024, 8, 1) and draft.checks == []

    def test_a_description_in_the_future_is_today(self):
        draft = parse_extraction(
            {"amount": 20, "date": "2027-01-01"}, kind="nl_parse", client_today=TODAY
        )
        assert draft.date == TODAY


class TestAmountChecks:
    def test_tender_mismatch_checks_the_amount_and_caps_confidence(self):
        """The TOTAL bar read with its cents dropped; the card line has them."""
        draft = parse_extraction(
            receipt(total=84.00, tender_amount=84.30, confidence=1.0),
            kind="receipt",
            client_today=TODAY,
        )
        assert draft.checks == ["amount"]
        assert draft.tender_amount == Decimal("84.30")
        assert draft.confidence == CHECKED_CONFIDENCE_CAP
        assert draft.amount == Decimal("-84.00")  # flagged, not overridden

    def test_agreeing_tender_is_not_flagged(self):
        draft = parse_extraction(
            receipt(total=84.30, tender_amount=84.30, confidence=0.9),
            kind="receipt",
            client_today=TODAY,
        )
        assert draft.checks == [] and draft.confidence == 0.9

    def test_line_item_mismatch_checks_the_amount_and_caps_confidence(self):
        """Discounts added as charges: the items come to more than was paid."""
        items = [
            {"description": "SHALLOTS", "amount": 80.00, "category": None},
            {"description": "TOWELS", "amount": 12.00, "category": None},
            {"description": "INSTANT SAVINGS", "amount": 2.30, "category": None},
        ]
        draft = parse_extraction(
            receipt(total=84.30, line_items=items, confidence=1.0),
            kind="receipt",
            client_today=TODAY,
        )
        assert draft.checks == ["amount"]
        assert draft.line_items_total == Decimal("94.30")
        assert draft.confidence == CHECKED_CONFIDENCE_CAP

    def test_line_items_with_discounts_negative_reconcile(self):
        items = [
            {"description": "SHALLOTS", "amount": 80.00, "category": None},
            {"description": "INSTANT SAVINGS", "amount": -2.30, "category": None},
        ]
        draft = parse_extraction(
            receipt(total=83.92, line_items=items), kind="receipt", client_today=TODAY
        )
        assert draft.checks == []

    def test_an_unreadable_line_skips_the_check(self):
        items = [
            {"description": "A", "amount": 80.00, "category": None},
            {"description": "B", "amount": "??", "category": None},
        ]
        draft = parse_extraction(
            receipt(total=10.00, line_items=items), kind="receipt", client_today=TODAY
        )
        assert draft.checks == []

    def test_both_fields_flagged_together(self):
        draft = parse_extraction(
            receipt(date="2024-08-01", total=84.00, tender_amount=84.30),
            kind="receipt",
            client_today=TODAY,
        )
        assert draft.checks == ["date", "amount"]

    def test_the_checks_are_served(self):
        from igab.services.ai_draft_service import draft_result_json

        draft = parse_extraction(
            receipt(date="2024-08-01", total=84.00, tender_amount=84.30),
            kind="receipt",
            client_today=TODAY,
        )
        served = draft_result_json(draft)["draft"]
        assert served["checks"] == ["date", "amount"]
        assert served["date_read"] == "2024-08-01"
        assert served["date"] == TODAY.isoformat()
        assert served["tender_amount"] == "84.30"
        assert served["line_items_total"] is None


class TestCategories:
    def test_exact_match_kept(self):
        draft = parse_extraction(
            receipt(category="Groceries"),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.category_name == "Groceries"

    def test_case_insensitive_match(self):
        draft = parse_extraction(
            receipt(category="gRoCeRiEs"),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.category_name == "Groceries"  # canonicalized to the real name

    def test_invented_category_dropped(self):
        draft = parse_extraction(
            receipt(category="Fun Money"),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.category_name is None

    def test_an_unresolved_name_is_kept_as_the_models_opinion(self):
        draft = parse_extraction(
            receipt(category="Fun Money"),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.category_unresolved == "Fun Money"

    def test_a_resolved_or_absent_name_is_not_unresolved(self):
        for value in ("Groceries", None, "", "   "):
            draft = parse_extraction(
                receipt(category=value),
                kind="receipt",
                client_today=TODAY,
                category_names=CATEGORIES,
            )
            assert draft.category_unresolved is None, value

    def test_an_ambiguous_name_is_unresolved(self):
        draft = parse_extraction(
            receipt(category="Gifts"),
            kind="receipt",
            client_today=TODAY,
            category_names=[("Gifts", "A"), ("Gifts", "B")],
        )
        assert draft.category_name is None
        assert draft.category_unresolved == "Gifts"

    def test_no_category_names_provided_drops_category(self):
        draft = parse_extraction(receipt(category="Groceries"), kind="receipt", client_today=TODAY)
        assert draft.category_name is None


class TestPayeeMemoConfidence:
    def test_empty_payee_is_none(self):
        for value in ("", "   ", None, 42):
            draft = parse_extraction(receipt(payee=value), kind="receipt", client_today=TODAY)
            assert draft.payee_name is None

    def test_payee_whitespace_stripped(self):
        draft = parse_extraction(receipt(payee="  Costco  "), kind="receipt", client_today=TODAY)
        assert draft.payee_name == "Costco"

    def test_confidence_clamped(self):
        assert (
            parse_extraction(receipt(confidence=7), kind="receipt", client_today=TODAY).confidence
            == 1.0
        )
        assert (
            parse_extraction(receipt(confidence=-1), kind="receipt", client_today=TODAY).confidence
            == 0.0
        )
        assert (
            parse_extraction(
                receipt(confidence="high"), kind="receipt", client_today=TODAY
            ).confidence
            == 0.0
        )


class TestSuggestedSplit:
    def split_receipt(self, split, total=100.00) -> dict:
        return receipt(total=total, suggested_split=split)

    def test_valid_split_offered_with_outflow_signs(self):
        draft = parse_extraction(
            self.split_receipt(
                [
                    {"category": "Groceries", "amount": 60.00},
                    {"category": "Household Supplies", "amount": 40.00},
                ]
            ),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.suggested_split is not None
        assert [s.amount for s in draft.suggested_split] == [
            Decimal("-60.00"),
            Decimal("-40.00"),
        ]
        assert sum(s.amount for s in draft.suggested_split) == draft.amount

    def test_uneven_cents_within_tolerance(self):
        # 3 × 3.33 + 0.01 rounding: lines sum to 9.99 vs total 10.00 → within 1 cent
        draft = parse_extraction(
            self.split_receipt(
                [
                    {"category": "Groceries", "amount": 3.33},
                    {"category": "Groceries", "amount": 3.33},
                    {"category": "Groceries", "amount": 3.33},
                ],
                total=10.00,
            ),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.suggested_split is not None

    def test_sum_mismatch_drops_split(self):
        draft = parse_extraction(
            self.split_receipt(
                [
                    {"category": "Groceries", "amount": 60.00},
                    {"category": "Household Supplies", "amount": 20.00},
                ]
            ),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.suggested_split is None

    def test_unknown_category_drops_split(self):
        draft = parse_extraction(
            self.split_receipt(
                [
                    {"category": "Groceries", "amount": 60.00},
                    {"category": "Alcohol", "amount": 40.00},
                ]
            ),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.suggested_split is None

    def test_single_line_split_dropped(self):
        draft = parse_extraction(
            self.split_receipt([{"category": "Groceries", "amount": 100.00}]),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.suggested_split is None

    def test_zero_line_drops_split(self):
        draft = parse_extraction(
            self.split_receipt(
                [
                    {"category": "Groceries", "amount": 100.00},
                    {"category": "Dining Out", "amount": 0},
                ]
            ),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.suggested_split is None

    def test_garbage_split_shapes_dropped(self):
        for bad in ("split", 42, [{"category": "Groceries"}], ["a", "b"], None, {}):
            draft = parse_extraction(
                self.split_receipt(bad),
                kind="receipt",
                client_today=TODAY,
                category_names=CATEGORIES,
            )
            assert draft.suggested_split is None

    def test_refund_split_carries_inflow_signs(self):
        draft = parse_extraction(
            self.split_receipt(
                [
                    {"category": "Groceries", "amount": 60.00},
                    {"category": "Household Supplies", "amount": 40.00},
                ],
                total=-100.00,
            ),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.suggested_split is not None
        assert all(s.amount > 0 for s in draft.suggested_split)
        assert sum(s.amount for s in draft.suggested_split) == Decimal("100.00")

    def test_nl_parse_never_offers_split(self):
        draft = parse_extraction(
            {
                "payee": "Costco",
                "amount": 100,
                "direction": "outflow",
                "date": "2026-08-01",
                "category": None,
                "confidence": 0.9,
                "suggested_split": [
                    {"category": "Groceries", "amount": 60.00},
                    {"category": "Household Supplies", "amount": 40.00},
                ],
            },
            kind="nl_parse",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.suggested_split is None


class TestCardEnding:
    def test_the_card_that_paid_is_read_off_the_receipt(self):
        draft = parse_extraction(
            receipt(card_last4="VISA ****4417"), kind="receipt", client_today=TODAY
        )
        assert draft.card_last4 == "4417"

    def test_cash_or_no_number_is_no_card(self):
        for value in (None, "", "cash", "**17"):
            draft = parse_extraction(receipt(card_last4=value), kind="receipt", client_today=TODAY)
            assert draft.card_last4 is None, value

    def test_a_prompt_that_never_asks_leaves_it_empty(self):
        # A customized prompt from before the field existed returns no key.
        draft = parse_extraction(receipt(), kind="receipt", client_today=TODAY)
        assert draft.card_last4 is None

    def test_the_recorded_result_carries_it(self):
        from igab.services.ai_draft_service import draft_result_json

        draft = parse_extraction(receipt(card_last4="4417"), kind="receipt", client_today=TODAY)
        assert draft_result_json(draft)["draft"]["card_last4"] == "4417"


class TestTooLongToItemize:
    """A reply cut short in its items, or looping in them, keeps payee, total
    and date, offers no split, and says why."""

    SPLIT = [{"category": "Groceries", "amount": 30.0}, {"category": "Dining Out", "amount": 12.5}]

    def test_a_salvaged_read_is_flagged_and_unsplit(self):
        draft = parse_extraction(
            receipt(**{RAW_CUT_SHORT: "repetition"}),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.amount == Decimal("-42.50")
        assert draft.payee_name == "Whole Foods"
        assert draft.checks == [ReceiptCheck.ITEMS]
        assert draft.suggested_split is None
        assert draft.confidence == CHECKED_CONFIDENCE_CAP

    def test_a_finished_reply_that_looped_is_treated_the_same(self):
        loop = [{"description": "SOAP", "amount": 1.0, "category": None}] * LOOPING_RUN
        draft = parse_extraction(
            receipt(line_items=loop, suggested_split=self.SPLIT),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.checks == [ReceiptCheck.ITEMS]
        assert draft.suggested_split is None
        assert draft.line_items_total is None

    def test_an_honest_itemized_read_is_not_flagged(self):
        draft = parse_extraction(
            receipt(suggested_split=self.SPLIT),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert ReceiptCheck.ITEMS not in draft.checks
        assert draft.suggested_split is not None

    def test_one_line_for_everything_is_not_an_itemized_read(self):
        """A sideways photo (reported 2026-11-18): one "various items" line
        equal to the total made the line-item check pass on a read that was
        wrong everywhere else."""
        draft = parse_extraction(
            receipt(line_items=[{"description": "Various items", "amount": 42.5}]),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.checks == [ReceiptCheck.ITEMS]
        assert draft.confidence == CHECKED_CONFIDENCE_CAP

    def test_a_receipt_for_one_real_item_is_itemized(self):
        draft = parse_extraction(
            receipt(line_items=[{"description": "KS OLIVE OIL 2L", "amount": 42.5}]),
            kind="receipt",
            client_today=TODAY,
            category_names=CATEGORIES,
        )
        assert draft.checks == []


class TestACategoryNamedAfterTheStore:
    """A sinking fund named after a store (its membership fee) took a whole
    grocery shop there, matched on the name alone (reported 2026-11-18)."""

    NAMES = [("Groceries", "Food"), ("Northwind Club", "Annual Expenses"), ("Dining Out", "Food")]

    def parse(self, **overrides):
        raw = receipt(payee="Northwind Club Wholesale", category="Northwind Club", **overrides)
        return parse_extraction(raw, kind="receipt", client_today=TODAY, category_names=self.NAMES)

    def items(self, *pairs):
        return [
            {"description": f"ITEM {n}", "amount": a, "category": c}
            for n, (c, a) in enumerate(pairs)
        ]

    def test_the_line_items_overrule_it(self):
        draft = self.parse(
            line_items=self.items(("Groceries", 30), ("Groceries", 8), ("Dining Out", 4.5))
        )
        assert draft.category_name == "Groceries"
        assert (draft.category_model, draft.category_from) == ("Northwind Club", "items")
        assert draft.category_suspect is False

    def test_the_items_of_a_cut_short_read_still_vote(self):
        draft = self.parse(
            line_items=self.items(("Groceries", 30), ("Groceries", 8)),
            **{RAW_CUT_SHORT: "length"},
        )
        assert draft.category_name == "Groceries"
        assert draft.suggested_split is None

    def test_items_that_agree_with_it_confirm_it(self):
        """The yearly fee itself, on its own receipt."""
        draft = self.parse(line_items=self.items(("Northwind Club", 42.5)))
        assert draft.category_name == "Northwind Club"
        assert draft.category_model is None
        assert draft.category_suspect is False

    def test_with_no_items_to_ask_it_is_left_for_payee_history(self):
        draft = self.parse()
        assert draft.category_name == "Northwind Club"
        assert draft.category_suspect is True

    def test_items_without_a_majority_do_not_decide(self):
        draft = self.parse(line_items=self.items(("Groceries", 20), ("Dining Out", 20)))
        assert draft.category_name == "Northwind Club"
        assert draft.category_suspect is True

    def test_a_category_that_is_not_the_stores_name_is_never_second_guessed(self):
        draft = parse_extraction(
            receipt(line_items=self.items(("Dining Out", 42.5))),
            kind="receipt",
            client_today=TODAY,
            category_names=self.NAMES,
        )
        assert draft.category_name == "Groceries"
        assert draft.category_suspect is False
