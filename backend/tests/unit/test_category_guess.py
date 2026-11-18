"""The per-payee auto-fill rule — domain/category_guess.py.

The acceptance cases from a tester's eight-year measurement, plus the
warehouse-club tie that made the old "most recent row" rule file every
grocery run under Membership. Payees and amounts are invented; the ratios
are what teach.

Which rule answered is shown by construction: each history is built so only
one rule gives the asserted envelope, and `scoreboard` pins who leads.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.category_guess import (
    HISTORY_LIMIT,
    MIN_SCORED,
    NEAREST_WINDOW,
    HistoryRow,
    guess_category,
    leader_is_trusted,
    scoreboard,
)

GROCERIES = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
MEMBERSHIP = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
HOUSEHOLD = uuid.UUID("00000000-0000-0000-0000-0000000000a3")
GIFTS = uuid.UUID("00000000-0000-0000-0000-0000000000a4")
MISC = uuid.UUID("00000000-0000-0000-0000-0000000000a5")
X = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
Y = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
Z = uuid.UUID("00000000-0000-0000-0000-0000000000b3")
W = uuid.UUID("00000000-0000-0000-0000-0000000000b4")


def D(s: str) -> Decimal:
    return Decimal(s)


def rows_oldest_first(*spec: tuple[str, uuid.UUID], start=date(2026, 1, 1)) -> list[HistoryRow]:
    """Build history from oldest-first (amount, category) pairs, one per day,
    and return it newest first — the repository's order."""
    out = [
        HistoryRow(start + timedelta(days=i), D(amount), cat)
        for i, (amount, cat) in enumerate(spec)
    ]
    return list(reversed(out))


def old_rule(history: list[HistoryRow]) -> uuid.UUID | None:
    """What auto-fill did before: the most recent row."""
    return history[0].category_id if history else None


def trusted(history: list[HistoryRow]) -> bool:
    hits, scored = scoreboard(history)
    assert scored >= MIN_SCORED, "not a scoreboard case"
    return leader_is_trusted(hits, scored)


# ─── New payee ───────────────────────────────────────────────────────────────


def test_new_payee_guesses_nothing():
    assert guess_category([], D("-20.00")) is None


# ─── Warehouse club ──────────────────────────────────────────────────────────


def warehouse_club_history() -> list[HistoryRow]:
    """Northwind Warehouse Club: grocery runs of a few hundred, and the
    annual membership at a third of one. On the latest date the membership
    and a grocery run share a date, and the membership was entered second —
    so `date DESC, created_at DESC` puts it first."""
    shared = date(2026, 9, 8)
    return [
        HistoryRow(shared, D("-60.00"), MEMBERSHIP),  # created later on the same day
        HistoryRow(shared, D("-180.00"), GROCERIES),
        HistoryRow(date(2026, 8, 22), D("-150.00"), GROCERIES),
        HistoryRow(date(2026, 8, 5), D("-210.00"), GROCERIES),
        HistoryRow(date(2026, 7, 19), D("-120.00"), GROCERIES),
        HistoryRow(date(2026, 7, 2), D("-165.00"), GROCERIES),
        HistoryRow(date(2026, 6, 14), D("-195.00"), GROCERIES),
    ]


def test_warehouse_club_tie_old_rule_files_groceries_under_membership():
    """The bug, pinned: the old rule hands a grocery run the membership."""
    assert old_rule(warehouse_club_history()) == MEMBERSHIP


def test_warehouse_club_grocery_sized_row_lands_in_groceries():
    """nearest ties last on the scoreboard and wins the tie; last alone
    would have said Membership."""
    hits, _ = scoreboard(warehouse_club_history())
    assert hits["nearest"] >= hits["last"] > hits["exact"]
    assert guess_category(warehouse_club_history(), D("-172.00")) == GROCERIES


def test_warehouse_club_membership_sized_row_lands_in_membership():
    assert guess_category(warehouse_club_history(), D("-60.00")) == MEMBERSHIP


def test_warehouse_club_with_last_years_membership_too():
    """A year of history with the previous membership in it: exact now hits
    the membership row, but misses every grocery run, so nearest still leads
    and a grocery-sized row is still Groceries."""
    history = [*warehouse_club_history(), HistoryRow(date(2025, 9, 8), D("-60.00"), MEMBERSHIP)]
    assert guess_category(history, D("-140.00")) == GROCERIES
    assert guess_category(history, D("-60.00")) == MEMBERSHIP


# ─── Alternating fixed amounts ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "pattern",
    [
        "ABABABABAB",
        "AABBABBAAB",
        "BBBAAABABA",
        "ABBBBBBBBA",
    ],
)
def test_alternating_fixed_amounts_follow_the_amount(pattern):
    """A→X, B→Y in any order: the amount says which, recency does not."""
    amounts = {"A": ("-15.99", X), "B": ("-42.50", Y)}
    history = rows_oldest_first(*(amounts[c] for c in pattern))
    assert guess_category(history, D("-15.99")) == X
    assert guess_category(history, D("-42.50")) == Y


