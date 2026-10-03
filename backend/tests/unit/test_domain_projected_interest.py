"""The plan matrix for a loan's projected interest row.

One month, one answer: Create, Update, Retire or nothing. Every condition
the plan turns on gets a row here — the wiring that gathers the facts is
tested against a real ledger in tests/integration/test_projected_interest.py.

Figures are fictional and round: 6% on 24,000.00 owed is 120.00 a month.
"""

import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from igab.domain.interest import interest_for_month
from igab.domain.projected_interest import (
    Create,
    MonthFacts,
    Retire,
    StandingProjection,
    Update,
    adopts_projection,
    may_create_for,
    plan_projection,
    projected_amount,
)

MARCH = date(2026, 3, 1)
PAID = date(2026, 3, 15)
SIX = Decimal("6")
OWED = Decimal("24000.00")
ROW_ID = uuid.UUID(int=7)

FACTS = MonthFacts(
    month=MARCH,
    owed_at_open=OWED,
    first_payment=PAID,
    lender_interest=Decimal("0"),
    standing=None,
    declined=False,
)


def _standing(amount: str = "-120.00", on: date = PAID) -> StandingProjection:
    return StandingProjection(id=ROW_ID, date=on, amount=Decimal(amount))


# ─── The amount ─────────────────────────────────────────────────────────────


def test_the_amount_is_last_months_close_at_the_rate_as_an_outflow():
    assert projected_amount(FACTS, SIX) == Decimal("-120.00")


def test_the_amount_is_interest_for_month_and_nothing_else():
    """One implementation: the row and the liability page's estimate are the
    same function of the same opening, so they can never disagree."""
    odd = replace(FACTS, owed_at_open=Decimal("18333.33"))
    assert projected_amount(odd, Decimal("6.875")) == -interest_for_month(
        Decimal("18333.33"), Decimal("6.875")
    )


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"first_payment": None}, "no payment arrived this month"),
        ({"lender_interest": Decimal("-120.00")}, "the lender's own row is here"),
        ({"lender_interest": Decimal("-0.01")}, "any lender row at all, not just an equal one"),
        ({"owed_at_open": Decimal("0")}, "nothing was owed as the month opened"),
        ({"owed_at_open": Decimal("-50.00")}, "the loan opened the month in credit"),
        ({"declined": True}, "the person deleted this month's projection"),
    ],
)
def test_no_row_is_wanted(change, why):
    assert projected_amount(replace(FACTS, **change), SIX) is None, why


def test_no_row_without_a_rate():
    assert projected_amount(FACTS, None) is None


def test_no_row_in_a_promo_month():
    """`chargeable_rate` passes zero for a month a 0% promo covers; zero
    interest is no row, not a row of 0.00."""
    assert projected_amount(FACTS, Decimal("0")) is None


def test_a_sub_cent_month_is_no_row():
    """A balance so small its month rounds to nothing writes nothing."""
    assert projected_amount(replace(FACTS, owed_at_open=Decimal("0.50")), SIX) is None


def test_rounding_is_to_the_cent():
    """6% on 24,001.00 is 120.005, which rounds half-even to 120.00."""
    assert projected_amount(replace(FACTS, owed_at_open=Decimal("24001.00")), SIX) == Decimal(
        "-120.00"
    )


# ─── The plan ───────────────────────────────────────────────────────────────


def test_a_wanted_month_with_no_row_creates_one_dated_on_the_first_payment():
    assert plan_projection(FACTS, SIX, may_create=True) == Create(
        month=MARCH, date=PAID, amount=Decimal("-120.00")
    )


def test_a_wanted_month_outside_the_window_creates_nothing():
    assert plan_projection(FACTS, SIX, may_create=False) is None


def test_a_standing_row_that_is_right_is_left_alone():
    facts = replace(FACTS, standing=_standing())
    assert plan_projection(facts, SIX, may_create=True) is None


def test_a_standing_row_resized_when_the_opening_moved():
    """Last month's balance changed — a back-dated row, or last month's own
    projection — so this month's interest is different."""
    facts = replace(FACTS, owed_at_open=Decimal("23000.00"), standing=_standing())
    assert plan_projection(facts, SIX, may_create=True) == Update(
        id=ROW_ID, date=PAID, amount=Decimal("-115.00")
    )


