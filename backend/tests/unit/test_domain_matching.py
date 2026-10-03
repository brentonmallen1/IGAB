"""The dedup ladder — domain.matching.decide_match.

One ladder, two callers: the SimpleFIN sync posts every feed record through
it and the CSV import every file line. These tests moved here with it from
the sync's own suite; the cases a bank CSV over another app's history adds
are at the bottom.
"""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from igab.domain.matching import (
    DEDUP_AUTO_MATCH_THRESHOLD,
    MatchCandidate,
    MatchDecision,
    decide_match,
    settles_in_strict_pass,
)

TODAY = date(2026, 3, 16)


def _candidate(
    *,
    days_ago: int = 0,
    payee: str | None = None,
    bank_payee: str | None = None,
    import_description: str | None = None,
    bank_posted_date: date | None = None,
) -> MatchCandidate:
    row = SimpleNamespace(
        id=uuid.uuid4(),
        date=TODAY - timedelta(days=days_ago),
        bank_payee=bank_payee,
        import_description=import_description,
        bank_posted_date=bank_posted_date,
    )
    return MatchCandidate.from_row(row, payee)


class TestMatchCandidate:
    def test_reads_every_string_the_row_keeps(self):
        c = _candidate(payee="Trader Joe's", bank_payee="TJ #552", import_description="TJ")
        assert c.payee_strings == ("Trader Joe's", "TJ #552", "TJ")
        assert c.bank_words is True

    def test_a_typed_row_has_no_bank_words(self):
        assert _candidate(payee="Rent").bank_words is False

    def test_compares_on_the_banks_posting_date_when_there_is_one(self):
        posted = TODAY + timedelta(days=9)
        assert _candidate(days_ago=0, bank_posted_date=posted).comparable_date == posted
        assert _candidate(days_ago=2).comparable_date == TODAY - timedelta(days=2)


