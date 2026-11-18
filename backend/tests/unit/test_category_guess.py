"""The per-payee auto-fill rule — domain/category_guess.py.

The acceptance cases from a tester's eight-year measurement, plus the
warehouse-club tie that made the old "most recent row" rule file every
grocery run under Membership. Payees and amounts are invented; the ratios
are what teach.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.category_guess import (
    HISTORY_LIMIT,
    NEAREST_WINDOW,
    HistoryRow,
    guess_category,
    scoreboard,
)

GROCERIES = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
MEMBERSHIP = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
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


# ─── New payee ───────────────────────────────────────────────────────────────


def test_new_payee_guesses_nothing():
    result = guess_category([], D("-20.00"))
    assert result.category_id is None
    assert result.rule is None
    assert result.record == (0, 0)


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
    result = guess_category(warehouse_club_history(), D("-172.00"))
    assert result.category_id == GROCERIES
    assert result.rule == "nearest"


def test_warehouse_club_membership_sized_row_lands_in_membership():
    result = guess_category(warehouse_club_history(), D("-60.00"))
    assert result.category_id == MEMBERSHIP


def test_warehouse_club_with_last_years_membership_too():
    """A year of history with the previous membership in it: exact now hits
    the membership row, but misses every grocery run, so nearest still leads
    and a grocery-sized row is still Groceries."""
    history = [*warehouse_club_history(), HistoryRow(date(2025, 9, 8), D("-60.00"), MEMBERSHIP)]
    assert guess_category(history, D("-140.00")).category_id == GROCERIES
    assert guess_category(history, D("-60.00")).category_id == MEMBERSHIP


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
    assert guess_category(history, D("-15.99")).category_id == X
    assert guess_category(history, D("-42.50")).category_id == Y


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
    small_result = guess_category(history, D("-39.60"))
    large_result = guess_category(history, D("-86.00"))
    assert small_result.category_id == X
    assert large_result.category_id == Y
    assert small_result.rule == "nearest"


# ─── Mixed payee: abstain ────────────────────────────────────────────────────


def test_mixed_payee_leaves_the_category_blank():
    """An everything-store: four envelopes in no pattern of amount or order.
    No rule is right 60% of the time, so the row is left for the person."""
    cats = [X, Y, Z, W]
    amounts = ["-12.00", "-55.00", "-23.00", "-80.00", "-17.00", "-34.00", "-61.00", "-9.00"]
    spec = [(amounts[i], cats[(i * 3 + i // 2) % 4]) for i in range(len(amounts))]
    history = rows_oldest_first(*spec)
    result = guess_category(history, D("-30.00"))
    assert result.category_id is None
    hits, scored = result.record
    assert scored == len(amounts) - 1
    assert hits * 5 < scored * 3


def test_abstain_threshold_boundary_three_of_five_fills():
    """Exactly 60% of five scored rows is enough to fill."""
    # Oldest first. nearest replays: hit, hit, miss, hit, miss → 3/5;
    # last trails at 1/5 and exact never sees a repeated amount.
    history = rows_oldest_first(
        ("-10", X), ("-11", X), ("-50", Y), ("-12", X), ("-51", Z), ("-13", X)
    )
    hits, scored = scoreboard(history)
    assert scored == 5
    assert max(hits.values()) == 3
    assert guess_category(history, D("-93")).category_id is not None


def test_abstain_threshold_boundary_two_of_four_blank():
    """Two of four scored rows (50%) is not enough."""
    history = rows_oldest_first(("-10", X), ("-90", Y), ("-11", Z), ("-91", W), ("-12", X))
    hits, scored = scoreboard(history)
    assert scored == 4
    assert max(hits.values()) < 3
    assert guess_category(history, D("-50")).category_id is None


# ─── Short history: exact, else last ─────────────────────────────────────────


def test_short_history_exact_match_wins():
    history = rows_oldest_first(("-9.99", X), ("-30.00", Y))
    result = guess_category(history, D("-9.99"))
    assert result.category_id == X
    assert result.rule == "exact"


def test_short_history_no_match_falls_back_to_last():
    history = rows_oldest_first(("-9.99", X), ("-30.00", Y))
    result = guess_category(history, D("-12.00"))
    assert result.category_id == Y
    assert result.rule == "last"


def test_single_row_is_inherited():
    """One row of history, unscoreable: today's behaviour, not a blank."""
    history = rows_oldest_first(("-4.50", X))
    assert guess_category(history, D("-7.25")).category_id == X


def test_four_rows_is_still_short_history():
    """Four rows replay only three — below the scoreboard minimum."""
    history = rows_oldest_first(("-10", X), ("-90", Y), ("-11", Z), ("-91", W))
    _, scored = scoreboard(history)
    assert scored == 3
    assert guess_category(history, D("-50")).category_id == W


# ─── Rule details ────────────────────────────────────────────────────────────


def test_exact_matches_the_signed_amount():
    """A refund of +25 is not the purchase of -25."""
    history = rows_oldest_first(("-25.00", X), ("25.00", Y), ("-40.00", Z))
    assert guess_category(history, D("-25.00")).category_id == X
    assert guess_category(history, D("25.00")).category_id == Y


def test_steady_payee_last_still_wins_when_amounts_wander():
    """One envelope, varying amounts: every rule but exact is perfect, the
    tie goes to nearest, and the answer is the envelope."""
    history = rows_oldest_first(*((f"-{30 + i * 7}.00", X) for i in range(10)))
    result = guess_category(history, D("-1000.00"))
    assert result.category_id == X
    assert result.record == (9, 9)


def test_exact_leader_with_unseen_amount_falls_to_nearest():
    """A payee whose amounts repeat, offered an amount it never charged:
    exact cannot answer, so the next rule in tie order does."""
    history = rows_oldest_first(*((("-10.00", X), ("-50.00", Y))[i % 2] for i in range(8)))
    result = guess_category(history, D("-48.00"))
    assert result.rule == "exact"
    assert result.category_id == Y


def test_nearest_looks_only_at_the_last_twelve():
    """An old price beyond the window is not matched: the payee's
    category changed and its amounts drifted with it."""
    old = [("-500.00", X)] + [("-20.00", X)] * 3
    recent = [(f"-{100 + i}.00", Y) for i in range(NEAREST_WINDOW)]
    history = rows_oldest_first(*old, *recent)
    assert guess_category(history, D("-500.00")).category_id == Y


def test_history_beyond_the_limit_is_ignored():
    long = [("-10.00", X)] * 30 + [("-10.00", Y)] * HISTORY_LIMIT
    history = rows_oldest_first(*long)
    result = guess_category(history, D("-10.00"))
    assert result.category_id == Y
    assert result.record[1] == HISTORY_LIMIT - 1
