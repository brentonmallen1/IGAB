"""Credit cards leave Ready to Assign — the arithmetic, pure.

The model (decided 2026-08-28, replacing the net-cash rule):

- A card's balance is not in the budget's cash. The only way a card moves
  Ready to Assign is money deliberately set aside for it.
- The set-aside is itself an envelope, simulated by `domain/carryover.py`
  like any other, over *synthetic* activity: spending on the card that the
  spending category could cover flows in ("funded credit"); payments to the
  card flow out; real assignments on the card's linked category add to it.
- The part a category could NOT cover — `min(shortfall, credit outflow)` at
  month end — never reaches the set-aside and never charges Ready to Assign.
  It rides on the card as *uncovered debt*: visible beside the card's
  balance, calm, and paid down by assigning to the card. Cash overspending
  keeps today's behavior (absorbed from Ready to Assign at the boundary).
- In the viewed month the shortfall has not been written off yet — the
  category still shows red — so its credit-funded part is subtracted from
  Ready to Assign directly (`uncovered_current` in the YNAB oracle, which
  states the same rules over an export; the two must not drift).

Everything here takes plain dicts and returns plain dicts: no database, no
account rows, so every branch is a one-line test. The repository layer
supplies net credit outflows per (category, month, card) — *net*, refunds
subtracted, floored at zero per month, so a refunded purchase releases its
reservation the way YNAB's payment envelope does.
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
    contribute nothing. Only months with an entry in `end_balances` exist —
    a category's data months — and the result carries only non-zero values.
    """
    out: dict[date, Decimal] = {}
    for month, end in end_balances.items():
        if end >= ZERO:
            continue
        floored = min(-end, credit_outflows.get(month, ZERO))
        if floored > ZERO:
            out[month] = floored
    return out


def funded_credit_by_month(
    end_balances: dict[date, Decimal],
    credit_outflows: dict[date, Decimal],
) -> dict[date, Decimal]:
    """What each month's card spending was *covered* by the envelope — the
    part that flows into the card's set-aside. outflow − floored, per month."""
    floored = credit_floored_by_month(end_balances, credit_outflows)
    out: dict[date, Decimal] = {}
    for month, outflow in credit_outflows.items():
        funded = outflow - floored.get(month, ZERO)
        if funded > ZERO:
            out[month] = funded
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


def card_funding[C, K](
    end_balances_by_category: dict[C, dict[date, Decimal]],
    credit_outflows: dict[C, dict[K, dict[date, Decimal]]],
) -> tuple[dict[K, dict[date, Decimal]], dict[C, dict[date, Decimal]]]:
    """The whole budget's card funding, composed from the primitives.

    Takes each category's raw month-end series (`monthly_end_balances`) and
    `credit_outflows[category][card][month]` (net, ≥ 0). Returns:

    - funded inflows per card per month — the synthetic positive activity of
      each card's set-aside envelope, and
    - floored per category per month — what rode onto cards instead of being
      written off; the viewed month's entries are what Ready to Assign
      subtracts directly (`uncovered_current`).
    """
    funded_by_card: dict[K, dict[date, Decimal]] = {}
    floored_by_category: dict[C, dict[date, Decimal]] = {}
    for category, by_card in credit_outflows.items():
        end_balances = end_balances_by_category.get(category, {})
        totals: dict[date, Decimal] = {}
        for outflows in by_card.values():
            for month, amount in outflows.items():
                totals[month] = totals.get(month, ZERO) + amount
        floored = credit_floored_by_month(end_balances, totals)
        if floored:
            floored_by_category[category] = floored
        for month in totals:
            month_floored = floored.get(month, ZERO)
            # Floored first, funded is the remainder — allocated per card so
            # each card's envelope receives only what was spent on it.
            floored_share = allocate_across_cards(
                month_floored, {c: o.get(month, ZERO) for c, o in by_card.items()}
            )
            for card, outflows in by_card.items():
                funded = outflows.get(month, ZERO) - floored_share.get(card, ZERO)
                if funded > ZERO:
                    per_card_funded = funded_by_card.setdefault(card, {})
                    per_card_funded[month] = per_card_funded.get(month, ZERO) + funded
    return funded_by_card, floored_by_category
