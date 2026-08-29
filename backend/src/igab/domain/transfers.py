"""What makes two rows one transfer, and where a category may sit on it.

Two rules live here. The second is stated first because it decides whether
the first is even asked.

## Which two rows are one movement (`pair_legs`)

A bank feed has no idea that your checking outflow and your card inflow are
one payment. It reports each account separately, so both legs arrive with
ordinary bank payees and nothing links them. Every consequence of that is a
money bug:

- **card payment** — the card's set-aside is drained only by a *transfer* leg
  (`sum_card_payments_by_month`), so an unpaired payment reserves nothing and
  the money has to go somewhere. On a real budget it went into an Internet
  envelope and took $4,180 of Ready to Assign with it.
- **on-budget savings** — the checking leg drains an envelope while the
  savings leg arrives with nothing to absorb it, so `cash − envelopes`
  *invents* the amount. Measured: a $1,000 transfer raised Ready to Assign by
  $1,000.
- **off-budget loan or brokerage** — no TBA term moves, but reports read the
  two legs as real income and real spending.

So this is not a credit-card rule wearing a general name; cards are one
instance of it.

## Where a category may sit (`leg_may_carry_category` and friends)

The rule, stated once:

    A category may sit only on an ON-BUDGET row — and on a transfer leg,
    only when the partner is OFF-budget.

The first clause is the general rule: a category files budget spending, and a
tracking account's rows are net-worth movement, not budget spending. A
categorized row on an off-budget account moved envelopes (and, via the
carryover floor, Ready to Assign) while its account contributed to no balance
term — money moving with no on-budget event.

The second clause is the transfer case: a category on a transfer means a YNAB
"spending transfer", real spending or income crossing the budget boundary. An
on↔on transfer is internal movement and can never be categorized (it would
count moving money as spending); an off-budget leg can never be categorized;
both legs categorized is always wrong.

This rule was found hand-written three times — transfer create, the
transfer-edit planner, and the YNAB importer's pairing check — each phrased
for its own call shape, and the fourth path that needed it (`repair_transfers`)
had none, so the auto-repair happily created exactly the categorized
on↔on link the manual paths refuse. One implementation, per CLAUDE.md.

Pure throughout: booleans and plain records in, verdicts out. Messages stay at
the call sites, where they can speak in that path's terms; the *decisions* are
only here.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PairableLeg:
    """One row that could still be joined to a partner, reduced to what the
    pairing decision actually reads. Deliberately not a `Transaction`: the rule
    below has to be testable without a database."""

    id: uuid.UUID
    account_id: uuid.UUID
    on_budget: bool
    date: date
    amount: Decimal
    categorized: bool
    #: Whether this row's category (if any) was applied by the sync run now
    #: pairing it, rather than chosen by a person. Auto-categorization is a
    #: guess; clearing a guess to link a transfer is a correction, clearing a
    #: person's choice is data loss. Only the former may happen unattended.
    category_is_a_guess: bool = False


@dataclass(frozen=True)
class LegPair:
    """Two rows that look like the two sides of one movement."""

    outflow_id: uuid.UUID
    inflow_id: uuid.UUID
    #: Ids whose category linking would have to clear. Empty for the common
    #: case; non-empty is not by itself a refusal — see `confident`.
    clears_categories: tuple[uuid.UUID, ...] = ()


def pair_legs(
    legs: Sequence[PairableLeg], *, window_days: int
) -> tuple[list[LegPair], list[LegPair]]:
    """Split pairable rows into `(confident, needs_review)`.

    A candidate pair is an outflow and an inflow of exactly opposite amount, on
    two *different* accounts, dated within `window_days` of each other. Exact
    amounts only: a transfer is one movement of one sum, and a near-miss is a
    different question (`domain/matching.py` scores those).

    Confident requires **mutual uniqueness** — this outflow's only candidate is
    that inflow, and that inflow's only candidate is this outflow. The same
    rule `repair_transfers` uses, and for the same reason: three $500 movements
    in one week have nine possible pairings and no basis to prefer any, so
    guessing would link the wrong two and look authoritative doing it.

    A pair whose linking would break the category rule is confident only when
    every category it must clear is a sync's own guess. A person's category is
    never cleared unattended — that pair goes to review with the clearing named
    so they can see the price of linking.
    """
    by_id = {leg.id: leg for leg in legs}
    candidates: dict[uuid.UUID, set[uuid.UUID]] = {leg.id: set() for leg in legs}
    outflows = [leg for leg in legs if leg.amount < 0]
    inflows = [leg for leg in legs if leg.amount > 0]
    for out in outflows:
        for inn in inflows:
            if out.account_id == inn.account_id:
                continue
            if inn.amount != -out.amount:
                continue
            if abs((inn.date - out.date).days) > window_days:
                continue
            candidates[out.id].add(inn.id)
            candidates[inn.id].add(out.id)

    confident: list[LegPair] = []
    review: list[LegPair] = []
    seen: set[uuid.UUID] = set()
    for out in sorted(outflows, key=lambda leg: (leg.date, str(leg.id))):
        if out.id in seen:
            continue
        mine = candidates[out.id]
        mutual = [i for i in mine if candidates[i] == {out.id}]
        pair_is_unambiguous = len(mine) == 1 and len(mutual) == 1
        for inflow_id in sorted(mine, key=str):
            inn = by_id[inflow_id]
            clears = tuple(
                leg.id
                for leg in (out, inn)
                if leg.categorized
                and not leg_may_carry_category(leg.on_budget, _other(out, inn, leg).on_budget)
            )
            pair = LegPair(outflow_id=out.id, inflow_id=inflow_id, clears_categories=clears)
            only_guesses = all(by_id[cid].category_is_a_guess for cid in clears)
            if pair_is_unambiguous and only_guesses:
                confident.append(pair)
                seen.update({out.id, inflow_id})
            else:
                review.append(pair)
            if pair_is_unambiguous:
                break
    return confident, review


def transfer_link_fields(
    own_payee_id: uuid.UUID,
    partner_payee_id: uuid.UUID,
    *,
    own_id: uuid.UUID,
    partner_id: uuid.UUID,
) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID]]:
    """What each of two existing rows must hold to be one transfer pair.

    Returns `(own_fields, partner_fields)`. Each leg points its `transfer_id`
    at the other and carries a payee naming the OTHER account — that is what a
    transfer payee means and what the register renders.

    Stated here because two paths write it: the editor's `link` action, where a
    human picked the partner, and `TransactionService.link_legs`, where a sync
    found it. A pair linked unattended must be indistinguishable from one
    linked by hand, and the only way to guarantee that is for both to read the
    field set from the same place.
    """
    return (
        {"payee_id": own_payee_id, "transfer_id": partner_id},
        {"payee_id": partner_payee_id, "transfer_id": own_id},
    )


def _other(a: PairableLeg, b: PairableLeg, this: PairableLeg) -> PairableLeg:
    return b if this.id == a.id else a


def leg_may_carry_category(own_on_budget: bool, partner_on_budget: bool | None = None) -> bool:
    """May THIS row hold a category? A plain transaction is a leg with no
    partner — the general clause alone decides it."""
    if partner_on_budget is None:
        return own_on_budget
    return own_on_budget and not partner_on_budget


def pair_may_carry_category(a_on_budget: bool, b_on_budget: bool) -> bool:
    """May a category exist anywhere on this pair? True iff exactly one side
    is on-budget — the category then belongs to that side
    (`leg_may_carry_category` says which)."""
    return leg_may_carry_category(a_on_budget, b_on_budget) or leg_may_carry_category(
        b_on_budget, a_on_budget
    )


def linking_breaks_category_rule(
    a_categorized: bool,
    a_on_budget: bool,
    b_categorized: bool,
    b_on_budget: bool,
) -> bool:
    """Would linking these two concrete legs as one transfer put a category
    somewhere the rule forbids? Used by the paths that join *existing* rows
    (import pairing, the repair pass) rather than creating fresh ones."""
    if a_categorized and b_categorized:
        return True
    if a_categorized:
        return not leg_may_carry_category(a_on_budget, b_on_budget)
    if b_categorized:
        return not leg_may_carry_category(b_on_budget, a_on_budget)
    return False
