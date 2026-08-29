"""domain.payee_names: the noise a bank appends is not the merchant."""

import json
import re
from pathlib import Path

import pytest
from rapidfuzz import fuzz

from igab.domain.payee_names import (
    dedupe_samples,
    distinctive_key,
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


class TestDistinctiveKey:
    """Is there a merchant in this string at all?

    The question `similarity_key` cannot answer, and the one that decides
    whether fuzzy matching may run. `token_set_ratio` scores a subset 100, so
    a raw name made only of banking vocabulary ties at 100 against every payee
    containing one of its words and the "best" match is whichever the loop
    reached first.
    """

    #: What SimpleFIN actually sent on the Citi register, verbatim. The first
    #: two filed $10,852 of card payments into the Internet envelope and three
    #: interest charges into Ready to Assign.
    @pytest.mark.parametrize(
        "raw",
        [
            "Payment",
            "Interest Charge",
            "ONLINE PAYMENT, THANK YOU",
            "PENDING PURCHASE",
            "ACH CREDIT",
            "Refund",
        ],
    )
    def test_a_name_that_is_all_banking_vocabulary_has_no_merchant(self, raw: str) -> None:
        assert distinctive_key(raw) == ""

    @pytest.mark.parametrize(
        ("raw", "key"),
        [
            # The generic word goes, the merchant stays.
            ("Att Payment Brenton Mallen", "att brenton mallen"),
            ("Interest Payment", ""),
            ("CITI CARD ONLINE PAYMENT 260816", "citi"),
            # Untouched: no banking vocabulary in them at all.
            ("ADP Totalsource", "adp totalsource"),
            ("Honda Financial", "honda financial"),
            ("Nordstrom Rack", "nordstrom rack"),
            ("Apple Pay", "apple pay"),
        ],
    )
    def test_only_the_banking_words_are_dropped(self, raw: str, key: str) -> None:
        assert distinctive_key(raw) == key

    def test_it_does_not_change_similarity_key(self) -> None:
        """The comparison key is Payee Cleanup's too, and dropping these words
        from it would make "Interest Payment" and "Att Payment Brenton Mallen"
        *more* alike, not less. Two questions, two functions."""
        assert similarity_key("Payment") == "payment"
        assert similarity_key("Interest Charge") == "interest charge"


class TestSubsetMatchingStaysCorrect:
    """The subset rule is not the bug — only a subset with no merchant in it.

    Every pair here is real: taken from a budget whose 49 distinct
    (bank name, resolved payee) pairs were replayed through the guard. The
    good ones score 100 by subset and must keep doing so; the bad ones score
    100 the same way and must never be reached.
    """

    GOOD = [
        ("ADP Totalsource", "ADP"),
        ("Honda Financial", "Honda"),
        ("Nordstrom Rack", "Nordstrom"),
        ("Pincushion Fabrics", "Pincushion"),
        ("Apple", "Apple Pay"),
        ("Hue Loco Hue L", "Hue Loco"),
    ]
    #: (raw bank name, the candidate string that scored 100 for it). The
    #: candidate is a payee's name or one of its `mapping_samples` — the
    #: interest charges matched the sample "Interest", not the payee name
    #: "Interest Payment", which scores only 71. Both routes are the same
    #: defect and the guard closes both, because it runs before either.
    BAD = [
        ("Payment", "Att Payment Brenton Mallen"),
        ("Payment", "Interest Payment"),
        ("Payment", "Payment Authorized Chewy.com FL"),
        ("Interest Charge", "Interest"),
    ]

    @pytest.mark.parametrize(("raw", "payee"), GOOD)
    def test_a_real_merchant_subset_still_scores_and_is_still_asked(
        self, raw: str, payee: str
    ) -> None:
        assert fuzz.token_set_ratio(similarity_key(raw), similarity_key(payee)) >= 80
        assert distinctive_key(raw) != ""

    @pytest.mark.parametrize(("raw", "candidate"), BAD)
    def test_a_banking_word_scores_just_as_high_and_is_never_asked(
        self, raw: str, candidate: str
    ) -> None:
        # A perfect score, on nothing. This is why raising the threshold could
        # not have fixed it and why the guard has to run before the scoring.
        assert fuzz.token_set_ratio(similarity_key(raw), similarity_key(candidate)) == 100
        assert distinctive_key(raw) == ""
