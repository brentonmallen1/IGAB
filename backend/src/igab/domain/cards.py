"""Credit cards leave Ready to Assign — the arithmetic, pure.

The model (decided 2026-08-28, replacing the net-cash rule; releases made
cumulative 2026-08-29 after "The Unreleased Reservation"; refusals removed
2026-08-29 after "The Refused Repayment"; assignments brought inside the walk
2026-08-30 after "Two Ledgers, One Debt"; a negative Set aside made
overspending 2026-09-24, matching YNAB):

- A card's balance is not in the budget's cash. The only way a card moves
  Ready to Assign is money deliberately set aside for it.
- The set-aside is a running total of its legs: funded credit spending
  flows in, card inflows release what was reserved, payments flow out, and
  real assignments on the card's linked category add to it. **A month that
  ends with it below zero is overspending**, exactly as YNAB treats a Credit
  Card Payments category paid past what it held: red for the rest of that
  month, then written off — the card's envelope starts the next month at
  zero and Ready to Assign absorbs the amount, the same `next_carryover`
  rule every envelope follows. The write-off is booked as its own leg
  (`written_off`, dated the 1st) rather than applied as a silent floor, so
  the legs still sum to the figure and the page can say where it went.
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
   reduces `set_aside`, **uncapped**, so a reserve may go negative within the
   month — overspending, written off at the month's end like any other.

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
every dollar ever assigned to its envelope, for the life of the
budget. Move money back out of an overfunded card's envelope and the same
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

**An import anchor coarsens attribution the same way, on purpose.** An
anchored walk (`AnchorOpenings`) starts at B with per-card openings only:
YNAB publishes no per-pair history, so opening uncovered debt rides under the
`ANCHOR_OPENING` sentinel — retired by assignments through step 5's pooled
read, unreachable by inflows — and per-pair `reserved` starts empty. A
post-anchor refund of a pre-anchor funded charge therefore lands as residual:
exact at the card level (the balance fell, the reserve falls), coarser in
category attribution, and the accepted price of not re-deriving the history
the anchor exists to retire.

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

from collections.abc import Container, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Final, cast

from igab.domain.carryover import next_carryover, sum_through, write_off
from igab.domain.dates import add_months

ZERO = Decimal("0")
ONE = Decimal("1")

#: The category key an import anchor's opening uncovered debt rides under.
#: Not a real category: YNAB publishes per-card uncovered only, so the ride
#: has no category to belong to. Step 5's pooled read retires it like any
#: other ride; inflows can never reach it, because an inflow's pair key is
#: always the register row's real category. A plain string, because
#: `allocate_capped` sorts keys through `str` and UUIDs and test stubs both
#: survive that.
ANCHOR_OPENING: Final = "anchor-opening"


@dataclass(frozen=True)
class AnchorOpenings[C, K]:
    """YNAB's displayed position at an import boundary, as walk seeds.

    `month` is B — the first month the walk re-derives. The openings
    themselves are dated B−1 (the last complete YNAB month): each category's
    raw Available, each card's signed CCP Available, and each card's
    uncovered debt (`max(0, -balance - ccp)`, so never negative). Built in
    exactly one place per consumer — `ImportAnchorRepository.get_for_budget`
    on the serving side, the scenario adapter in `sample_budget` — so the
    walk, the snapshot rebuild, and the probe cannot disagree about what was
    anchored.
    """

    month: date
    available_by_category: dict[C, Decimal] = field(default_factory=dict)
    reserve_by_card: dict[K, Decimal] = field(default_factory=dict)
    uncovered_by_card: dict[K, Decimal] = field(default_factory=dict)

    @property
    def opening_month(self) -> date:
        """B−1 — the month the openings are stated at."""
        return add_months(self.month, -1)

    def opening_for(self, category: C) -> tuple[date, Decimal]:
        """One category's carryover seed, `(B−1, its opening Available)`.

        Zero for a category the anchor never named: an envelope YNAB showed
        at zero and one the anchor skipped are the same position, and both
        truncate. The one derivation — the serving path, the snapshot
        rebuild and the generator's own verification all read it from here,
        because three hand-written copies of `.get(id, ZERO)` is how the
        cache and the fallback learn to disagree.
        """
        return (self.opening_month, self.available_by_category.get(category, ZERO))


def credit_floored(end_of_month: Decimal, card_charges: Decimal) -> Decimal:
    """The credit-funded part of one month's shortfall, for one category.

    A month that ended at -50 with 70 spent on cards has 50 riding as card
    debt and 0 written off from Ready to Assign; the same month with 20 on
    cards has 20 riding and 30 written off. A month that ended non-negative
    contributes nothing.

    `card_charges` is what was CHARGED to cards that month — the positive
    nets only — not the month's net card activity. The cap used to be the net,
    and that counted a discharging inflow twice: `card_funding` has already
    subtracted it from `end_of_month` as `repaid` (step 1 → step 2), so
    netting it out of the cap as well under-stated what may ride. A tab
    charged 100 on one card while a refund on another discharged an older
    ride read as fully reserved on the first card, and the 100 nobody had
    funded was written off as cash overspending. Released and residual
    inflows are real money already inside `end_of_month` through activity, so
    they never belonged in the cap either.
    """
    if end_of_month >= ZERO:
        return ZERO
    return min(-end_of_month, max(ZERO, card_charges))


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
        # Only the oracle and tests call this, with a single card's signed
        # series; a net inflow month charges nothing, which the floor already
        # treats as zero.
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

    Greedy, largest capacity first — the card that was charged most carries
    the shortfall first; the biggest ride on a card is retired first. Exact
    (no proportional rounding), deterministic, and a rule a person can be
    told. It was sorted-key order, which for real data meant UUID order: which
    card wore Uncovered for a shared shortfall — and therefore which remedy
    its row offered — depended on whose id happened to sort first, and two
    households with identical spending saw different cards flagged.
    `SETTLED_ELSEWHERE` exists to explain the consequence of that split;
    with this order the explanation at least names a reason. Ties break on
    the key as a string so UUIDs and test stubs both stay deterministic.
    Irrelevant in the overwhelmingly common one-bucket case.
    """
    out: dict[T, Decimal] = {}
    remaining = amount
    for bucket in sorted(capacity, key=lambda k: (-capacity[k], str(k))):
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

    The reserve legs (`opening`, `assignments`, `reservations`, `released`,
    `residual`, `payments`) are kept apart rather than pre-summed. A set-aside
    used to be assembled at the call site from a net figure plus payments plus
    assignments, and the assignment leg
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
    #: The same residual, attributed to the (category, card) pair that carried
    #: the inflow — a decomposition of `residual_by_card`, never a second
    #: opinion about its total (pinned by test). Kept because "WHICH envelope
    #: produced the residual" is the whole question a negative reserve raises:
    #: a reimbursement filed to a category that never charged this card, a
    #: refund filed to the wrong envelope, a payment onto card A for spending
    #: done on card B — every one of them lands here, and without the pair the
    #: diagnosis stops at "residual".
    residual_by_pair: dict[tuple[C, K], dict[date, Decimal]] = field(default_factory=dict)
    #: Assignments to each card's own envelope, per month. Signed:
    #: money moved back out of a card's envelope is an ordinary thing to do.
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
    #: The same allocation kept at full resolution: which envelope rode onto
    #: which card, per month. `floored_by_card` and `floored_by_category` are
    #: both sums of this (pinned by test), so a surface that shows the
    #: breakdown and one that shows a total cannot disagree.
    #:
    #: This is what answers "why is this envelope still red after I covered
    #: the overspending" — the cash part was covered and the ride was not,
    #: and until this existed no surface could name the card holding it.
    floored_by_pair: dict[tuple[C, K], dict[date, Decimal]] = field(default_factory=dict)
    #: Signed change in what is riding uncovered on each card, per month:
    #: what went on, less what an inflow discharged, less what an assignment
    #: covered. `sum_through` it for the level — which is the `riding` term of
    #: the closed form.
    riding_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: What an import brought in as uncovered debt and is still riding, per
    #: card per month: the `ANCHOR_OPENING` seed, less what card assignments
    #: have since retired of it. Kept APART from `riding_by_card` because the
    #: two mean different things to a reader — "a month ended short and this
    #: rode" is a story about the budget; "you arrived owing this" is not —
    #: and pooling them let a card on an imported budget read "$2,000 of
    #: spending rode onto this card when a month ended short" about debt that
    #: predates the budget, with a remedy (fund that month's envelope) that
    #: nothing could act on. Retired only by assigning to the card.
    imported_riding_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: `discharged` per category per month: the part of that month's card
    #: inflows that repaid uncovered debt rather than returning money to the
    #: envelope. **Already folded into `end_balances`.** Never summed across
    #: months by anyone — carried per month so a row can say why its activity
    #: differs from the register's.
    repaid_by_category: dict[C, dict[date, Decimal]] = field(default_factory=dict)
    #: Transfers from the budget's cash that paid each card, per month — the
    #: repository sum, handed to the walk so the walk owns every leg of a
    #: reserve and the anchor's truncation is applied once, here. On an
    #: anchored budget months before B are dropped: the B−1 seed already
    #: accounts for them.
    payments_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: What each card's envelope had written off into Ready to Assign, dated
    #: the 1st of the month that absorbed it: the previous month ended with
    #: Set aside below zero by exactly this. The seventh leg of a reserve.
    written_off_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
    #: An import anchor's `{B−1: CCP Available}` per card — signed, since a
    #: card can be imported with its envelope in the red. Empty everywhere
    #: but anchored budgets.
    opening_by_card: dict[K, dict[date, Decimal]] = field(default_factory=dict)
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