class TestMatchDecision:
    """Pure decision-ladder tests. Candidates already share the exact amount
    within the ±10 day search window (SQL guarantees that); the ladder only
    chooses between auto / review / create. Auto-matching is confined to
    ±5 days — candidates beyond that only ever reach review."""

    def test_no_candidates_creates(self) -> None:
        d = decide_match("STARBUCKS", TODAY, True, [])
        assert d.action == "create"
        assert d.candidate_id is None

    def test_renamed_payee_same_day_auto_matches(self) -> None:
        """The user renamed the payee in another app, and the bank descriptor
        shares no words with it — exact amount + same day must still
        auto-match instead of silently duplicating."""
        cand = _candidate(days_ago=0, payee="Bread Financial")
        d = decide_match("COMENITY PAY VI WEB PYMT", TODAY, True, [cand])
        assert d.action == "auto"
        assert d.candidate_id == cand.id

    def test_bank_descriptor_that_contradicts_the_feed_goes_to_review(self) -> None:
        """The structural shortcut takes a lone same-amount row a day away
        regardless of payee — which is right for a row a person typed
        ("Rent" never resembles "CHECK 1234") and wrong when the row carries
        the bank's own words: "HOME DEPOT" and "TRADER JOE'S" the same day
        are two purchases, and merging them loses one."""
        cand = _candidate(days_ago=0, payee="Home Depot", bank_payee="HOME DEPOT #4411")
        d = decide_match("TRADER JOE'S #552", TODAY, True, [cand])
        assert d.action == "review"
        assert d.candidate_id == cand.id

    def test_a_file_descriptor_on_the_row_counts_as_bank_words(self) -> None:
        """A row a CSV wrote keeps the file's descriptor in
        import_description — the bank's words, the same as a feed's."""
        cand = _candidate(days_ago=0, payee="Home Depot", import_description="HOME DEPOT #4411")
        d = decide_match("TRADER JOE'S #552", TODAY, True, [cand])
        assert d.action == "review"

    def test_bank_descriptor_that_agrees_still_auto_matches(self) -> None:
        cand = _candidate(days_ago=1, payee="Trader Joe's", bank_payee="TRADER JOE'S #552")
        d = decide_match("TRADER JOES 552", TODAY, True, [cand])
        assert d.action == "auto"

    def test_check_descriptor_one_day_off_auto_matches(self) -> None:
        cand = _candidate(days_ago=1, payee="Lawn Service")
        d = decide_match("CHECK # 1234", TODAY, True, [cand])
        assert d.action == "auto"
        assert d.candidate_id == cand.id

    def test_dissimilar_payee_two_days_off_goes_to_review(self) -> None:
        """Outside the tight window, payee dissimilarity means real doubt —
        create the row but queue it for human review, never silently."""
        cand = _candidate(days_ago=2, payee="Bread Financial")
        d = decide_match("COMENITY PAY VI WEB PYMT", TODAY, True, [cand])
        assert d.action == "review"
        assert d.candidate_id == cand.id
        assert d.score > 0.0

    def test_similar_payee_two_days_off_still_auto_matches(self) -> None:
        """Strong payee similarity auto-matches at any distance inside the
        auto radius."""
        cand = _candidate(days_ago=2, payee="Whole Foods Market")
        d = decide_match("WHOLE FOODS MARKET #123", TODAY, True, [cand])
        assert d.action == "auto"
        assert d.candidate_id == cand.id
        assert d.score >= DEDUP_AUTO_MATCH_THRESHOLD

    def test_two_same_day_lookalikes_go_to_review(self) -> None:
        """Two identical-amount same-day candidates with equally weak payee
        similarity: guessing would corrupt one of them — review instead."""
        a = _candidate(days_ago=0, payee="Lunch")
        b = _candidate(days_ago=0, payee="Lunch")
        d = decide_match("SQ *FOOD TRUCK", TODAY, True, [a, b])
        assert d.action == "review"

    def test_same_day_pair_with_clear_payee_winner_auto_matches(self) -> None:
        with patch(
            "igab.domain.matching.best_payee_similarity",
            side_effect=lambda names, other, **_: {"close": 0.62, "far": 0.30}[names[0]],
        ):
            close = _candidate(days_ago=0, payee="close")
            far = _candidate(days_ago=0, payee="far")
            d = decide_match("BANK DESCRIPTOR", TODAY, True, [close, far])
        assert d.action == "auto"
        assert d.candidate_id == close.id

    def test_same_day_pair_below_margin_goes_to_review(self) -> None:
        with patch(
            "igab.domain.matching.best_payee_similarity",
            side_effect=lambda names, other, **_: {"close": 0.45, "far": 0.40}[names[0]],
        ):
            close = _candidate(days_ago=0, payee="close")
            far = _candidate(days_ago=0, payee="far")
            d = decide_match("BANK DESCRIPTOR", TODAY, True, [close, far])
        assert d.action == "review"

    def test_far_candidates_do_not_block_structural_match(self) -> None:
        """A second candidate 3 days out does not make the same-day one
        ambiguous — date proximity disambiguates recurring amounts."""
        near = _candidate(days_ago=0, payee="Bread Financial")
        far = _candidate(days_ago=3, payee="Card Payment")
        d = decide_match("COMENITY PAY VI WEB PYMT", TODAY, True, [near, far])
        assert d.action == "auto"
        assert d.candidate_id == near.id

    def test_missing_payees_tight_window_auto_matches(self) -> None:
        """Neutral 0.5 similarity on both sides: structure still decides."""
        cand = _candidate(days_ago=1, payee=None)
        d = decide_match("", TODAY, True, [cand])
        assert d.action == "auto"

    def test_pending_feed_row_never_structurally_matches(self) -> None:
        """Pending amounts are provisional (tips, gas holds) — a same-day
        dissimilar candidate goes to review, not auto."""
        cand = _candidate(days_ago=0, payee="Bread Financial")
        d = decide_match("COMENITY PAY VI WEB PYMT", TODAY, False, [cand])
        assert d.action == "review"

    def test_pending_feed_row_still_payee_matches(self) -> None:
        cand = _candidate(days_ago=0, payee="Whole Foods Market")
        d = decide_match("WHOLE FOODS MARKET #123", TODAY, False, [cand])
        assert d.action == "auto"

    def test_window_edge_dissimilar_goes_to_review(self) -> None:
        cand = _candidate(days_ago=5, payee="Bread Financial")
        d = decide_match("COMENITY PAY VI WEB PYMT", TODAY, True, [cand])
        assert d.action == "review"
        assert d.candidate_id == cand.id

    def test_settlement_lag_candidate_reviews_instead_of_silent_create(self) -> None:
        """A card payment the user dated the 15th posted the 22nd — 7 days
        out, beyond the old ±5 search window, so it silently duplicated. The
        widened window must surface it for review."""
        cand = _candidate(days_ago=7, payee="Sapphire")
        d = decide_match("SAPPHIRE CARD ONLINE PAYMENT", TODAY, True, [cand])
        assert d.action == "review"
        assert d.candidate_id == cand.id

    def test_identical_payee_beyond_auto_radius_never_auto_matches(self) -> None:
        """An identical payee a week out is as likely a weekly recurring
        charge as a settlement-lagged duplicate — review, never auto."""
        cand = _candidate(days_ago=7, payee="Spotify")
        d = decide_match("SPOTIFY", TODAY, True, [cand])
        assert d.action == "review"
        assert d.candidate_id == cand.id

    def test_strong_far_candidate_blocks_structural_shortcut(self) -> None:
        """A perfect-payee candidate 7 days out plus a weak same-day one is
        genuinely ambiguous — review, not a silent structural pick."""
        far_strong = _candidate(days_ago=7, payee="Spotify")
        near_weak = _candidate(days_ago=0, payee="Lunch Money")
        d = decide_match("SPOTIFY", TODAY, True, [far_strong, near_weak])
        assert d.action == "review"

    def test_weak_far_candidates_do_not_block_structural_match(self) -> None:
        """Weak candidates in the widened 6–10 day band leave the same-day
        singleton auto-match intact."""
        near = _candidate(days_ago=0, payee="Bread Financial")
        far = _candidate(days_ago=8, payee="Card Payment")
        d = decide_match("COMENITY PAY VI WEB PYMT", TODAY, True, [near, far])
        assert d.action == "auto"
        assert d.candidate_id == near.id

    def test_decision_days_are_measured_on_the_comparable_date(self) -> None:
        """A row the bank posted on the 25th that the user dated the 16th is
        the same day as its own re-issued posting, not nine days off."""
        cand = _candidate(days_ago=9, payee="Harborstone Mortgage", bank_posted_date=TODAY)
        d = decide_match("HARBORSTONE MTG PMT", TODAY, True, [cand])
        assert d.days == 0
        assert d.action == "auto"


