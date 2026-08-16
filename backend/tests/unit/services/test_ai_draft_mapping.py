"""parse_extraction() is the single mapping from model JSON to transaction
drafts — every amount/date/category/split edge case is exercised here."""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.services.ai_draft_service import parse_extraction

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
        draft = parse_extraction(
            receipt(total=0.1 + 0.2), kind="receipt", client_today=TODAY
        )
        assert draft.amount == Decimal("-0.30")

    @pytest.mark.parametrize("bad", [0, 0.0, "0.00", None, "abc", "", [], {}, True, False])
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
        draft = parse_extraction(
            self.nl(amount=-5.50), kind="nl_parse", client_today=TODAY
        )
        assert draft.amount == Decimal("-5.50")

    def test_missing_direction_defaults_outflow(self):
        draft = parse_extraction(
            self.nl(direction=None), kind="nl_parse", client_today=TODAY
        )
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
        # date.fromisoformat handles 2026-2-3 on 3.11+
        draft = parse_extraction(receipt(date="2026-2-3"), kind="receipt", client_today=TODAY)
        assert draft.date == date(2026, 2, 3)

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
            parse_extraction(
                receipt(confidence=-1), kind="receipt", client_today=TODAY
            ).confidence
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