def cash_written_off(end_of_month: Decimal, credit_part: Decimal) -> Decimal:
    """What Ready to Assign absorbs from one envelope when a month ends at
    `end_of_month`, of which `credit_part` rode onto a card.

    The ride is card debt, not a write-off — it waits on the card, calm, as
    Uncovered — so only the rest of the shortfall comes out of the next
    month's Ready to Assign. A card's own envelope has no ride of its own:
    all of its red is written off (`credit_part` zero).
    """
    return max(ZERO, write_off(end_of_month) - credit_part)


def _cover[C, K](
    out: CardFunding[C, K],
    ridden: dict[tuple[C, K], Decimal],
    card: K,
    month: date,
    amount: Decimal,
) -> None:
    """Money reaching a card's envelope from Ready to Assign retires the debt
    riding on that card first — largest ride first, `ANCHOR_OPENING` included.

    The one routine, because two kinds of money arrive this way: an
    assignment to the card (step 5), and a month-end write-off, which is
    Ready to Assign covering the card's overspending. Written twice, the two
    would retire rides differently — the shape of "Two Ledgers, One Debt".
    """
    pool = {cat: exposure for (cat, k), exposure in ridden.items() if k == card and exposure > ZERO}
    for cat, take in allocate_capped(amount, pool).items():
        ridden[(cat, card)] -= take
        _add(out.covered_by_card, card, month, take)
        _add(out.covered_by_category, cat, month, take)
        if cat == ANCHOR_OPENING:
            _add(out.imported_riding_by_card, card, month, -take)
        else:
            _add(out.riding_by_card, card, month, -take)


