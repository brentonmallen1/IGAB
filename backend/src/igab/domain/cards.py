"""Credit cards leave Ready to Assign — the arithmetic, pure.

The model (decided 2026-08-28, replacing the net-cash rule; releases made
cumulative 2026-08-29 after "The Unreleased Reservation"; refusals removed
2026-08-29 after "The Refused Repayment"):

- A card's balance is not in the budget's cash. The only way a card moves
  Ready to Assign is money deliberately set aside for it.
- The set-aside is a running total, not a floored envelope: funded credit
  spending flows in, card inflows release what was reserved, payments flow
  out, and real assignments on the card's linked category add to it. A month
  where payments exceed the reserve is an overpayment — a credit balance on
  the card, carried forward — not an overspend for Ready to Assign to
  absorb, so no zero floor is applied between months (`set_aside_through`).
- The part a category could NOT cover — `min(shortfall, credit outflow)` at
  month end — never reaches the set-aside and never charges Ready to Assign.
  It rides on the card as *uncovered debt*: visible beside the card's
  balance, calm, and paid down by assigning to the card. Cash overspending
  keeps today's behavior (absorbed from Ready to Assign at the boundary).
- In the viewed month the shortfall has not been written off yet — the
  category still shows red, and that negative would otherwise *raise* the
  figure through the envelope term — so its credit-funded part is subtracted
  from Ready to Assign directly (`uncovered_current` in the YNAB oracle,
  which states the same rules over an export; the two must not drift).

**Every cent of every card inflow lands somewhere. Nothing is refused.**
A category's exposure on a card has two layers, and `release_split` sends an
inflow through them in order:

1. `discharged` — met **uncovered debt**. The card's balance fell and no cash
   was released, because none was ever behind it. Goods taken without paying:
   returning them cancels the debt, it does not hand you spending money. So
   this amount is subtracted from the category's activity *for that month*,
   inside the walk, before the month-end balance is taken.
2. `released` — gave back **reserved cash**. Goods the envelope did pay for:
   returning them must hand the envelope its money back. `set_aside` falls,
   the envelope keeps the inflow, no adjustment.
3. `residual` — beyond everything this category ever had riding here. Also
   reduces `set_aside`, **uncapped**, so a reserve may go negative. That is a
   real position, not an error: the card is holding budget money (a credit
   balance, or a prepayment a later purchase absorbs).

Uncovered first is what puts both sides of one debt in the same ledger. The
previous rule reserved only the *funded* part and then measured the repayment
against that reserve, so a repayment of ridden debt was refused, the envelope
was charged twice for one shortfall, and the refusal — a cumulative sum
subtracted from a floored carryover — could only ratchet upward. On a real
budget it reached a five-figure red on one envelope charging a card that owed
almost nothing ("The Refused Repayment").

The correction is **never summed**. `repaid_by_category[c][m]` is an
adjustment to month `m`'s activity, bounded above by the same month's card
inflow, so it can never make a month more negative than that month with no
refund at all, and `next_carryover` floors it at the boundary exactly as it
floors anything else. That is why `card_funding` runs the carryover walk
itself instead of reading a precomputed series: the adjustment has to be
inside the simulation, not applied after it.

The walk is acyclic, one forward pass. Within a month, `discharged` reads only
that month's inflows and exposure carried in from earlier months; it never
reads its own month's floored share. A (category, card, month) is either a
charge or a release — the repository sums it to one signed net — and a charge
on one card cannot be released by an inflow on another, because exposure is
per (category, card).

**Exposure stays per (category, card), deliberately.** Pooling it would let a
refund on one card reduce another card's `set_aside` while that card's balance
did not move, breaking the reserve identity for a card nothing happened to.
The cost is that a repayment onto card A for spending done on card B lands as
a residual (a negative reserve on A) rather than releasing B — correct for the
card ledgers, and named rather than silent (`reserve_discrepancy`'s T2 bound).

The identity that keeps the accumulated series honest against the
directly-computed truth, with **no exclusions** — assignments, inflows that
predate their reservations, and overpayments all included:

    set_aside + uncovered == -balance + over_reserved - short_reserved
                             + card_credit

That equation is an identity given the definitions in `reserve_discrepancy`;
the content is in its three bounds, which is where the old form's excused
cases went. The old form said "for a card with no assignments and no inflows
that predate their reservations" — and those were precisely the cases that
broke, so nothing ever asked.

Everything here takes plain dicts and returns plain dicts: no database, no
account rows, so every branch is a one-line test. The repository layer
supplies SIGNED net credit outflows per (category, month, card) — a month
that nets to an inflow arrives negative, never clamped.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from igab.domain.carryover import next_carryover, sum_through

ZERO = Decimal("0")


def credit_floored(end_of_month: Decimal, net_card_outflow: Decimal) -> Decimal:
    """The credit-funded part of one month's shortfall, for one category.

    A month that ended at -50 with 70 spent on cards has 50 riding as card
    debt and 0 written off from Ready to Assign; the same month with 20 on
    cards has 20 riding and 30 written off. A month that ended non-negative
    contributes nothing, and a month whose card activity nets to an inflow
    carries no shortfall onto a card.
    """
    if end_of_month >= ZERO:
        return ZERO
    return min(-end_of_month, max(ZERO, net_card_outflow))


def credit_floored_by_month(
    end_balances: dict[date, Decimal],
    credit_outflows: dict[date, Decimal],
) -> dict[date, Decimal]:
    """`credit_floored` over a whole series, keeping only non-zero months.

    Only months with an entry in `end_balances` exist — a category's data
    months. `card_funding` calls `credit_floored` directly, one month at a
    time, because its walk needs the *adjusted* end balance it has just
    computed rather than a precomputed series.
    """
    out: dict[date, Decimal] = {}
    for month, end in end_balances.items():
        floored = credit_floored(end, credit_outflows.get(month, ZERO))
        if floored > ZERO:
            out[month] = floored
    return out


def allocate_across_cards[K](
    amount: Decimal,
    per_card: dict[K, Decimal],
) -> dict[K, Decimal]:
    """Split `amount` across cards, each capped at its own outflow.

    A category-month spent on two cards has one floored amount and two
    possible homes for it. Greedy in sorted-key order: deterministic, exact
    (no proportional rounding), and irrelevant in the overwhelmingly common
    one-card case. Keys sort as strings so UUIDs and test stubs both work.
    """
    out: dict[K, Decimal] = {}
    remaining = amount
    for card in sorted(per_card, key=str):
        take = min(remaining, per_card[card])
        if take > ZERO:
            out[card] = take
            remaining -= take
    return out


def release_split(
    release: Decimal,
    floored_exposure: Decimal,
    funded_reserve: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """One card inflow, split three ways: `(discharged, released, residual)`.

    `release` is positive (the inflow), `floored_exposure` is what this
    category has riding on this card uncovered (>= 0), `funded_reserve` is
    what it has reserved there (signed — a negative reserve releases nothing
    more). The three parts always sum to `release`: nothing is refused.

    Uncovered debt is discharged first. See the module docstring for why —
    it is the only order that does not simultaneously tell the user they have
    money to spend and that they owe something nobody is covering.
    """
    discharged = min(release, floored_exposure)
    released = min(release - discharged, max(ZERO, funded_reserve))
    return discharged, released, release - discharged - released


@dataclass(frozen=True)
class CardFunding[C, K]:
    """What one pass over a budget's card history produces.

    A dataclass rather than a tuple because the tuple grew a fourth slot that
    every caller unpacked as `_`, and a slot nobody names is a slot nobody
    tests — which is exactly how the old `truncated` shipped with no coverage
    at all.
    """

    #: Net reservation flows per card per month — the synthetic activity of
    #: each card's set-aside envelope. Positive where funded spending reserved
    #: money, negative where an inflow released a reservation (or overshot one,
    #: as a residual).
    funded_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: What rode onto cards per category per month instead of being written
    #: off. The viewed month's entries are what Ready to Assign subtracts
    #: directly (`uncovered_current`).
    floored_by_category: dict[C, dict[date, Decimal]] = field(default_factory=dict)
    #: The same ridden amounts attributed to the card each was swiped on.
    #: Exact, not apportioned: `allocate_across_cards` decides it, its pool is
    #: the cards with positive net that month, and that pool sums to at least
    #: the month's net — so the per-card figures sum to the per-category ones.
    floored_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: `discharged` per category per month: the part of that month's card
    #: inflows that repaid uncovered debt rather than returning money to the
    #: envelope. **Already folded into `end_balances`.** Never summed across
    #: months by anyone — carried per month so a row can say why its activity
    #: differs from the register's.
    repaid_by_category: dict[C, dict[date, Decimal]] = field(default_factory=dict)
    #: `residual` per card per month: inflow beyond everything the category
    #: ever had riding on that card. Already inside `funded_by_card`; carried
    #: separately because it is the T2 bound of the reserve identity.
    residual_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: The month-end series each card-touching category's `available` must be
    #: read out of (`carryover.available_at`) — the ordinary simulation with
    #: `repaid_by_category` folded into each month's activity. Categories with
    #: no card activity are absent: their series is unchanged, and recomputing
    #: it here would give the snapshot path a second opinion to disagree with.
    end_balances: dict[C, dict[date, Decimal]] = field(default_factory=dict)


def card_funding[C, K](
    assignments_by_category: dict[C, dict[date, Decimal]],
    activity_by_category: dict[C, dict[date, Decimal]],
    credit_outflows: dict[C, dict[K, dict[date, Decimal]]],
) -> CardFunding[C, K]:
    """The whole budget's card funding, in one forward pass per category.

    Takes each category's raw assignment and activity series and
    `credit_outflows[category][card][month]` (SIGNED net: a month whose card
    activity nets to an inflow is negative). Runs the carryover simulation
    itself, because the correction an inflow makes to a month's activity has
    to be inside the walk — applied after it, as a cumulative sum against a
    floored balance, it ratchets upward forever.

    Within each month, in this order: inflows split through `release_split`;
    the month's adjusted end balance; its floored share; then the charges.
    Acyclic — see the module docstring.
    """
    out: CardFunding[C, K] = CardFunding()
    for category, by_card in credit_outflows.items():
        assignments = assignments_by_category.get(category, {})
        activity = activity_by_category.get(category, {})
        months = sorted(set(assignments) | set(activity) | {m for s in by_card.values() for m in s})
        # Running exposure for this category, per card: what it has riding
        # there uncovered, and what it has reserved there.
        ridden: dict[K, Decimal] = {}
        reserved: dict[K, Decimal] = {}
        carryover = ZERO
        for month in months:
            nets = {c: s[month] for c, s in by_card.items() if month in s}

            # 1. Inflows, split three ways. Reads only exposure carried in
            #    from earlier months, never this month's floored share.
            repaid = ZERO
            for card, net in nets.items():
                if net >= ZERO:
                    continue
                discharged, released, residual = release_split(
                    -net, ridden.get(card, ZERO), reserved.get(card, ZERO)
                )
                ridden[card] = ridden.get(card, ZERO) - discharged
                reserved[card] = reserved.get(card, ZERO) - released - residual
                repaid += discharged
                if released + residual != ZERO:
                    per_card = out.funded_by_card.setdefault(card, {})
                    per_card[month] = per_card.get(month, ZERO) - released - residual
                if residual != ZERO:
                    per_card = out.residual_by_card.setdefault(card, {})
                    per_card[month] = per_card.get(month, ZERO) + residual
            if repaid != ZERO:
                out.repaid_by_category.setdefault(category, {})[month] = repaid

            # 2. The month's end balance, with the correction folded in — the
            #    same simulation `carryover.monthly_end_balances` runs, sharing
            #    its floor so the two cannot drift.
            end = carryover + assignments.get(month, ZERO) + activity.get(month, ZERO) - repaid
            out.end_balances.setdefault(category, {})[month] = end
            carryover = next_carryover(end)

            # 3. What the shortfall put on a card, from the ADJUSTED balance.
            floored = credit_floored(end, sum(nets.values(), ZERO))
            if floored > ZERO:
                out.floored_by_category.setdefault(category, {})[month] = floored

            # 4. The charges. Floored first, funded is the remainder —
            #    allocated per card so each card's envelope receives only what
            #    was spent on it. Only cards that netted to spending that month
            #    can carry the ride.
            floored_share = allocate_across_cards(
                floored, {c: n for c, n in nets.items() if n > ZERO}
            )
            for card, share in floored_share.items():
                per_card = out.floored_by_card.setdefault(card, {})
                per_card[month] = per_card.get(month, ZERO) + share
                ridden[card] = ridden.get(card, ZERO) + share
            for card, net in nets.items():
                if net <= ZERO:
                    continue
                delta = net - floored_share.get(card, ZERO)
                reserved[card] = reserved.get(card, ZERO) + delta
                if delta != ZERO:
                    per_card = out.funded_by_card.setdefault(card, {})
                    per_card[month] = per_card.get(month, ZERO) + delta
    return out


def synthetic_activity(
    funded: dict[date, Decimal],
    payments: dict[date, Decimal],
) -> dict[date, Decimal]:
    """One card's set-aside activity: reservation flows in, payments out."""
    out = dict(funded)
    for month, paid in payments.items():
        out[month] = out.get(month, ZERO) - paid
    return out


