"""Credit cards leave Ready to Assign — the arithmetic, pure.

The model (decided 2026-08-28, replacing the net-cash rule; releases made
cumulative 2026-08-29 after "The Unreleased Reservation"):

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

The one invariant that keeps the accumulated series honest against the
directly-computed truth (pinned by tests/unit/test_cards.py and the
integration identity walk): for a card with no assignments and no inflows
that predate their reservations,

    set_aside + uncovered == -balance    at every month.

Reservations release *cumulatively*: a refund lands whenever it lands, and
it releases the reservation its purchase made even when that was months ago
and in a different calendar month (`card_funding`'s running walk). Only an
inflow exceeding everything its category ever reserved on that card is
capped — it reduced the card's debt without touching reserved cash, so it
pays down Uncovered instead. Flooring per month, as the first release rule
did, silently discarded every cross-month release and ratcheted the
set-aside upward forever.

**What is capped on the card side must be taken off the envelope side**
(`truncated_by_category`, added 2026-08-29 after "The Internet Envelope").
An inflow raises its category's available through the ordinary activity sum
before any of this arithmetic runs. Capping the release without also
reducing that available leaves the same dollars counted twice — once as
card debt paid down, once as spendable envelope money — and because
`TBA = cash − envelopes − …` the whole difference comes out of Ready to
Assign, silently and with no red anywhere. On a real budget that was
$10,852 on a card owing $6,925.97: three synced card payments that arrived
as ordinary rows instead of transfer legs, auto-filed to an Internet
envelope that had never reserved a cent on that card.

Everything here takes plain dicts and returns plain dicts: no database, no
account rows, so every branch is a one-line test. The repository layer
supplies SIGNED net credit outflows per (category, month, card) — a month
that nets to an inflow arrives negative, never clamped.
"""

from datetime import date
from decimal import Decimal

ZERO = Decimal("0")


def credit_floored_by_month(
    end_balances: dict[date, Decimal],
    credit_outflows: dict[date, Decimal],
) -> dict[date, Decimal]:
    """The credit-funded part of each month's shortfall, for one category.

    A month that ended at −50 with 70 spent on cards has 50 riding as card
    debt and 0 written off from Ready to Assign; the same month with 20 on
    cards has 20 riding and 30 written off. Months that ended non-negative
    contribute nothing. `credit_outflows` is signed net card spending: a
    month that nets to an inflow carries no shortfall onto a card, so it is
    treated as zero here. Only months with an entry in `end_balances` exist
    — a category's data months — and the result carries only non-zero
    values.
    """
    out: dict[date, Decimal] = {}
    for month, end in end_balances.items():
        if end >= ZERO:
            continue
        floored = min(-end, max(ZERO, credit_outflows.get(month, ZERO)))
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


def cap_releases(
    deltas: dict[date, Decimal],
) -> tuple[dict[date, Decimal], dict[date, Decimal]]:
    """One (category, card) series of reservation deltas, releases capped.

    Walks the months in order carrying the running reservation: positive
    deltas (funded credit spending) accumulate, negative deltas (card
    inflows) release against what has accumulated and are truncated to it —
    the running total is floored at zero, never each month independently.
    The truncated remainder is an inflow with no reservation behind it
    (a refund of pre-history or overspent-and-ridden spending); it already
    reduced the card's balance, so it pays down Uncovered rather than
    withdrawing reserved cash that was never reserved.

    Returns `(capped, truncated)`. The second dict is the part of each
    release this function refused, as a positive amount, and it exists
    because discarding it silently cost a real budget $10,852 of Ready to
    Assign: the inflow had *already* raised its category's available through
    the ordinary activity sum, so refusing the release here left the same
    dollars counted twice — once as card debt paid down, once as spendable
    envelope money — with Ready to Assign absorbing the difference. Whoever
    caps the card side has to hand back what it capped so the envelope side
    can be balanced (`card_funding` → `truncated_by_category`).
    """
    out: dict[date, Decimal] = {}
    truncated: dict[date, Decimal] = {}
    reserved = ZERO
    for month in sorted(deltas):
        delta = deltas[month]
        if delta < ZERO:
            capped = -min(-delta, reserved)
            if capped != delta:
                truncated[month] = capped - delta
            delta = capped
        reserved += delta
        if delta != ZERO:
            out[month] = delta
    return out, truncated


def card_funding[C, K](
    end_balances_by_category: dict[C, dict[date, Decimal]],
    credit_outflows: dict[C, dict[K, dict[date, Decimal]]],
) -> tuple[
    dict[K, dict[date, Decimal]],
    dict[C, dict[date, Decimal]],
    dict[C, dict[date, Decimal]],
]:
    """The whole budget's card funding, composed from the primitives.

    Takes each category's raw month-end series (`monthly_end_balances`) and
    `credit_outflows[category][card][month]` (SIGNED net: a month whose card
    activity nets to an inflow is negative). Returns:

    - net reservation flows per card per month — the synthetic activity of
      each card's set-aside: positive where funded spending reserved money,
      negative where an inflow released a reservation made in any earlier
      (or the same) month. Releases are capped per (category, card) by
      `cap_releases`, so no category can withdraw more from a card's reserve
      than it ever put in.
    - floored per category per month — what rode onto cards instead of being
      written off; the viewed month's entries are what Ready to Assign
      subtracts directly (`uncovered_current`).
    - truncated per category per month — the releases `cap_releases` refused,
      as positive amounts. The card kept its reserve, so the category must
      not keep the money too: the caller subtracts this from the category's
      activity. Without it, every card inflow into a category that never
      reserved on that card drains Ready to Assign dollar-for-dollar.
    """
    funded_by_card: dict[K, dict[date, Decimal]] = {}
    floored_by_category: dict[C, dict[date, Decimal]] = {}
    truncated_by_category: dict[C, dict[date, Decimal]] = {}
    for category, by_card in credit_outflows.items():
        end_balances = end_balances_by_category.get(category, {})
        totals: dict[date, Decimal] = {}
        for outflows in by_card.values():
            for month, amount in outflows.items():
                totals[month] = totals.get(month, ZERO) + amount
        floored = credit_floored_by_month(end_balances, totals)
        if floored:
            floored_by_category[category] = floored
        deltas_by_card: dict[K, dict[date, Decimal]] = {}
        for month in totals:
            month_floored = floored.get(month, ZERO)
            # Floored first, funded is the remainder — allocated per card so
            # each card's envelope receives only what was spent on it. Only
            # cards that netted to spending that month can carry the ride.
            floored_share = allocate_across_cards(
                month_floored,
                {c: o[month] for c, o in by_card.items() if o.get(month, ZERO) > ZERO},
            )
            for card, outflows in by_card.items():
                net = outflows.get(month, ZERO)
                delta = net - floored_share.get(card, ZERO) if net > ZERO else net
                if delta != ZERO:
                    deltas_by_card.setdefault(card, {})[month] = delta
        for card, deltas in deltas_by_card.items():
            capped, truncated = cap_releases(deltas)
            for month, delta in capped.items():
                per_card = funded_by_card.setdefault(card, {})
                per_card[month] = per_card.get(month, ZERO) + delta
            for month, refused in truncated.items():
                per_cat = truncated_by_category.setdefault(category, {})
                per_cat[month] = per_cat.get(month, ZERO) + refused
    return funded_by_card, floored_by_category, truncated_by_category


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
    return sum((v for m, v in assignments_by_month.items() if m <= month_start), ZERO) + sum(
        (v for m, v in synthetic_by_month.items() if m <= month_start), ZERO
    )