def card_funding[C, K](
    assignments_by_category: dict[C, dict[date, Decimal]],
    activity_by_category: dict[C, dict[date, Decimal]],
    credit_outflows: dict[C, dict[K, dict[date, Decimal]]],
    card_categories: dict[K, C],
    openings: AnchorOpenings[C, K] | None = None,
    payments_by_card: dict[K, dict[date, Decimal]] | None = None,
) -> CardFunding[C, K]:
    """The whole budget's card funding, in one forward pass over the months.

    Takes each category's raw assignment and activity series,
    `credit_outflows[category][card][month]` (SIGNED net: a month whose card
    activity nets to an inflow is negative), and `card_categories[card]` — the
    card's envelope linked to each card, whose assignments are a leg of that
    card's reserve. `payments_by_card` is the transfers from the budget's cash
    that paid each card; the walk records them as the payments leg so that
    every leg of a reserve comes out of this one pass, truncated at an import
    anchor in one place.

    **Every calendar month is walked**, from the first month with any data (B
    on an anchored budget) to the last, gaps included — a month with only a
    payment in it is still a month the card's reserve moves in.

    **The pass is month-major, and it has to be.** An assignment is made to a
    card's envelope, which has no spending category of its own: it
    retires debt riding on that card across every category that charged it. A
    per-category outer loop cannot reach that. Nor can a second pass, because
    covering a ride changes whether a later inflow discharges or releases,
    which changes `repaid_by_category`, which changes `end_balances`, which
    changes `credit_floored`, which changes what rides — pass two would feed
    pass one, and a fixpoint over a floored carryover is not guaranteed
    unique.

    Within each month, in this order: (0) last month's negative Set aside is
    written off — Ready to Assign covers it, retiring rides first; (1) inflows
    split through `release_split`; (2) each category's adjusted end balance;
    (3) its floored share; (4) the charges; (5) the card assignments, against
    the ride step 4 has just finished writing; (6) the payments.

    Step 0 comes first so a refund later in the month finds the ride already
    retired and releases to its envelope, as YNAB hands a refund back to the
    category. After the last month a final write-off is booked at the month
    that follows, so any later month reads the card at zero.

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
    # by construction: a card's envelope is not spendable.
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

    if openings is not None:
        # An import anchor: seed the running state from YNAB's own B−1
        # position and walk months >= B only. The carryover seed is the same
        # rule `carryover.monthly_end_balances` applies (floored opening,
        # earlier months skipped) — a differential test holds the two walks
        # to one answer. The opening uncovered debt rides under
        # ANCHOR_OPENING: step 5 retires it like any ride; per-pair
        # `reserved` is deliberately NOT seeded, so a post-anchor refund of
        # a pre-anchor funded charge lands as residual — exact at the card
        # level (balance falls, reserve falls), coarser in attribution.
        for category, amount in openings.available_by_category.items():
            carryover[category] = next_carryover(amount)
        for card, uncovered in openings.uncovered_by_card.items():
            if uncovered > ZERO:
                ridden[(cast(C, ANCHOR_OPENING), card)] = uncovered
                _add(out.imported_riding_by_card, card, openings.opening_month, uncovered)
    payments = payments_by_card or {}
    # Each card's running Set aside, to know what a month ended at. Seeded at
    # the anchor's signed B−1 reserve, so a card imported with its envelope in
    # the red is written off at B — the same rule as a category opening.
    level: dict[K, Decimal] = {}
    if openings is not None:
        for card, reserve in openings.reserve_by_card.items():
            level[card] = reserve

    def write_off_into(month: date) -> None:
        for card in sorted(level, key=str):
            amount = write_off(level[card])
            if amount > ZERO:
                _add(out.written_off_by_card, card, month, amount)
                _cover(out, ridden, card, month, amount)
                level[card] += amount

    if openings is not None:
        # Every card the walk knows of gets its B−1 entry, a zero included:
        # the entry is also the timeline's seam row, which an anchored card
        # opens on whatever YNAB showed.
        known_cards = (
            set(card_categories)
            | set(openings.reserve_by_card)
            | set(payments)
            | {card for by_card in credit_outflows.values() for card in by_card}
        )
        for card in known_cards:
            out.opening_by_card[card] = {
                openings.opening_month: openings.reserve_by_card.get(card, ZERO)
            }

    data_months = (
        set(categories_in_month)
        | {m for series in card_assignments.values() for m in series}
        | {m for series in payments.values() for m in series}
    )
    if openings is not None:
        data_months = {m for m in data_months if m >= openings.month}
    all_months: list[date] = []
    if data_months:
        month, last = min(data_months), max(data_months)
        while month <= last:
            all_months.append(month)
            month = add_months(month, 1)
    for month in all_months:
        # 0. Last month's negative is overspending: Ready to Assign covers it.
        write_off_into(month)
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
                level[card] = level.get(card, ZERO) - released - residual
                _add(out.riding_by_card, card, month, -discharged)
                if residual != ZERO:
                    per_pair = out.residual_by_pair.setdefault(pair, {})
                    per_pair[month] = per_pair.get(month, ZERO) + residual
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
            #    Capped by what was CHARGED, not the month's net: a discharging
            #    inflow is already out of `end` as `repaid`, and netting it out
            #    of the cap too is how a never-funded charge read as reserved.
            floored = credit_floored(end, sum((n for n in nets.values() if n > ZERO), ZERO))
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
                if share != ZERO:
                    per_pair = out.floored_by_pair.setdefault((category, card), {})
                    per_pair[month] = per_pair.get(month, ZERO) + share
                ridden[(category, card)] = ridden.get((category, card), ZERO) + share
            for card, net in nets.items():
                if net <= ZERO:
                    continue
                delta = net - floored_share.get(card, ZERO)
                reserved[(category, card)] = reserved.get((category, card), ZERO) + delta
                _add(out.reservations_by_card, card, month, delta)
                level[card] = level.get(card, ZERO) + delta

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
            level[card] = level.get(card, ZERO) + amount
            if amount <= ZERO:
                # Money moved back out of a card's envelope re-rides nothing:
                # there is no non-arbitrary category to charge, and the
                # spending it funded was funded. The reserve simply falls,
                # and `uncovered` rises to meet it.
                continue
            _cover(out, ridden, card, month, amount)

        # 6. The payments. A payment does NOT retire riding debt: paying a
        #    bill the budget never funded drives the reserve negative, and
        #    what repairs that is covering the difference — or, at the
        #    month's end, the write-off.
        for card, series in payments.items():
            paid = series.get(month, ZERO)
            _add(out.payments_by_card, card, month, paid)
            if paid != ZERO:
                level[card] = level.get(card, ZERO) - paid

    # The last month's own negative, written off where any later month reads
    # it. Invisible at the last month itself: `sum_through` stops there.
    if all_months:
        write_off_into(add_months(all_months[-1], 1))
    elif openings is not None:
        write_off_into(openings.month)

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

    #: + YNAB's own CCP Available at an import anchor's B−1 — at most one
    #: entry, and only on anchored budgets. Signed: a card can be imported
    #: with its envelope in the red. The sixth leg, first in time.
    opening: dict[date, Decimal] = field(default_factory=dict)
    #: + money the user put into the card's envelope. Signed.
    assignments: dict[date, Decimal] = field(default_factory=dict)
    #: + funded credit spending that moved into this card.
    reservations: dict[date, Decimal] = field(default_factory=dict)
    #: − an inflow returning cash the envelope had reserved here.
    released: dict[date, Decimal] = field(default_factory=dict)
    #: − an inflow beyond anything that ever rode here.
    residual: dict[date, Decimal] = field(default_factory=dict)
    #: − transfers from the budget's cash that paid the card.
    payments: dict[date, Decimal] = field(default_factory=dict)
    #: + what Ready to Assign absorbed when a month ended below zero, dated
    #: the 1st of the month that absorbed it.
    written_off: dict[date, Decimal] = field(default_factory=dict)

    def set_aside(self, month_start: date) -> Decimal:
        """The reserve at `month_start`: a plain running total of seven legs.

        Negative only within the month that produced it — the next month's
        `written_off` entry brings it back to zero. Booked as a leg rather
        than applied as a floor between months, which is what the earlier
        clamp did wrong: it discarded the amount silently, so the legs stopped
        summing to the figure and nothing could say where the money went.
        """
        return (
            sum_through(self.opening, month_start)
            + sum_through(self.written_off, month_start)
            + sum_through(self.assignments, month_start)
            + sum_through(self.reservations, month_start)
            - sum_through(self.released, month_start)
            - sum_through(self.residual, month_start)
            - sum_through(self.payments, month_start)
        )


def card_reserve[C, K](funding: CardFunding[C, K], card: K) -> CardReserve:
    """One card's legs, out of the walk.

    Every leg comes from `card_funding` — the payments and an import anchor's
    opening included. They used to be passed in beside the walk, which meant
    three callers each truncated the payments at an anchor and built the
    opening leg by hand, and a reserve assembled from a walk and a separate
    payments series could disagree about which months it covered.
    """
    return CardReserve(
        opening=funding.opening_by_card.get(card, {}),
        assignments=funding.assignments_by_card.get(card, {}),
        reservations=funding.reservations_by_card.get(card, {}),
        released=funding.released_by_card.get(card, {}),
        residual=funding.residual_by_card.get(card, {}),
        payments=funding.payments_by_card.get(card, {}),
        written_off=funding.written_off_by_card.get(card, {}),
    )


@dataclass(frozen=True)
class CardPosition:
    """Where one card stands: the four terms the reserve identity is written in.

    One home for the arithmetic that turns a (set_aside, balance) pair into
    words. These four used to be local expressions inside
    `reserve_discrepancy`, and `uncovered` was spelled a SECOND time inline in
    `budget_service.get_budget_summary` — two spellings of one rule, and the
    surface needed a third to tell an overpayment from a negative reserve.

    The four are not independent: at most one of `over_reserved` and
    `short_reserved` is non-zero, and `uncovered` and `card_credit` cannot both
    be. That is the point — naming them separately is what lets a caller say
    WHICH way a card is unusual instead of only that it is.
    """

    #: Owed beyond the reserve. The inner floor is load-bearing: a negative
    #: set-aside reserves nothing, so it cannot reduce what the card owes.
    uncovered: Decimal
    #: Reserve standing beyond the debt. Money assigned to a card that never
    #: had a ride to retire accumulates here for the life of the budget.
    over_reserved: Decimal
    #: The card's envelope is in the red — payments or inflows ran past
    #: everything reserved. NOT an overpayment unless `card_credit` is also
    #: non-zero; the card can owe a full balance while this is large.
    short_reserved: Decimal
    #: The card holds your money: it owes nothing and then some. This is the
    #: only state the word "overpaid" was ever true of.
    card_credit: Decimal


def residual_is_pass_through(assigned_amounts: Iterable[Decimal], available: Decimal) -> bool:
    """Whether an envelope's residual took nothing from anybody.

    Residual is inflow beyond everything a category ever had riding on a card
    (`CardFunding.residual_by_pair`): it reduces the card's reserve without
    releasing any envelope's cash. The complaint a surface makes about it is
    that *the envelope keeps the money*. This says when that complaint is
    false, and the answer is not about the residual at all — it is about
    whether the envelope was ever an envelope.

    A **receivable ledger** is a category run as a running tab rather than a
    fund: never assigned to, allowed to go negative as charges land, squared
    to zero when the person settles up. Its charges land on whatever account
    was handy — cash accounts and other cards included — while the single
    repayment lands on one card, so that pair nets to an inflow every month
    and residual accumulates monotonically. Nothing is lost: the repayment
    paid the card down by exactly that much more than was charged to it, so
    the reserve falls beside a debt that fell with it, and the household pays
    the card that much less from its own cash. Both legs carry `-1` into
    `set_aside`; they cancel.

    The discriminator is not "does available look like zero" — a funded
    envelope that spent everything it held reads zero too, and a refund
    arriving there is a genuine release that failed to find its exposure.
    It is **never assigned, and holding nothing now**:

    - **never assigned** — not one month carried a non-zero amount, so no
      cash of the household's was ever reserved through it to hand back.
    - `available <= 0` — it is holding none of the inflow. A ledger squares to
      zero; one carrying a positive balance has kept card money, which is the
      complaint, restated.

    "Never", not "nets to zero": a category funded in March and emptied in
    April held real money in between, its charges reserved against it, and a
    later refund there is a release that failed to find its exposure. Summing
    the assignments would call that history a ledger. Reasoning about how much
    funding is a little would put a threshold between a household's money and
    a detector's silence, so there is no threshold — one non-zero assignment,
    ever, and the envelope is an envelope.
    """
    return all(amount == ZERO for amount in assigned_amounts) and available <= ZERO


def receivable_ledgers[C](
    assigned_ever: Mapping[C, Iterable[Decimal]],
    available_by_category: Mapping[C, Decimal],
) -> set[C]:
    """Which of a budget's categories are receivable ledgers.

    `residual_is_pass_through` is the rule; this is the sweep, in one place
    because two callers need the answer and they must not disagree. The
    served `set_aside_state` asks so a settle-up does not read as an envelope
    keeping card money, and `AccountHygieneService` asks so it stays quiet
    about the same card. Written twice, those two surfaces would eventually
    call one household's bookkeeping normal on the budget page and a defect
    on the accounts page.

    `available_by_category` must be Available **as the Budget page states
    it** — card-corrected where a card inflow repaid uncovered debt. The
    uncorrected sum reads high on exactly the categories this asks about,
    which are the ones card inflows land in.

    A category absent from `available_by_category` is not a ledger: nothing
    here knows what it holds, and silence is the wrong way to be wrong.
    """
    return {
        category
        for category, available in available_by_category.items()
        if residual_is_pass_through(assigned_ever.get(category, ()), available)
    }


def card_position(set_aside: Decimal, balance: Decimal) -> CardPosition:
    """The four terms, from a reserve and a balance. `balance` is signed as the
    ledger holds it — negative is owed.

    Split from `reserve_discrepancy` so a surface can ask where a card stands
    without asking whether anything is wrong. Those are different questions and
    conflating them hid two real cards for years: a reserve several times its
    balance and a reserve below zero on a card owing thousands both satisfy the
    discrepancy check's bounds, because those bounds are ALLOWANCES — T1
    excuses an over-reserve explained by assignments, T2 excuses a negative one
    explained by payments or residual. A zero discrepancy means the identity
    holds, never that the number on screen is sensible.
    """
    owed = -balance
    return CardPosition(
        uncovered=max(ZERO, owed - max(ZERO, set_aside)),
        over_reserved=max(ZERO, set_aside - max(ZERO, owed)),
        short_reserved=max(ZERO, -set_aside),
        card_credit=max(ZERO, -owed),
    )


class SetAsideState(StrEnum):
    """Which of the eight situations a card's Set aside is in.

    The surface used to decide this for itself, out of `set_aside` and
    `balance`, and it could not: two of the eight are told apart only by
    `residual_by_pair` and by whether an envelope was EVER assigned to, and
    neither crosses the wire. So the row spent one label — "ahead of budget" —
    on three causes whose remedies differ, and on the fourth it offered advice
    that does nothing (F8, below).

    Named for the situation rather than for the sign of a number, because the
    sign is what the user already sees and is not what they are asking about.
    A negative Set aside deliberately gets **no** noun of its own: four of
    these states produce one, they want opposite responses, and a single word
    for all four is precisely the flattening that made the column unreadable.

    `StrEnum` because this crosses the API to the client, like `TargetType`.
    """

    #: Set aside is doing its job: money is waiting for a bill, and nothing
    #: about the figure needs explaining. The card may still owe more than it
    #: holds — that is Uncovered's column to answer, not this one.
    FUNDED = "funded"
    #: More set aside than the card owes. Assignments stay in a card's
    #: envelope until riding debt turns up to retire, so on a card always paid
    #: from funded envelopes they simply accumulate. Releasable.
    SURPLUS = "surplus"
    #: The card owes nothing and holds money of yours — the only state the
    #: word "overpaid" was ever true of. A negative Set aside alone is NOT it.
    CARD_HOLDS_IT = "card_holds_it"
    #: Somebody else's settle-up drove Set aside below zero. Their spending ran
    #: through a running tab rather than a fund (`residual_is_pass_through`),
    #: so no envelope of yours is holding the money: the repayment paid this
    #: card down by exactly as much as it took out of Set aside. Nothing to do.
    SETTLED_BY_OTHERS = "settled_by_others"
    #: Money came back onto the card beyond anything an envelope charged here,
    #: and an envelope IS holding it. The tension is real and worth naming:
    #: that envelope's money is spendable, and it exists only as a credit on
    #: this card. Name the amount that came back, never the shortfall it left.
    REFUND_OUTRAN_ENVELOPE = "refund_outran_envelope"
    #: A month ended short, the shortfall rode onto this card — and onto at
    #: least one other. Funding that envelope cannot be aimed at this card:
    #: the shortfall is allocated across cards largest charge first, so partial
    #: funding shrinks the most-charged card's share and this row does not move
    #: (F8, measured: funding the envelope left -60 at -60; assigning to the
    #: card landed on 0 exactly). Say what happened; promise nothing.
    SETTLED_ELSEWHERE = "settled_elsewhere"
    #: A month ended short and the whole shortfall rode onto this card, so
    #: back-funding that month's envelope does retire it — the walk is
    #: recomputed from scratch on every request. The only state that may
    #: promise it.
    RIDE_UNFUNDED = "ride_unfunded"
    #: Payment ran past everything reserved, with NOTHING else present: no
    #: residual of any kind and no ride. A deliberate paydown out of money no
    #: envelope had set aside; it went straight to the balance. The only
    #: state that may quote `short_reserved` as "what you paid ahead" — with
    #: a second cause present, that figure includes the other cause's money.
    PAID_AHEAD = "paid_ahead"
    #: More than one thing put Set aside below zero, and none of them explains
    #: all of it. The row names what is present and quotes each served leg,
    #: and says nothing about how much of the shortfall is which: the reserve
    #: identity is bounds, not parts (`reserve_discrepancy`'s T2 is `<=`), so
    #: any split into "this much settle-up, this much paid ahead" would be an
    #: attribution rule — the same shape of confident wrong answer that
    #: labelled a two-thirds settle-up as overpayment. The legs panel is the
    #: whole picture; this points at it.
    MIXED = "mixed"
    #: Money was moved OUT of the card's envelope past what it held — a
    #: release, or a negative typed into Assigned, larger than the reserve.
    #: No payment happened and nothing came back onto the card: the money is
    #: in Ready to Assign (or wherever it was moved) and the envelope is
    #: simply overdrawn. T2's third term. It read `PAID_AHEAD` — "you have
    #: paid $200 more … the money has already left your account" — about
    #: money that had left nothing but this envelope.
    MOVED_OUT = "moved_out"


def riding_series[C, K](funding: CardFunding[C, K], card: K) -> dict[date, Decimal]:
    """Everything riding uncovered on a card, month by month — what a month
    ending short put there AND what an import brought — for the one reader
    that wants the total: the timeline, which draws the card's debt as it
    stood after each month. Every sentence elsewhere means the first part
    only and reads `riding_by_card` directly."""
    out: dict[date, Decimal] = {}
    for series in (
        funding.riding_by_card.get(card, {}),
        funding.imported_riding_by_card.get(card, {}),
    ):
        for month, amount in series.items():
            out[month] = out.get(month, ZERO) + amount
    return out


def ride_is_exclusive[C, K](
    floored_by_pair: dict[tuple[C, K], dict[date, Decimal]],
    card: K,
    through: date,
) -> bool:
    """Did every envelope that rode onto this card ride onto ONLY this card?

    This is the question `RIDE_UNFUNDED`'s promise stands on. "Fund that
    month's envelope and the ride disappears" is true when the envelope's
    whole shortfall is here, and false the moment it is shared: `allocate_capped`
    hands the shortfall out across that month's cards largest charge first, so
    money put into the envelope shrinks the most-charged card's ride, and a row
    being read about the other one does not move at all.

    Measured on the real walk before it was believed — one shared tab charging
    $300 on card A and $60 on card B, settled the next month on A. Doing
    nothing left card B at -60, and it does not clear itself. Funding the
    envelope $60, which is what the row told the user to do, left card B at
    -60: the $60 shrank card A's ride from 300 to 240. Only assigning $60 to
    card B landed on 0.

    An empty ride is NOT exclusive: there is nothing to promise about. This
    used to return True vacuously on the assumption that the caller had
    checked something was riding — but the caller checked `riding`, which
    then included an import's opening debt that never appears in these
    pairs, so an anchored card with a negative Set aside read `RIDE_UNFUNDED`
    and was told to fund a month that had never ended short.
    """
    mine = {
        (category, month)
        for (category, key), series in floored_by_pair.items()
        if key == card
        for month, amount in series.items()
        if month <= through and amount != ZERO
    }
    if not mine:
        return False
    return not any(
        key != card and (category, month) in mine
        for (category, key), series in floored_by_pair.items()
        for month, amount in series.items()
        if month <= through and amount != ZERO
    )


def residual_from[C, K](
    residual_by_pair: dict[tuple[C, K], dict[date, Decimal]],
    card: K,
    categories: Container[C],
    month: date,
) -> Decimal:
    """How much of this card's residual in `month` came from the given
    categories.

    One spelling of a reduction two callers need: the served state, to tell a
    settle-up from a refund an envelope kept, and the scenario checker that
    mirrors it. They were about to compute it separately, which is how one
    surface comes to call a household's bookkeeping a defect while the other
    calls it normal.

    One month, not a lifetime: a Set aside below zero is written off at the
    month's end, so the shortfall it is compared with is always this month's.
    """
    return sum(
        (
            series.get(month, ZERO)
            for (category, key), series in residual_by_pair.items()
            if key == card and category in categories
        ),
        ZERO,
    )


def set_aside_state(
    position: CardPosition,
    *,
    residual: Decimal,
    riding: Decimal,
    residual_from_ledgers: Decimal,
    ride_reaches_this_card: bool,
    released_out: Decimal = ZERO,
) -> SetAsideState:
    """Which situation a card's Set aside is in, from the served terms.

    Pure, and deliberately not keyed on `reserve_discrepancy`: that check's
    bounds are ALLOWANCES, so a card that has drifted furthest is exactly the
    one it stays silent about. This asks where the card stands, which is a
    different question from whether anything is wrong.

    Precedence, and why it is this order:

    1. `card_credit` first. It is the one state that is about the CARD rather
       than the envelope, and it is the only one "overpaid" describes.
    2. Then the four ways Set aside can be below zero, most specific first.
       Each needs a different response, and one label for all four is the
       defect this replaces.
    3. `over_reserved`, then everything else. `RIDE_UNFUNDED` therefore never
       fires on a positive Set aside: riding debt on a card that is holding
       money is Uncovered's business, and the remedy sentence would be
       answering a question nobody asked.

    `riding` is what months ending short put on this card — `riding_by_card`,
    never the import's opening debt (`imported_riding_by_card`). The two ride
    states promise that funding a month's envelope retires the ride; imported
    debt has no such month, and is retired only by assigning to the card.

    **`residual`, `residual_from_ledgers` and `released_out` are this month's
    figures.** A Set aside below zero is written off at the month's end, so a
    shortfall is always this month's, and a cause from an earlier month —
    already written off — must not explain it. `riding` stays a level: the
    write-off retires rides, so what is still riding is current.

    `released_out` is money moved out of the card's envelope this month. It
    is the one cause where no cash left the household and nothing came back
    onto the card, so the row must not say "you have paid".

    A **full** explanation, never a partial one: `residual_from_ledgers`,
    `residual` and `riding` must each cover the whole shortfall to claim it.
    Accepting part of one would let a real shortfall hide behind a
    household's bookkeeping — and, the other way, claiming the whole
    shortfall for the one cause that was checked last labelled a settle-up
    plus a small paydown as "you have paid $300 ahead" when $200 of it was
    somebody squaring up. `PAID_AHEAD` therefore requires that nothing else
    is present at all; anything partial is `MIXED`, which names the causes
    and attributes nothing.
    """
    if position.card_credit > ZERO:
        return SetAsideState.CARD_HOLDS_IT
    if position.short_reserved > ZERO:
        short = position.short_reserved
        if residual_from_ledgers >= short:
            return SetAsideState.SETTLED_BY_OTHERS
        if residual >= short:
            return SetAsideState.REFUND_OUTRAN_ENVELOPE
        # Symmetric with the two above: the ride must explain the WHOLE
        # shortfall to claim it. It used to fire on `riding > ZERO`, so a
        # $5 ride claimed a $805 shortfall and the row promised that funding
        # one month would retire it — leaving $800 short.
        if riding >= short:
            return (
                SetAsideState.RIDE_UNFUNDED
                if ride_reaches_this_card
                else SetAsideState.SETTLED_ELSEWHERE
            )
        if released_out >= short:
            return SetAsideState.MOVED_OUT
        if residual == ZERO and riding == ZERO and released_out == ZERO:
            return SetAsideState.PAID_AHEAD
        # Something is present and nothing covers it all. Say so; do not pick.
        return SetAsideState.MIXED
    if position.over_reserved > ZERO:
        return SetAsideState.SURPLUS
    return SetAsideState.FUNDED


def _allowance(*terms: Decimal) -> Decimal:
    """Capacity to explain a gap, from terms that are each allowed to be zero
    but never negative.

    Each term floors **on its own**, not after summing. `assigned` is a signed
    lifetime total and goes negative the moment someone moves more money back
    out of a card's envelope than they ever put in — ordinary
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
    opening_credit: Decimal = ZERO,
    written_off: Decimal = ZERO,
) -> Decimal:
    """0 when a card's reserve identity holds with all three bounds met;
    otherwise the largest amount by which one of them does not.

    The four terms are `card_position` — one implementation, read here and by
    the surface, so nothing gets a second opinion about what an over-reserve
    is. With `owed = -balance`:

        set_aside + uncovered == owed + over_reserved - short_reserved
                                 + card_credit

    **A zero here is not a clean bill of health.** Every bound below is an
    allowance, so a card whose reserve has travelled a long way from its
    balance for an accepted reason reports nothing. That is deliberate — but
    it means the surface must read `card_position` directly rather than
    treating silence here as "the number is sensible". Two real cards, one
    over-reserved several times over by assignments that never retired a ride
    and one below zero on a balance it still owed, sat inside these bounds for
    years.

    The equation is an algebraic identity given those definitions, so it
    catches nothing on its own. **The content is the three bounds**, and each
    one replaces a clause the old invariant used to excuse. Every right-hand
    side is an allowance — capacity to explain something — so every term on it
    floors at zero individually (`_allowance`); a bound written `L - R` is only
    sound while `R >= 0`, and `assigned` is signed:

    - **T1** `over_reserved <= (assigned - covered) + unclaimed_rows +
      opening_credit`. A reserve exceeds its debt only by money someone
      deliberately assigned to the card **and that has not already done its
      job**, by a row on the card the budget has no claim on, or — on an
      anchored budget — by a credit the card already held at B−1. Replaces
      "for a card with no assignments".

      The anchor-era term is on this bound for the same reason it is on T3,
      and leaving it off T3 alone was a hole: an opening credit does not STAY
      in `card_credit`. It converts to over-reserve the moment the card is
      used. A card imported holding 80 that then funds and spends 100 owes 20,
      not 100, because the credit absorbed the difference — so its envelope
      reserves 100 against a 20 debt and `over_reserved` reads exactly the 80
      the card came in with. With the allowance only on T3, every anchored
      card that arrived in credit reported that 80 as drift forever, from its
      first ordinary funded spend onward, and the integrity check said so.

      The allowance is the same size on both bounds and that does not
      double-count: `owed` floors at zero inside `card_position`, so
      `over_reserved` and `card_credit` are never both positive on one
      balance — and `worst` below is a `max`, never a sum.

      The subtraction is the whole content of this bound. With the plain
      lifetime `assigned`, the quantity that *caused* the drift and the
      quantity offered to *explain* it were the same number, so the further
      the reserve drifted the more thoroughly the check was satisfied — the
      same failure the old invariant's exclusion clause had, re-admitted as
      an allowance. An assignment that retired riding debt has been spent; it
      explains the debt it covered, not a reserve standing beyond it.

      Note `assigned - covered` is ONE term inside `_allowance`, not two.
      Flooring `covered` on its own would break the subtraction.
    - **T2** `short_reserved <= payments + residual_releases + released_out`,
      where `released_out` is the negative half of the lifetime assignment.
      A reserve goes negative only by paying the card more than was reserved,
      by an inflow beyond what its category ever had riding there, or by the
      user moving more money back out of the card's envelope than was ever
      put in — which the over-reserve note itself invites ("type a negative
      in Assigned"). The third term was missing: a release past the reserve
      reported its whole short-reserve as drift on a card where nothing was
      wrong — the same one-sided arithmetic as "The Watchman's Arithmetic",
      on the other bound. Replaces "and no inflows that predate their
      reservations".
    - **T3** `card_credit <= short_reserved + unclaimed_rows +
      opening_credit`. A credit balance on a card is either budget money,
      somebody else's, or — on an anchored budget — a credit the card already
      held at B−1, before any post-anchor leg existed to explain it. This is
      the one that catches a repayment landing where no category ever
      charged.

      **`opening_credit` is permanent and read live.** It never decays: the
      offset between a lifetime reserve that starts at the anchor and a
      balance that starts at B−1 is fixed for the life of the budget, so the
      allowance has to be too. And the caller computes it from the register
      rather than from a stored row, so editing or importing a pre-anchor card
      row moves it with no anchor rewrite. Both bounds are that much wider on
      such a card, for as long as it exists — `test_g`/`test_h` pin the size,
      and `ANCHORED_CREDIT_SPENT_DOWN` shows the shape.

    `assigned` is the *net* lifetime assignment to the card's own linked
    category — negative where more has been moved out than in, which is why it
    is floored rather than trusted to be positive. **On an anchored budget the
    caller folds the opening reserve into it**: YNAB's accumulated CCP
    position is a pre-anchor net assignment, and it enters T1 and T2 with
    exactly an assignment's signs — an opening the user later moves out
    appears in T2's `-assigned` term, an opening standing beyond the debt in
    T1's allowance. `opening_credit` is `max(0, balance at end of B−1)` —
    computed live from the register, not stored, so edits to pre-anchor rows
    stay coherent. `covered` is
    `CardFunding.covered_by_card` summed through the month: the part of those
    assignments that retired riding debt. `payments` are transfers from the
    budget's cash, `residual_releases` is `CardFunding.residual_by_card`
    summed for this card, and `unclaimed_rows` is
    `txn_filters.UNCLAIMED_CARD_ROW` — the signed net of card rows no term of
    the model claims, in both directions.

    **The write-off.** A month-end write-off is Ready to Assign putting money
    into the card's envelope, so callers fold it into `assigned` (T1 and T2
    read it with an assignment's signs) and its ride retirements are in
    `covered`. T3 names it separately: a card overpaid past its reserve holds
    a credit that `short_reserved` explained only until the write-off brought
    Set aside back to zero, so the written-off amount is what explains it
    after. Without the leg, a floor would report every overpaid month as
    drift — the "boundary floor ratchet" `TestReservationInvariant` exists to
    catch.

    **What this does not do.** All three bounds are consequences of the
    identity above, so they check the walk against itself, not against
    reality. What makes T1 bite now is that the identity only closes if
    assignments really do retire rides — a regression in the walk's step 5
    drives `covered` to zero and T1 goes quiet again, exactly as it did when
    the unclaimed term was widened in one sign only. The independent checks
    are the YNAB oracle (`integrations/ynab/parity.py`) and the closed-form
    test.
    """
    pos = card_position(set_aside, balance)
    worst = max(
        pos.over_reserved - _allowance(assigned - covered, unclaimed_rows, opening_credit),
        pos.short_reserved - _allowance(payments, residual_releases, -assigned),
        pos.card_credit
        - _allowance(pos.short_reserved, unclaimed_rows, opening_credit, written_off),
    )
    return worst if worst > ZERO else ZERO