def set_aside_through(
    assignments_by_month: dict[date, Decimal],
    synthetic_by_month: dict[date, Decimal],
    month_start: date,
) -> Decimal:
    """A card's reserve at `month_start`: a plain running total.

    Deliberately NOT `carryover.available_through`: the zero floor between
    months is the write-off rule for spending envelopes, where a negative
    month is overspending absorbed from Ready to Assign. A set-aside's
    negative month is an overpayment — a real credit balance on the card —
    and flooring it discarded the surplus and ratcheted the reserve upward
    by every overpaid month. The negative carries; if a surface prefers not
    to show one, it floors at the presentation layer only.
    """
    return sum_through(assignments_by_month, month_start) + sum_through(
        synthetic_by_month, month_start
    )


def reserve_discrepancy(
    set_aside: Decimal,
    balance: Decimal,
    assigned: Decimal,
    payments: Decimal,
    residual_releases: Decimal,
    unbudgeted_credits: Decimal,
) -> Decimal:
    """0 when a card's reserve identity holds with all three bounds met;
    otherwise the largest amount by which one of them does not.

    With `owed = -balance` and every term below floored at zero:

        uncovered      = max(0, owed - max(0, set_aside))
        over_reserved  = max(0, set_aside - max(0, owed))
        short_reserved = max(0, -set_aside)
        card_credit    = max(0, -owed)

        set_aside + uncovered == owed + over_reserved - short_reserved
                                 + card_credit

    The equation is an algebraic identity given those definitions, so it
    catches nothing on its own. **The content is the three bounds**, and each
    one replaces a clause the old invariant used to excuse:

    - **T1** `over_reserved <= assigned + unbudgeted_credits`. A reserve
      exceeds its debt only by money someone deliberately assigned to the
      card, or by a credit somebody outside the budget put on it. Replaces
      "for a card with no assignments".
    - **T2** `short_reserved <= payments + residual_releases`. A reserve goes
      negative only by paying the card more than was reserved, or by an inflow
      beyond what its category ever had riding there. Replaces "and no inflows
      that predate their reservations".
    - **T3** `card_credit <= short_reserved + unbudgeted_credits`. A credit
      balance on a card is either budget money or somebody else's. This is the
      one that catches a repayment landing where no category ever charged.

    `assigned` is assignments to the card's own linked category, `payments`
    are transfers from the budget's cash, `residual_releases` is
    `CardFunding.residual_by_card` summed for this card through the month, and
    `unbudgeted_credits` is `txn_filters.UNBUDGETED_CARD_CREDIT` — a card
    inflow the budget has no claim on at all.
    """
    owed = -balance
    over_reserved = max(ZERO, set_aside - max(ZERO, owed))
    short_reserved = max(ZERO, -set_aside)
    card_credit = max(ZERO, -owed)
    worst = max(
        over_reserved - (assigned + unbudgeted_credits),
        short_reserved - (payments + residual_releases),
        card_credit - (short_reserved + unbudgeted_credits),
    )
    return worst if worst > ZERO else ZERO