# ─── Same-day pair, no repeated amount ───────────────────────────────────────


def test_same_day_pair_half_apart_follows_size():
    """Two charges each visit, the small one about half the large one, no
    amount ever repeating. Small → X, large → Y, whichever was entered last."""
    pairs = [("-40.10", "-82.30"), ("-38.75", "-79.40"), ("-43.20", "-88.60"), ("-41.05", "-84.90")]
    history: list[HistoryRow] = []
    for i, (small, large) in enumerate(pairs):
        day = date(2026, 3, 1) + timedelta(days=14 * i)
        # Alternate which of the pair was entered second.
        first, second = ((small, X), (large, Y)) if i % 2 == 0 else ((large, Y), (small, X))
        history.insert(0, HistoryRow(day, D(first[0]), first[1]))
        history.insert(0, HistoryRow(day, D(second[0]), second[1]))
    hits, _ = scoreboard(history)
    assert hits["nearest"] > hits["last"]
    assert guess_category(history, D("-39.60")) == X
    assert guess_category(history, D("-86.00")) == Y


# ─── Mixed payee ─────────────────────────────────────────────────────────────


def test_mixed_payee_with_no_dominant_envelope_is_left_blank():
    """An everything-store: four envelopes in no pattern of amount or order.
    No rule is right 60% of the time, the amount never appeared and no
    envelope holds half, so the row is left for the person."""
    cats = [X, Y, Z, W]
    amounts = ["-12.00", "-55.00", "-23.00", "-80.00", "-17.00", "-34.00", "-61.00", "-9.00"]
    spec = [(amounts[i], cats[(i * 3 + i // 2) % 4]) for i in range(len(amounts))]
    history = rows_oldest_first(*spec)
    assert not trusted(history)
    assert guess_category(history, D("-30.00")) is None


def test_trust_boundary_three_of_five_fills():
    """Exactly 60% of five scored rows is trusted."""
    # Oldest first. nearest replays: hit, hit, miss, hit, miss → 3/5;
    # last trails at 1/5 and exact never sees a repeated amount.
    history = rows_oldest_first(
        ("-10", X), ("-11", X), ("-50", Y), ("-12", X), ("-51", Z), ("-13", X)
    )
    hits, scored = scoreboard(history)
    assert (max(hits.values()), scored) == (3, 5)
    assert trusted(history)
    assert guess_category(history, D("-14")) == X


def test_trust_boundary_two_of_four_is_not_trusted():
    """Two of four scored rows (50%) is not enough."""
    history = rows_oldest_first(("-10", X), ("-90", Y), ("-11", Z), ("-91", W), ("-12", X))
    hits, scored = scoreboard(history)
    assert scored == 4
    assert max(hits.values()) < 3
    assert not trusted(history)
    assert guess_category(history, D("-50")) is None


# ─── Short history: exact, else last ─────────────────────────────────────────


def test_short_history_exact_match_wins():
    history = rows_oldest_first(("-9.99", X), ("-30.00", Y))
    assert guess_category(history, D("-9.99")) == X


def test_short_history_no_match_falls_back_to_last():
    history = rows_oldest_first(("-9.99", X), ("-30.00", Y))
    assert guess_category(history, D("-12.00")) == Y


def test_single_row_is_inherited():
    """One row of history, unscoreable: today's behaviour, not a blank."""
    history = rows_oldest_first(("-4.50", X))
    assert guess_category(history, D("-7.25")) == X


def test_four_rows_is_still_short_history():
    """Four rows replay only three — below the scoreboard minimum."""
    history = rows_oldest_first(("-10", X), ("-90", Y), ("-11", Z), ("-91", W))
    _, scored = scoreboard(history)
    assert scored == MIN_SCORED - 1
    assert guess_category(history, D("-50")) == W


# ─── Rule details ────────────────────────────────────────────────────────────


def test_exact_matches_the_signed_amount():
    """A refund of +25 is not the purchase of -25."""
    history = rows_oldest_first(("-25.00", X), ("25.00", Y), ("-40.00", Z))
    assert guess_category(history, D("-25.00")) == X
    assert guess_category(history, D("25.00")) == Y


def test_steady_payee_is_filed_whatever_the_amount():
    """One envelope, varying amounts: nearest and last are perfect."""
    history = rows_oldest_first(*((f"-{30 + i * 7}.00", X) for i in range(10)))
    hits, scored = scoreboard(history)
    assert (hits["nearest"], hits["last"], scored) == (9, 9, 9)
    assert guess_category(history, D("-1000.00")) == X


def test_exact_leader_with_unseen_amount_falls_to_nearest():
    """A payee whose amounts repeat, offered an amount it never charged:
    exact leads but cannot answer, so the next rule in tie order does."""
    history = rows_oldest_first(*((("-10.00", X), ("-50.00", Y))[i % 2] for i in range(8)))
    hits, _ = scoreboard(history)
    assert hits["exact"] >= max(hits.values())
    assert guess_category(history, D("-48.00")) == Y


def test_nearest_looks_only_at_the_last_twelve():
    """An old price beyond the window is not matched: the payee's
    category changed and its amounts drifted with it."""
    old = [("-500.00", X)] + [("-20.00", X)] * 3
    recent = [(f"-{100 + i}.00", Y) for i in range(NEAREST_WINDOW)]
    history = rows_oldest_first(*old, *recent)
    assert guess_category(history, D("-500.00")) == Y


def test_history_beyond_the_limit_is_ignored():
    """Thirty older X rows past the limit cannot outvote the 24 newest."""
    long = [("-10.00", X)] * 30 + [("-10.00", Y)] * HISTORY_LIMIT
    assert guess_category(rows_oldest_first(*long), D("-10.00")) == Y


# ─── Zero amounts ────────────────────────────────────────────────────────────


def test_zero_history_row_is_matched_by_a_zero_row():
    """A $0 row (a voided authorisation, a free trial) is an amount like any
    other: a new $0 row matches it exactly, and `0.00` equals `0`."""
    history = rows_oldest_first(("-30.00", X), ("0.00", Z), ("-31.00", X), ("-29.00", X))
    assert guess_category(history, D("0")) == Z
    assert guess_category(history, D("-30.50")) == X


def test_zero_new_row_with_no_zero_in_history():
    """With no $0 in history a $0 row takes the payee's best rule: here
    nearest, which lands on the smallest charge."""
    history = rows_oldest_first(
        ("-80.00", Y), ("-5.00", X), ("-82.00", Y), ("-6.00", X), ("-81.00", Y), ("-4.00", X)
    )
    assert trusted(history)
    assert guess_category(history, D("0.00")) == X


# ─── Not trusted: a repeated amount, then a dominant envelope ────────────────


def messy_warehouse_club() -> list[HistoryRow]:
    """A real warehouse club's shape: mostly groceries, the rest filed under
    several envelopes at overlapping sizes, one membership row. Groceries
    holds 12 of 24 and no rule's record is trusted."""
    return rows_oldest_first(
        ("-140.00", GROCERIES),
        ("-38.00", HOUSEHOLD),
        ("-155.00", GROCERIES),
        ("-150.00", GIFTS),
        ("-42.00", GROCERIES),
        ("-160.00", MISC),
        ("-60.00", MEMBERSHIP),
        ("-48.00", GROCERIES),
        ("-145.00", HOUSEHOLD),
        ("-52.00", GROCERIES),
        ("-170.00", GIFTS),
        ("-135.00", GROCERIES),
        ("-44.00", MISC),
        ("-165.00", GROCERIES),
        ("-58.00", HOUSEHOLD),
        ("-130.00", GROCERIES),
        ("-47.00", GIFTS),
        ("-175.00", GROCERIES),
        ("-55.00", MISC),
        ("-128.00", GROCERIES),
        ("-162.00", HOUSEHOLD),
        ("-50.00", GROCERIES),
        ("-148.00", GIFTS),
        ("-41.00", GROCERIES),
    )


def test_messy_warehouse_club_is_not_trusted_by_any_rule():
    assert not trusted(messy_warehouse_club())


def test_messy_warehouse_club_grocery_sized_row_gets_the_dominant_envelope():
    """-152 sits nearest a Gifts row (-148), so nearest would say Gifts;
    Groceries here is the dominant envelope answering."""
    assert guess_category(messy_warehouse_club(), D("-152.00")) == GROCERIES


def test_messy_warehouse_club_membership_sized_row_gets_membership_by_amount():
    """The renewal repeats last year's amount exactly: that beats the
    dominant envelope."""
    assert guess_category(messy_warehouse_club(), D("-60.00")) == MEMBERSHIP


def test_exact_fallback_matches_the_signed_amount_only():
    """A refund the size of the membership is not the membership."""
    assert guess_category(messy_warehouse_club(), D("60.00")) == GROCERIES


def test_dominant_at_exactly_half_fills():
    """Five of ten rows in X, no amount repeated, no rule trusted."""
    history = rows_oldest_first(
        ("-10", X), ("-90", Y), ("-20", X), ("-80", Z), ("-30", X),
        ("-70", W), ("-40", X), ("-60", Y), ("-50", X), ("-15", Z),
    )  # fmt: skip
    assert not trusted(history)
    assert guess_category(history, D("-1")) == X


def test_dominant_just_under_half_stays_blank():
    """The same history with one X row moved to W: four of ten."""
    history = rows_oldest_first(
        ("-10", X), ("-90", Y), ("-20", X), ("-80", Z), ("-30", X),
        ("-70", W), ("-40", X), ("-60", Y), ("-50", W), ("-15", Z),
    )  # fmt: skip
    assert not trusted(history)
    assert guess_category(history, D("-1")) is None


def test_two_envelopes_at_half_each_go_to_the_more_recent():
    history = rows_oldest_first(
        ("-10", X), ("-90", Y), ("-20", Y), ("-80", X), ("-30", X), ("-70", Y)
    )
    assert not trusted(history)
    assert guess_category(history, D("-1")) == Y
