"""A card's reserve month by month, and where it first went wrong.

`CardReserve.set_aside` answers "what is the reserve NOW"; every question a
negative reserve raises is about *when*. A ten-year import that lands at
-1,000 did not drift there smoothly — it is usually a handful of months, and
naming them is the difference between "your card is negative" and "fund
March 2019, or assign the reimbursements envelope's windfall to the card".

Composes what already exists — the five legs of `CardReserve`, and
`card_position` — into a per-month series. **No new money rules**: the
cumulative reserve here is definitionally `CardReserve.set_aside` evaluated
at each month, pinned by a test rather than trusted, and the position is the
same `card_position` every other surface reads.

Pure, like the rest of `domain/`: plain dicts in, dataclasses out, every
branch a one-line test. The offline probe (`scripts/card_reserve_probe.py`)
carries a deliberate copy of this analysis for deployments whose code we do
not control; `tests/integration/test_card_probe_agreement.py` keeps the two
in step.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from igab.domain.cards import CardPosition, CardReserve, card_position

ZERO = Decimal("0")

#: The five legs in reserve order, with the sign each contributes to the
#: set-aside. One spelling — `first_breach` ranks by these, `CardMonth`
#: recombines them, and a second list would let the two disagree about what
#: a reserve is made of.
LEG_SIGNS: tuple[tuple[str, int], ...] = (
    ("assignments", 1),
    ("reservations", 1),
    ("released", -1),
    ("residual", -1),
    ("payments", -1),
)


@dataclass(frozen=True)
class CardMonth:
    """One month of a card's reserve: the five legs' deltas, and where the
    running totals stood once the month had happened."""

    month: date
    #: This month's movement in each leg, keyed as `LEG_SIGNS` names them.
    legs: dict[str, Decimal]
    #: `CardReserve.set_aside(month)` — cumulative, unfloored.
    set_aside: Decimal
    #: The card's ledger through this month. Negative is owed.
    balance: Decimal
    #: What was riding uncovered after this month.
    riding: Decimal
    #: `card_position(set_aside, balance)` at this month.
    position: CardPosition

    @property
    def reserve_delta(self) -> Decimal:
        """What this month did to the reserve, signed."""
        return sum((Decimal(sign) * self.legs[leg] for leg, sign in LEG_SIGNS), ZERO)


@dataclass(frozen=True)
class Breach:
    """The first month the reserve crossed below zero."""

    month: date
    set_aside_before: Decimal
    set_aside_after: Decimal
    #: (leg, signed contribution to the reserve that month), most negative
    #: first, zero legs omitted — the first entry is what did it.
    ranked_legs: tuple[tuple[str, Decimal], ...]


def card_timeline(
    reserve: CardReserve,
    balance_by_month: dict[date, Decimal],
    riding_by_month: dict[date, Decimal],
) -> list[CardMonth]:
    """The reserve's whole history, one entry per month anything moved.

    Months come from the union of the five legs, the balance, and the ride —
    a month where only the balance moved (an unfiled charge) still appears,
    because that is exactly the month a diagnosis needs to see.
    """
    leg_series: dict[str, dict[date, Decimal]] = {
        "assignments": reserve.assignments,
        "reservations": reserve.reservations,
        "released": reserve.released,
        "residual": reserve.residual,
        "payments": reserve.payments,
    }
    months = sorted(
        {m for series in leg_series.values() for m in series}
        | set(balance_by_month)
        | set(riding_by_month)
    )
    out: list[CardMonth] = []
    set_aside = balance = riding = ZERO
    for month in months:
        legs = {leg: leg_series[leg].get(month, ZERO) for leg, _ in LEG_SIGNS}
        set_aside += sum((Decimal(sign) * legs[leg] for leg, sign in LEG_SIGNS), ZERO)
        balance += balance_by_month.get(month, ZERO)
        riding += riding_by_month.get(month, ZERO)
        out.append(
            CardMonth(
                month=month,
                legs=legs,
                set_aside=set_aside,
                balance=balance,
                riding=riding,
                position=card_position(set_aside, balance),
            )
        )
    return out


def first_breach(timeline: list[CardMonth]) -> Breach | None:
    """The first month the cumulative reserve crossed from >= 0 to < 0,
    with that month's legs ranked so the answer says which leg did it.

    The *first* crossing, deliberately: a reserve that dips, recovers, and
    dips again has its story start at the first dip, and the later ones are
    visible in `worst_months`. A reserve negative in its very first month is
    a breach in that month — the running total is zero before any month
    exists, so there is always a `>= 0` to cross from. `None` only when the
    reserve never went below zero at any month boundary.
    """
    prev = ZERO
    for cm in timeline:
        if cm.set_aside < ZERO and prev >= ZERO:
            contributions = sorted(
                ((leg, Decimal(sign) * cm.legs[leg]) for leg, sign in LEG_SIGNS),
                key=lambda pair: pair[1],
            )
            return Breach(
                month=cm.month,
                set_aside_before=prev,
                set_aside_after=cm.set_aside,
                ranked_legs=tuple((leg, amt) for leg, amt in contributions if amt != ZERO),
            )
        prev = cm.set_aside
    return None


def worst_months(timeline: list[CardMonth], limit: int = 6) -> list[CardMonth]:
    """The months that moved the reserve furthest down, worst first.

    A ten-year drift is usually a handful of months, not a slope; these are
    the ones worth reading the register for. Only strictly negative months
    qualify — an empty result means no month ever lowered the reserve.
    """
    negative = [cm for cm in timeline if cm.reserve_delta < ZERO]
    negative.sort(key=lambda cm: cm.reserve_delta)
    return negative[:limit]
