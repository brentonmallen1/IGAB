"""Credit cards leave Ready to Assign — the arithmetic, pure.

The model (decided 2026-08-28, replacing the net-cash rule; releases made
cumulative 2026-08-29 after "The Unreleased Reservation"; refusals removed
2026-08-29 after "The Refused Repayment"; assignments brought inside the walk
2026-08-30 after "Two Ledgers, One Debt"):

- A card's balance is not in the budget's cash. The only way a card moves
  Ready to Assign is money deliberately set aside for it.
- The set-aside is a running total, not a floored envelope: funded credit
  spending flows in, card inflows release what was reserved, payments flow
  out, and real assignments on the card's linked category add to it. A month
  where payments exceed the reserve is an overpayment — a credit balance on
  the card, carried forward — not an overspend for Ready to Assign to
  absorb, so no zero floor is applied between months (`CardReserve`).
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

**An assignment is the other way money meets uncovered debt, and it goes
through the same door.** In YNAB, credit overspending debits the Credit Card
Payments category and the assignment covering it credits the same category:
one ledger, net zero, self-cancelling. Here the debt deliberately rides on the
card, *outside* the reserve — that is the whole point of the design and the
rest of this docstring argues it. But the assignment covering that debt lands
*inside* the reserve, and for a while nothing reconciled the two. The result
was exact and unbounded:

    set_aside - owed == assignments + unclaimed - riding

Read the first term. On a card that is always paid in full the reserve does
not converge on what the card owes; it converges on what the card owes plus
every dollar ever assigned to its payment category, for the life of the
budget. Move money back out of an overfunded payment envelope and the same
term drives the reserve permanently negative, at which point
`max(0, owed - max(0, set_aside))` reports the card's entire balance as
uncovered. One defect, two directions ("Two Ledgers, One Debt").

Step 5 of the walk closes it. An assignment retires the ride first, then
reserves **in full** — a conversion, not a diversion. `set_aside` is unchanged
in the month of the assignment; what changes is what every later inflow does,
because the exposure it would have discharged against is gone.

Why that matters beyond bookkeeping: `discharged` is netted out of the
envelope's activity *inside* the walk, so a stale ride turns a refund into a
month the envelope ends negative — and a negative month with no card outflow
left to carry it is written off at the boundary as **cash** overspending,
which Ready to Assign pays for and which never comes back. The
discharged/released split is otherwise neutral to `total_category_balance`;
the boundary floor is how the defect reached Ready to Assign, which is worth
knowing before concluding from the neutral case that nothing is wrong.

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
ONE = Decimal("1")


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


def allocate_capped[T](
    amount: Decimal,
    capacity: dict[T, Decimal],
) -> dict[T, Decimal]:
    """Split `amount` across buckets, each capped at its own capacity.

    Two callers, two kinds of key, one rule. `card_funding` places a month's
    floored overspending across the **cards** it was swiped on, and places a
    card's assignment across the **categories** riding on that card. Writing
    the second one out separately is how a third copy starts.

    Greedy in sorted-key order: deterministic, exact (no proportional
    rounding), and irrelevant in the overwhelmingly common one-bucket case.
    Keys sort as strings so UUIDs and test stubs both work.
    """
    out: dict[T, Decimal] = {}
    remaining = amount
    for bucket in sorted(capacity, key=str):
        take = min(remaining, capacity[bucket])
        if take > ZERO:
            out[bucket] = take
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


def _add[T](series: dict[T, dict[date, Decimal]], key: T, month: date, amount: Decimal) -> None:
    """Accumulate into a per-key, per-month series, skipping exact zeros."""
    if amount == ZERO:
        return
    per_key = series.setdefault(key, {})
    per_key[month] = per_key.get(month, ZERO) + amount


@dataclass(frozen=True)
class CardFunding[C, K]:
    """What one pass over a budget's card history produces.

    A dataclass rather than a tuple because the tuple grew a fourth slot that
    every caller unpacked as `_`, and a slot nobody names is a slot nobody
    tests — which is exactly how the old `truncated` shipped with no coverage
    at all.

    The five reserve legs (`assignments`, `reservations`, `released`,
    `residual`, and the payments the repository supplies) are kept apart
    rather than pre-summed. A set-aside used to be assembled at the call site
    from a net figure plus payments plus assignments, and the assignment leg
    was the one that never entered the walk. `CardReserve` is now the only way
    to put them back together.
    """

    #: Funded credit spending that reserved money, per card per month. The
    #: positive half of the old `funded_by_card`.
    reservations_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: `released` per card per month: an inflow handing back cash the envelope
    #: had genuinely reserved on this card.
    released_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: `residual` per card per month: inflow beyond everything the category
    #: ever had riding on that card. A reserve may go negative on it, which is
    #: a real position (a credit balance) and the T2 bound of the identity.
    residual_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: Assignments to each card's own payment category, per month. Signed:
    #: money moved back out of a card envelope is an ordinary thing to do.
    #: Authoritative — the reserve reads the series from here rather than
    #: re-reading the assignment repo, so the walk and the total cannot
    #: disagree about what was assigned.
    assignments_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: The part of each assignment that retired debt riding on that card.
    #: Not subtracted from the reserve — see the walk's step 5 — but it is
    #: what stops `reserve_discrepancy`'s T1 accepting an assignment as the
    #: explanation for the drift that same assignment caused.
    covered_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: The same covering, attributed to the category whose ride it retired.
    covered_by_category: dict[C, dict[date, Decimal]] = field(default_factory=dict)
    #: What rode onto cards per category per month instead of being written
    #: off. The viewed month's entries are what Ready to Assign subtracts
    #: directly (`uncovered_current`). **Not retracted when an assignment
    #: covers the ride**: this is the historical record the month's own
    #: visible red is paired with, and retracting it would charge Ready to
    #: Assign twice for one shortfall.
    floored_by_category: dict[C, dict[date, Decimal]] = field(default_factory=dict)
    #: The same ridden amounts attributed to the card each was swiped on.
    #: Exact, not apportioned: `allocate_capped` decides it, its pool is
    #: the cards with positive net that month, and that pool sums to at least
    #: the month's net — so the per-card figures sum to the per-category ones.
    floored_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: Signed change in what is riding uncovered on each card, per month:
    #: what went on, less what an inflow discharged, less what an assignment
    #: covered. `sum_through` it for the level — which is the `riding` term of
    #: the closed form.
    riding_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: `discharged` per category per month: the part of that month's card
    #: inflows that repaid uncovered debt rather than returning money to the
    #: envelope. **Already folded into `end_balances`.** Never summed across
    #: months by anyone — carried per month so a row can say why its activity
    #: differs from the register's.
    repaid_by_category: dict[C, dict[date, Decimal]] = field(default_factory=dict)
    #: The month-end series each card-touching category's `available` must be
    #: read out of (`carryover.available_at`) — the ordinary simulation with
    #: `repaid_by_category` folded into each month's activity. Categories with
    #: no card activity are absent: their series is unchanged, and recomputing
    #: it here would give the snapshot path a second opinion to disagree with.
    end_balances: dict[C, dict[date, Decimal]] = field(default_factory=dict)

    @property
    def funded_by_card(self) -> dict[K, dict[date, Decimal]]:
        """Net reservation flow per card per month: reservations, less what
        inflows released or overshot.

        **Derived, never accumulated.** This was a stored field until the legs
        were split apart, and a stored copy sitting beside them would be a
        second opinion for them to disagree with. `CardReserve` is what a
        set-aside is built from; this is for reading one number where the
        split does not matter.
        """
        out: dict[K, dict[date, Decimal]] = {}
        for series, sign in (
            (self.reservations_by_card, ONE),
            (self.released_by_card, -ONE),
            (self.residual_by_card, -ONE),
        ):
            for card, by_month in series.items():
                for month, amount in by_month.items():
                    _add(out, card, month, sign * amount)
        return out


def card_funding[C, K](
    assignments_by_category: dict[C, dict[date, Decimal]],
    activity_by_category: dict[C, dict[date, Decimal]],
    credit_outflows: dict[C, dict[K, dict[date, Decimal]]],
    card_categories: dict[K, C],
) -> CardFunding[C, K]:
    """The whole budget's card funding, in one forward pass over the months.

    Takes each category's raw assignment and activity series,
    `credit_outflows[category][card][month]` (SIGNED net: a month whose card
    activity nets to an inflow is negative), and `card_categories[card]` — the
    payment category linked to each card, whose assignments are the fifth leg
    of that card's reserve.

    **The pass is month-major, and it has to be.** An assignment is made to a
    card's payment category, which has no spending category of its own: it
    retires debt riding on that card across every category that charged it. A
    per-category outer loop cannot reach that. Nor can a second pass, because
    covering a ride changes whether a later inflow discharges or releases,
    which changes `repaid_by_category`, which changes `end_balances`, which
    changes `credit_floored`, which changes what rides — pass two would feed
    pass one, and a fixpoint over a floored carryover is not guaranteed
    unique.

    Within each month, in this order: (1) inflows split through
    `release_split`; (2) each category's adjusted end balance; (3) its floored
    share; (4) the charges; then (5) the card assignments, against the ride
    step 4 has just finished writing.

    Step 5 comes last on purpose. An assignment made in the month a category
    overspends must cover *that month's* ride — the user reads "Uncovered 50"
    on the page in front of them and assigns 50. The consequence, named rather
    than silent: within one month a refund beats an assignment to the ride.
    That is right, and it leaves the assignment as surplus reserve the user
    can see and move.

    Acyclic — every phase reads only state written by an earlier month or an
    earlier phase of this one. Categories within a month are independent, and
    are walked in sorted order so nobody can introduce an order dependency
    without noticing.
    """
    out: CardFunding[C, K] = CardFunding()

    months_by_category: dict[C, list[date]] = {}
    for category, by_card in credit_outflows.items():
        months_by_category[category] = sorted(
            set(assignments_by_category.get(category, {}))
            | set(activity_by_category.get(category, {}))
            | {m for series in by_card.values() for m in series}
        )
    categories_in_month: dict[date, list[C]] = {}
    for category, months in months_by_category.items():
        for month in months:
            categories_in_month.setdefault(month, []).append(category)

    # A card's own assignment series, read once. Absent from `credit_outflows`
    # by construction: a card payment category is not spendable.
    card_assignments: dict[K, dict[date, Decimal]] = {
        card: assignments_by_category.get(category, {})
        for card, category in card_categories.items()
    }

    # Running state, all carried across months. `ridden` and `reserved` stay
    # per (category, card) — pooling the CARD dimension would let a refund on
    # one card release another, which is the thing the module docstring
    # refuses. Only `ridden` is ever read pooled, only across categories, and
    # only by one card's own assignment, which has no category to scope it to.
    carryover: dict[C, Decimal] = {}
    ridden: dict[tuple[C, K], Decimal] = {}
    reserved: dict[tuple[C, K], Decimal] = {}

    all_months = sorted(
        set(categories_in_month) | {m for series in card_assignments.values() for m in series}
    )
    for month in all_months:
        for category in sorted(categories_in_month.get(month, []), key=str):
            nets = {
                card: series[month]
                for card, series in credit_outflows[category].items()
                if month in series
            }

            # 1. Inflows, split three ways. Reads only exposure carried in
            #    from earlier months, never this month's floored share.
            repaid = ZERO
            for card, net in nets.items():
                if net >= ZERO:
                    continue
                pair = (category, card)
                discharged, released, residual = release_split(
                    -net, ridden.get(pair, ZERO), reserved.get(pair, ZERO)
                )
                ridden[pair] = ridden.get(pair, ZERO) - discharged
                reserved[pair] = reserved.get(pair, ZERO) - released - residual
                repaid += discharged
                _add(out.released_by_card, card, month, released)
                _add(out.residual_by_card, card, month, residual)
                _add(out.riding_by_card, card, month, -discharged)
            if repaid != ZERO:
                out.repaid_by_category.setdefault(category, {})[month] = repaid

            # 2. The month's end balance, with the correction folded in — the
            #    same simulation `carryover.monthly_end_balances` runs, sharing
            #    its floor so the two cannot drift.
            end = (
                carryover.get(category, ZERO)
                + assignments_by_category.get(category, {}).get(month, ZERO)
                + activity_by_category.get(category, {}).get(month, ZERO)
                - repaid
            )
            out.end_balances.setdefault(category, {})[month] = end
            carryover[category] = next_carryover(end)

            # 3. What the shortfall put on a card, from the ADJUSTED balance.
            floored = credit_floored(end, sum(nets.values(), ZERO))
            if floored > ZERO:
                out.floored_by_category.setdefault(category, {})[month] = floored

            # 4. The charges. Floored first, funded is the remainder —
            #    allocated per card so each card's envelope receives only what
            #    was spent on it. Only cards that netted to spending that month
            #    can carry the ride.
            floored_share = allocate_capped(floored, {c: n for c, n in nets.items() if n > ZERO})
            for card, share in floored_share.items():
                _add(out.floored_by_card, card, month, share)
                _add(out.riding_by_card, card, month, share)
                ridden[(category, card)] = ridden.get((category, card), ZERO) + share
            for card, net in nets.items():
                if net <= ZERO:
                    continue
                delta = net - floored_share.get(card, ZERO)
                reserved[(category, card)] = reserved.get((category, card), ZERO) + delta
                _add(out.reservations_by_card, card, month, delta)

        # 5. The card assignments, against the ride the month has just settled.
        #
        #    A **conversion, not a diversion**: the whole assignment still
        #    reserves, exactly as before, and what changes is that the debt it
        #    covers stops being uncovered. Reserving only the remainder would
        #    make the assignment a visible no-op and stop Ready to Assign
        #    falling by money the user just committed.
        #
        #    Leaving the ride in place instead is what the defect was. A stale
        #    `ridden` sends a later refund down the `discharged` path, where it
        #    is netted out of the envelope's activity rather than handed back —
        #    and a month pushed negative that way is written off at the
        #    boundary as *cash* overspending, permanently. The envelope keeps
        #    nothing and Ready to Assign pays for a debt the user already
        #    covered.
        for card, series in card_assignments.items():
            amount = series.get(month, ZERO)
            if amount == ZERO:
                continue
            _add(out.assignments_by_card, card, month, amount)
            if amount <= ZERO:
                # Money moved back out of a card envelope re-rides nothing:
                # there is no non-arbitrary category to charge, and the
                # spending it funded was funded. The reserve simply falls,
                # and `uncovered` rises to meet it.
                continue
            pool = {
                cat: exposure
                for (cat, k), exposure in ridden.items()
                if k == card and exposure > ZERO
            }
            for cat, take in allocate_capped(amount, pool).items():
                ridden[(cat, card)] -= take
                _add(out.covered_by_card, card, month, take)
                _add(out.covered_by_category, cat, month, take)
                _add(out.riding_by_card, card, month, -take)

    return out


@dataclass(frozen=True)
class CardReserve:
    """One card's set-aside, assembled once from all five of its legs.

    There is exactly one way to build a set-aside and it is `card_reserve`.
    The reserve used to be composed at the call site — `funded_by_card` plus
    payments, with assignments added on afterwards — and the assignment leg
    was precisely the one that never entered the walk, so the debt it covered
    rode on forever. A subset of these legs is not a reserve.
    """

    #: + money the user put into the card's payment envelope. Signed.
    assignments: dict[date, Decimal] = field(default_factory=dict)
    #: + funded credit spending that moved into this card.
    reservations: dict[date, Decimal] = field(default_factory=dict)
    #: − an inflow returning cash the envelope had reserved here.
    released: dict[date, Decimal] = field(default_factory=dict)
    #: − an inflow beyond anything that ever rode here.
    residual: dict[date, Decimal] = field(default_factory=dict)
    #: − transfers from the budget's cash that paid the card.
    payments: dict[date, Decimal] = field(default_factory=dict)

    def set_aside(self, month_start: date) -> Decimal:
        """The reserve at `month_start`: a plain running total of five legs.

        Deliberately NOT `carryover.available_through`: the zero floor between
        months is the write-off rule for spending envelopes, where a negative
        month is overspending absorbed from Ready to Assign. A set-aside's
        negative month is an overpayment — a real credit balance on the card —
        and flooring it discarded the surplus and ratcheted the reserve upward
        by every overpaid month. The negative carries; if a surface prefers
        not to show one, it floors at the presentation layer only.
        """
        return (
            sum_through(self.assignments, month_start)
            + sum_through(self.reservations, month_start)
            - sum_through(self.released, month_start)
            - sum_through(self.residual, month_start)
            - sum_through(self.payments, month_start)
        )


def card_reserve[C, K](
    funding: CardFunding[C, K],
    card: K,
    payments: dict[date, Decimal],
) -> CardReserve:
    """One card's five legs, out of the walk plus the payments it did not see.

    `payments` stays outside `card_funding` because it is a repository query,
    and because a payment legitimately does NOT retire riding debt: paying a
    bill the budget never funded drives the reserve negative, and the
    assignment that repairs it is what retires the ride.
    """
    return CardReserve(
        assignments=funding.assignments_by_card.get(card, {}),
        reservations=funding.reservations_by_card.get(card, {}),
        released=funding.released_by_card.get(card, {}),
        residual=funding.residual_by_card.get(card, {}),
        payments=payments,
    )


def _allowance(*terms: Decimal) -> Decimal:
    """Capacity to explain a gap, from terms that are each allowed to be zero
    but never negative.

    Each term floors **on its own**, not after summing. `assigned` is a signed
    lifetime total and goes negative the moment someone moves more money back
    out of a card's payment envelope than they ever put in — ordinary
    reallocation. Unfloored, `L - R` with `R < 0` reported the shortfall as
    drift on a card with nothing wrong ("The Watchman's Arithmetic"). Flooring
    the *sum* instead would fix that case and break another: a negative
    assignment total would cancel an outside credit that genuinely does explain
    an over-reserve, inventing a fresh false positive of the credit's size.
    """
    return sum((max(ZERO, t) for t in terms), ZERO)


def reserve_discrepancy(
    set_aside: Decimal,
    balance: Decimal,
    assigned: Decimal,
    covered: Decimal,
    payments: Decimal,
    residual_releases: Decimal,
    unclaimed_rows: Decimal,
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
    one replaces a clause the old invariant used to excuse. Every right-hand
    side is an allowance — capacity to explain something — so every term on it
    floors at zero individually (`_allowance`); a bound written `L - R` is only
    sound while `R >= 0`, and `assigned` is signed:

    - **T1** `over_reserved <= (assigned - covered) + unclaimed_rows`. A
      reserve exceeds its debt only by money someone deliberately assigned to
      the card **and that has not already done its job**, or by a row on the
      card the budget has no claim on. Replaces "for a card with no
      assignments".

      The subtraction is the whole content of this bound. With the plain
      lifetime `assigned`, the quantity that *caused* the drift and the
      quantity offered to *explain* it were the same number, so the further
      the reserve drifted the more thoroughly the check was satisfied — the
      same failure the old invariant's exclusion clause had, re-admitted as
      an allowance. An assignment that retired riding debt has been spent; it
      explains the debt it covered, not a reserve standing beyond it.

      Note `assigned - covered` is ONE term inside `_allowance`, not two.
      Flooring `covered` on its own would break the subtraction.
    - **T2** `short_reserved <= payments + residual_releases`. A reserve goes
      negative only by paying the card more than was reserved, or by an inflow
      beyond what its category ever had riding there. Replaces "and no inflows
      that predate their reservations".
    - **T3** `card_credit <= short_reserved + unclaimed_rows`. A credit
      balance on a card is either budget money or somebody else's. This is the
      one that catches a repayment landing where no category ever charged.

    `assigned` is the *net* lifetime assignment to the card's own linked
    category — negative where more has been moved out than in, which is why it
    is floored rather than trusted to be positive. `covered` is
    `CardFunding.covered_by_card` summed through the month: the part of those
    assignments that retired riding debt. `payments` are transfers from the
    budget's cash, `residual_releases` is `CardFunding.residual_by_card`
    summed for this card, and `unclaimed_rows` is
    `txn_filters.UNCLAIMED_CARD_ROW` — the signed net of card rows no term of
    the model claims, in both directions.

    **What this does not do.** All three bounds are consequences of the
    identity above, so they check the walk against itself, not against
    reality. What makes T1 bite now is that the identity only closes if
    assignments really do retire rides — a regression in the walk's step 5
    drives `covered` to zero and T1 goes quiet again, exactly as it did when
    the unclaimed term was widened in one sign only. The independent checks
    are the YNAB oracle (`integrations/ynab/parity.py`) and the closed-form
    test.
    """
    owed = -balance
    over_reserved = max(ZERO, set_aside - max(ZERO, owed))
    short_reserved = max(ZERO, -set_aside)
    card_credit = max(ZERO, -owed)
    worst = max(
        over_reserved - _allowance(assigned - covered, unclaimed_rows),
        short_reserved - _allowance(payments, residual_releases),
        card_credit - _allowance(short_reserved, unclaimed_rows),
    )
    return worst if worst > ZERO else ZERO
