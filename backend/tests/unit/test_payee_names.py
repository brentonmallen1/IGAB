"""domain.payee_names: the noise a bank appends is not the merchant."""

import json
import re
from pathlib import Path

import pytest
from rapidfuzz import fuzz

from igab.domain.payee_names import (
    dedupe_samples,
    pattern_matches,
    rank_match_patterns,
    samples_from_legacy,
    similarity_key,
)

#: Run by the frontend too (payeeSamples.test.ts) — one rule, two languages.
_SAMPLE_CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "sample_cases.json").read_text()
)["cases"]


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("EMPLOYER PAYROLL #4821", "employer payroll"),
        ("ACME CORP PAYROLL #1234567890", "acme corp payroll"),
        # Date-like tokens: six digits, or six digits split by slashes — count
        # the digits in the token, not a run of three.
        ("EMPLOYER PAYROLL 240815", "employer payroll"),
        ("ACH DEPOSIT PAYROLL 08/15/26", "ach deposit payroll"),
        ("PAYROLL 2026-08-15 REF 88231", "payroll ref"),
        ("AMZN Mktp US*1A2B3", "amzn mktp us"),
        ("STARBUCKS #1234", "starbucks"),
        # A marker with no digit behind it is the name — Square prefixes its
        # merchants "SQ *", Toast "TST*".
        ("SQ *COFFEE HOUSE", "sq coffee house"),
        ("TST* BURGER JOINT", "tst burger joint"),
        # One or two digits are names, not noise.
        ("Rental Unit 1", "rental unit 1"),
        ("7-Eleven", "7 eleven"),
        ("Forever 21 #204", "forever 21"),
        ("24 Hour Fitness", "24 hour fitness"),
        ("H&R Block", "h&r block"),
        ("The Home Depot", "the home depot"),
        # Stripping would leave nothing: fall back to the collapsed name.
        ("1-800-FLOWERS", "1 800 flowers"),
        ("#1234", "1234"),
    ],
)
def test_similarity_key(name: str, key: str) -> None:
    assert similarity_key(name) == key


def test_the_key_is_what_lets_payroll_postings_agree() -> None:
    a, b = "ACME CORP PAYROLL #1234567890", "ACME CORP PAYROLL #9876543210"
    # The raw strings miss the Balanced (75) threshold; the keys are identical.
    assert fuzz.token_set_ratio(a.lower(), b.lower()) < 75
    assert fuzz.token_set_ratio(similarity_key(a), similarity_key(b)) == 100


@pytest.mark.parametrize("case", _SAMPLE_CASES, ids=[c["note"] for c in _SAMPLE_CASES])
def test_dedupe_samples_shared_cases(case: dict) -> None:
    assert dedupe_samples(case["parts"]) == case["samples"]


class TestSamplesFromLegacy:
    def test_the_old_comma_string_splits_one_last_time(self) -> None:
        assert samples_from_legacy("ADP PAYROLL, adp payroll , ADP TOTALSOURCE") == [
            "ADP PAYROLL",
            "ADP TOTALSOURCE",
        ]

    def test_a_list_is_normalized_and_anything_else_is_empty(self) -> None:
        assert samples_from_legacy([" A ", "a", "B"]) == ["A", "B"]
        assert samples_from_legacy(None) == []
        assert samples_from_legacy(42) == []


class TestRankMatchPatterns:
    NAMES = ["ACH DEPOSIT PAYROLL 88", "ACH DEPOSIT PAYROLL 99"]

    def test_keeps_the_proposal_order_among_equals(self) -> None:
        proposed = ["^ACH DEPOSIT PAYROLL [0-9]+$", "^ACH DEPOSIT PAYROLL ", "PAYROLL"]
        assert rank_match_patterns(proposed, self.NAMES, 3) == proposed

    def test_wider_coverage_ranks_first(self) -> None:
        # "PAYROLL 88" misses the second name: offered, but after the one that
        # matches both — the caller shows the count beside each.
        assert rank_match_patterns(["PAYROLL 88", "^ACH"], self.NAMES, 3) == ["^ACH", "PAYROLL 88"]

    def test_one_stray_sample_does_not_blank_the_answer(self) -> None:
        # A bank name split on its own comma leaves "BRENTON" in the list; the
        # obvious pattern still comes back, 20 of 21.
        names = [f"ADP TOTALSOURCE PAYROLL 2608{d:02d} 3800841151{d:02d}" for d in range(1, 21)]
        names.append("BRENTON")
        assert rank_match_patterns(["^ADP TOTALSOURCE PAYROLL "], names, 3) == [
            "^ADP TOTALSOURCE PAYROLL "
        ]

    def test_matching_nothing_is_dropped(self) -> None:
        assert rank_match_patterns(["RENT", "^ACH"], self.NAMES, 3) == ["^ACH"]

    def test_invalid_blank_and_non_string_candidates_are_dropped(self) -> None:
        assert rank_match_patterns(["([bad", "  ", 42, None, "^ACH"], self.NAMES, 3) == ["^ACH"]

    def test_duplicates_collapse_and_the_limit_holds(self) -> None:
        proposed = ["^ACH", "^ACH", "DEPOSIT", "PAYROLL", "ACH"]
        assert rank_match_patterns(proposed, self.NAMES, 3) == ["^ACH", "DEPOSIT", "PAYROLL"]

    def test_a_trailing_space_survives_the_trim(self) -> None:
        assert rank_match_patterns(["^ACH DEPOSIT PAYROLL \n"], self.NAMES, 3) == [
            "^ACH DEPOSIT PAYROLL "
        ]


class TestPatternMatches:
    def test_case_insensitive_and_unanchored(self) -> None:
        assert pattern_matches("payroll", "ACH DEPOSIT PAYROLL 123")
        assert pattern_matches("^ACH DEPOSIT PAYROLL ", "ach deposit payroll 99")

    def test_no_match(self) -> None:
        assert not pattern_matches("^PAYROLL", "ACH DEPOSIT PAYROLL 123")

    def test_a_bad_pattern_raises_rather_than_answering(self) -> None:
        with pytest.raises(re.error):
            pattern_matches("([bad", "anything")
