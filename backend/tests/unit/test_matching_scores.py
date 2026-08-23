"""What a missing payee is allowed to buy.

The two dedup scorers give opposite answers for an unknown payee — 0.5 in
SimpleFIN, 0.0 in matching — and that difference is deliberate. What was not
deliberate is that both were only *safe* by arithmetic nobody had checked: in
each case the weights happen to leave a payee-less pair short of its
auto-accept threshold.

These tests pin that property rather than the constants, so a future weight
change cannot quietly make "we don't know who this was" enough to merge two
transactions without review.
"""

from datetime import date, timedelta

import pytest

from igab.domain.matching import date_proximity, payee_similarity
from igab.services.simplefin_service import (
    DEDUP_AUTO_MATCH_THRESHOLD,
    _calculate_dedup_score,
)
from igab.services.transaction_matching_service import (
    AUTO_ACCEPT_THRESHOLD,
    calculate_confidence,
)

DAY = date(2026, 8, 1)


class TestAnUnknownPayeeCannotReachAutoAccept:
    def test_simplefin_cannot_auto_merge_without_a_payee(self):
        # Best case for everything else: same day, exact amount (prefiltered).
        score = _calculate_dedup_score(None, DAY, None, DAY)
        assert score < DEDUP_AUTO_MATCH_THRESHOLD, (
            "a payee-less pair reached the auto-merge threshold on date alone"
        )

    def test_matching_cannot_auto_match_without_a_payee(self):
        from decimal import Decimal

        score = calculate_confidence(Decimal("10.00"), DAY, "", Decimal("10.00"), DAY, "")
        assert score < AUTO_ACCEPT_THRESHOLD, (
            "a payee-less pair reached the auto-match threshold on date and amount alone"
        )

    @pytest.mark.parametrize("days", [0, 1, 2, 3, 4, 5, 6, 30])
    def test_no_date_offset_rescues_a_missing_payee(self, days):
        other = DAY + timedelta(days=days)
        assert _calculate_dedup_score(None, DAY, None, other) < DEDUP_AUTO_MATCH_THRESHOLD


class TestPayeeSimilarity:
    def test_identical_payees_score_one(self):
        assert payee_similarity("Starbucks", "Starbucks", unknown=0.0) == 1.0

    def test_case_is_ignored(self):
        assert payee_similarity("STARBUCKS", "starbucks", unknown=0.0) == 1.0

    def test_a_bank_description_matches_a_cleaned_name(self):
        assert payee_similarity("STARBUCKS #12345", "Starbucks", unknown=0.0) >= 0.85

    def test_unrelated_payees_score_low(self):
        assert payee_similarity("Starbucks", "Shell Oil", unknown=0.0) < 0.6

    @pytest.mark.parametrize(("a", "b"), [(None, "x"), ("x", None), (None, None), ("", "x")])
    def test_the_unknown_value_is_the_callers_choice(self, a, b):
        assert payee_similarity(a, b, unknown=0.5) == 0.5
        assert payee_similarity(a, b, unknown=0.0) == 0.0


class TestDateProximity:
    def test_same_day_is_one(self):
        # The short-circuit one copy had was redundant: 1 - 0/(w+1) is already 1.
        assert date_proximity(DAY, DAY) == 1.0

    def test_decays_with_distance(self):
        assert date_proximity(DAY, DAY + timedelta(days=1)) == pytest.approx(1 - 1 / 6)
        assert date_proximity(DAY, DAY + timedelta(days=5)) == pytest.approx(1 - 5 / 6)

    def test_zero_past_the_window(self):
        assert date_proximity(DAY, DAY + timedelta(days=6)) == 0.0
        assert date_proximity(DAY, DAY + timedelta(days=365)) == 0.0

    def test_is_symmetric(self):
        later = DAY + timedelta(days=3)
        assert date_proximity(DAY, later) == date_proximity(later, DAY)

    def test_window_is_honoured(self):
        assert date_proximity(DAY, DAY + timedelta(days=2), window_days=1) == 0.0
        assert date_proximity(DAY, DAY + timedelta(days=2), window_days=10) > 0.0