class TestStrictPass:
    def test_only_a_same_day_auto_match_settles_first(self) -> None:
        cid = uuid.uuid4()
        assert settles_in_strict_pass(MatchDecision("auto", cid, 0.9, 0))
        assert not settles_in_strict_pass(MatchDecision("auto", cid, 0.9, 1))
        assert not settles_in_strict_pass(MatchDecision("review", cid, 0.6, 0))
        assert not settles_in_strict_pass(MatchDecision("create"))


class TestBankFileOverCleanedPayees:
    """What a bank CSV meets when the account's history came from another
    app: cleaned payees on one side, raw descriptors on the other, posted the
    same day or a few days later. Every one of these is a row already here."""

    def test_cleaned_name_against_a_raw_descriptor_three_days_later(self) -> None:
        cand = _candidate(days_ago=3, payee="Trader Joe's")
        d = decide_match("TRADER JOE'S #552 SEATTLE WA", TODAY, True, [cand])
        assert d.action == "auto"

    def test_payroll_descriptor_two_days_later(self) -> None:
        cand = _candidate(days_ago=2, payee="Northwind Payserv")
        d = decide_match("NORTHWIND PAYSERV DIR DEP", TODAY, True, [cand])
        assert d.action == "auto"

    def test_case_alone_never_separates_two_spellings(self) -> None:
        cand = _candidate(days_ago=3, payee="trader joe's")
        d = decide_match("TRADER JOE'S", TODAY, True, [cand])
        assert d.action == "auto"
        assert d.score >= DEDUP_AUTO_MATCH_THRESHOLD