def test_a_standing_row_follows_a_re_dated_payment():
    facts = replace(FACTS, standing=_standing(on=date(2026, 3, 2)))
    assert plan_projection(facts, SIX, may_create=True) == Update(
        id=ROW_ID, date=PAID, amount=Decimal("-120.00")
    )


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"first_payment": None}, "the payment was deleted or moved out"),
        ({"lender_interest": Decimal("-120.00")}, "the lender's row replaced it"),
        ({"owed_at_open": Decimal("0")}, "the loan was paid off last month"),
        ({"declined": True}, "a tombstone beside a live row: the decline wins"),
    ],
)
def test_a_standing_row_no_longer_wanted_is_retired(change, why):
    facts = replace(FACTS, standing=_standing(), **change)
    assert plan_projection(facts, SIX, may_create=True) == Retire(ROW_ID), why


def test_a_standing_row_is_retired_when_the_terms_go():
    facts = replace(FACTS, standing=_standing())
    assert plan_projection(facts, None, may_create=True) == Retire(ROW_ID)


def test_a_standing_row_is_retired_when_a_promo_covers_the_month():
    facts = replace(FACTS, standing=_standing())
    assert plan_projection(facts, Decimal("0"), may_create=True) == Retire(ROW_ID)


@pytest.mark.parametrize("may_create", [True, False])
def test_update_and_retire_ignore_the_creation_window(may_create):
    """Correcting the app's own row is never limited by age — only writing
    a NEW one is."""
    resized = replace(FACTS, owed_at_open=Decimal("12000.00"), standing=_standing())
    assert plan_projection(resized, SIX, may_create=may_create) == Update(
        id=ROW_ID, date=PAID, amount=Decimal("-60.00")
    )
    gone = replace(FACTS, first_payment=None, standing=_standing())
    assert plan_projection(gone, SIX, may_create=may_create) == Retire(ROW_ID)


def test_nothing_wanted_and_nothing_standing_is_nothing():
    assert plan_projection(replace(FACTS, first_payment=None), SIX, may_create=True) is None


def test_create_is_keyed_to_the_months_first_day():
    facts = replace(FACTS, month=date(2026, 3, 20))
    plan = plan_projection(facts, SIX, may_create=True)
    assert isinstance(plan, Create) and plan.month == MARCH


# ─── The creation window ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("month", "today", "allowed"),
    [
        (date(2026, 3, 1), date(2026, 3, 18), True),  # this month
        (date(2026, 2, 1), date(2026, 3, 18), True),  # last month
        (date(2026, 2, 27), date(2026, 3, 1), True),  # any day of last month
        (date(2026, 1, 1), date(2026, 3, 18), False),  # two months back
        (date(2026, 4, 1), date(2026, 3, 18), False),  # next month
        (date(2025, 12, 1), date(2026, 1, 5), True),  # across a year end
        (date(2025, 11, 1), date(2026, 1, 5), False),
    ],
)
def test_a_new_row_only_for_this_month_and_last(month, today, allowed):
    assert may_create_for(month, today) is allowed


# ─── Adoption ───────────────────────────────────────────────────────────────

ROW = {
    "amount": Decimal("-120.0000"),
    "date": PAID,
    "cleared": "uncleared",
    "account_id": uuid.UUID(int=1),
}


@pytest.mark.parametrize(
    "change",
    [
        {"amount": Decimal("-118.40")},
        {"date": date(2026, 3, 16)},
        {"cleared": "cleared"},
        {"account_id": uuid.UUID(int=2)},
    ],
)
def test_editing_money_or_bank_state_adopts_the_row(change):
    assert adopts_projection(ROW, change)


@pytest.mark.parametrize(
    "change",
    [
        {"memo": "March statement"},
        {"payee_id": uuid.UUID(int=3)},
        {},
        # The editor sends every field it shows: an unchanged value riding
        # along with a memo edit is not an edit of that value.
        {**ROW, "memo": "March statement"},
        {"amount": Decimal("-120.00")},  # same money, different scale
    ],
)
def test_bookkeeping_and_unchanged_fields_adopt_nothing(change):
    assert not adopts_projection(ROW, change)
