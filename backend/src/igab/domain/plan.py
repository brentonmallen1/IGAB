"""Did an envelope's spending fit what it had? One answer for every
plan-vs-actual report.

**An envelope is judged by what it held, not by what one month assigned it**
(owner's call, 2026-09-28). A month's `funded` is what it carried in from the
month before — the budget page's carryover, floored by `carryover.
next_carryover` — plus what was assigned and moved in, less what was moved
out. What it had `left` is the budget page's Available, and the month was
over only when that went negative: the budget page's red, the overspending
Ready to Assign had to cover.

This replaced a month's plan judged alone, carryover ignored, which named the
most careful envelopes the worst habits. An envelope funded 600 in January
and spending 100 a month read "over" five months running and was flagged
chronic, unless someone had tagged it Long-term expense; 200 a month saved
toward a car read 1,200 "under plan"; and 1,000 assigned in February and
moved to a brokerage in March read 1,000 underspent, because March's plan
floored the transfer away, while the same transfer in February read 0.
Every one of those envelopes the budget page showed as fine.

**Money moved INTO an envelope funds it; money moved OUT unfunds it** — the
row's activity class decides which (`plan_effect`). A transfer from savings
that paid a Medical bill funded it as surely as an assignment; a principal
transfer out of a Mortgage envelope took money back out of the plan rather
than being left unspent. A REFUND is spending coming back, so it lowers spent.

**`left` is served, not re-walked.** It is `BudgetService.envelope_series`'
Available — the import anchor, the walk back before it and the card
corrections already applied — so this report and the budget page cannot
disagree about a balance. Where the budget page states none (a month before
an import whose history cannot reproduce it), the month is walked from the
ledger instead and says so (`estimated`).

**A span of months is its months walked in order** (`across_months`): what
it started with plus everything funded, less spent, plus what Ready to Assign
covered, is what it ended with. Its verdict is that coverage.

Pure: takes one month's figures and returns the verdict.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple

from igab.domain.activity_class import ActivityClass, counted_classes
from igab.domain.carryover import next_carryover, write_off

ZERO = Decimal("0")

#: How far negative an envelope must go before it is OVER. Both, not either:
#: a dollar, and a hundredth of what it was funded with. Without it a
#: mortgage paid from an envelope assigned a few cents short read "over"
#: three months running and was named a chronic overspender — on a real
#: budget, more than one chronic flag in five was rounding. The dollar floor
#: keeps a small envelope's cents quiet; the percentage keeps a large one's
#: rounding quiet. An envelope with nothing in it is over as soon as it is a
#: dollar short (1% of nothing is nothing).
OVER_BY_AT_LEAST = Decimal("1.00")
OVER_SHARE_AT_LEAST = Decimal("0.01")

#: "Chronic" is over in at least `CHRONIC_MONTHS` of the last
#: `CHRONIC_WINDOW` months the report reads — an envelope habitually run dry
#: rather than a month unlucky. Plan vs Spent serves the flag and the Guide's
#: checkup reads it (`guide.service.checkup`); neither decides it again.
CHRONIC_MONTHS = 3
CHRONIC_WINDOW = 6


@dataclass(frozen=True)
class EnvelopeOutcome:
    """One envelope over one month, or over a span of them (`across_months`).

    The identities it keeps: a month's `funded - spent + other == left`, the
    budget page's Available, negative when overspent; a span's
    `funded - spent + other + overspent == left`, floored — Ready to Assign
    covered each month's negative, and that is `overspent`.
    """

    #: What it started with: the month before's Available, floored. None where
    #: the budget page states no figure for the month before, counted as zero.
    carried_in: Decimal | None
    #: `carried_in + assigned + moved_in - moved_out`.
    funded: Decimal
    #: Net of refunds; negative only when refunds beat the spending.
    spent: Decimal
    #: `left - (funded - spent)`: what the budget page's Available counts and
    #: the plan ledger does not — a pending row, a starting balance filed to
    #: the envelope, a card refund repaying uncovered debt. Deliberate, and
    #: bounded by `test_plan_vs_spent_report`'s differential test: an
    #: ordinary envelope's is zero.
    other: Decimal
    #: The budget page's Available at the end: negative when the envelope was
    #: overspent. A span's is floored, as the next month would carry it.
    left: Decimal
    #: What Ready to Assign covered: the negative `left` a month ended at, as
    #: a positive amount (`carryover.write_off`); a span's is its months'.
    overspent: Decimal
    #: Overspent by at least `OVER_BY_AT_LEAST` and `OVER_SHARE_AT_LEAST` of
    #: what it was funded with — the one meaning of "over" the matrix tint,
    #: the chronic count and the Total column's verdict all read.
    over: bool
    #: `left` was walked from the ledger because the budget page states no
    #: figure for this month (before an import it cannot walk back through).
    estimated: bool = False


def _is_over(overspent: Decimal, funded: Decimal) -> bool:
    base = max(funded, ZERO)
    return overspent >= OVER_BY_AT_LEAST and overspent >= base * OVER_SHARE_AT_LEAST


def envelope_outcome(
    *,
    carried_in: Decimal | None,
    assigned: Decimal,
    moved_in: Decimal,
    moved_out: Decimal,
    spent: Decimal,
    left: Decimal | None,
) -> EnvelopeOutcome:
    """The verdict for one envelope over one month.

    `carried_in` is the month before's Available floored (None: unknown,
    counted as zero); `assigned`, `moved_in`, `moved_out` and `spent` the
    plan ledger's; `left` the budget page's Available this month — None where
    it states none, and then the month is walked from the ledger.

    All four movements are required: a caller that forgot `moved_out` would
    report a debt-paying envelope as holding its whole payment.
    """
    funded = (carried_in or ZERO) + assigned + moved_in - moved_out
    walked = funded - spent
    estimated = left is None
    end = walked if left is None else left
    overspent = write_off(end)
    return EnvelopeOutcome(
        carried_in=carried_in,
        funded=funded,
        spent=spent,
        other=end - walked,
        left=end,
        overspent=overspent,
        over=_is_over(overspent, funded),
        estimated=estimated,
    )


def across_months(outcomes: Sequence[EnvelopeOutcome]) -> EnvelopeOutcome:
    """One envelope's months, oldest first, as one span: what the first
    carried in plus every month's funding, the spending and `other` summed,
    Ready to Assign's coverage summed, and the last month's Available floored
    as the next month would carry it.

    Not the months' `funded` summed — each already counts the one before's
    leftover, so a 600 envelope spending 100 a month would read funded 2,100
    over six months. And not a floor over the span's arithmetic either: a
    month that went negative was covered that month, which is `overspent`.
    """
    if not outcomes:
        return EnvelopeOutcome(
            carried_in=ZERO,
            funded=ZERO,
            spent=ZERO,
            other=ZERO,
            left=ZERO,
            overspent=ZERO,
            over=False,
        )
    first = outcomes[0]
    funded = sum((o.funded - (o.carried_in or ZERO) for o in outcomes), first.carried_in or ZERO)
    overspent = sum((o.overspent for o in outcomes), ZERO)
    return EnvelopeOutcome(
        carried_in=first.carried_in,
        funded=funded,
        spent=sum((o.spent for o in outcomes), ZERO),
        other=sum((o.other for o in outcomes), ZERO),
        left=next_carryover(outcomes[-1].left),
        overspent=overspent,
        over=_is_over(overspent, funded),
        estimated=any(o.estimated for o in outcomes),
    )


def is_chronic(months_over_recently: int) -> bool:
    """Whether an envelope is chronically overspent, given how many of the
    last `CHRONIC_WINDOW` months it went negative in.

    No exemption by tag. A sinking fund used to need one — judged by its
    monthly assignment, the month its bill landed was "over" — but judged by
    what it held, paying the bill it saved for leaves it at zero, not below.
    One that does go negative month after month is overspent, tagged or not.
    """
    return months_over_recently >= CHRONIC_MONTHS


class PlanEffect(NamedTuple):
    """What one row (or one bucket of like rows) does to a plan report."""

    #: Added to spent: an outflow positive, a refund negative.
    spent: Decimal
    #: Added to the plan: money moved into the envelope.
    moved_in: Decimal
    #: Taken off the plan: money moved out of the envelope that is not spent.
    #: Non-negative, like `moved_in`.
    moved_out: Decimal


NO_EFFECT = PlanEffect(ZERO, ZERO, ZERO)


def plan_effect(amount: Decimal, cls: str, *, savings_envelope: bool) -> PlanEffect:
    """What a row filed to a planned envelope (`txn_filters.PLAN_LEDGER_ROW`)
    does to that envelope's plan report — the one statement of it. Every
    Plan vs Spent figure, Category History's Spent, Volatility and
    Anomalies read it.

    `amount` is signed (outflow negative); `cls` the row's `ACTIVITY_CLASS`;
    `savings_envelope` whether its category is a savings category
    (`category_filters.IS_SAVINGS_CATEGORY`). Linear in `amount`, so a bucket
    of rows sharing all three facts may be passed as its sum.

    - **Spending, either sign, is spent.** A refund is spending coming back,
      so it lowers spent — the budget page nets it, and so does every other
      spending figure. It used to be dropped, which drew a returned purchase
      as the whole purchase.
    - **Money leaving a savings envelope is spent, whatever its class.** The
      household planned that money to leave; see
      `activity_class.PLANNED_SPEND_TAG_KEYS` and #182 for the phantom
      underspend counting it as nothing made. This is the only statement of
      that exception — `money_moves.counts_as_planned_spend_by_tag` asks it
      here rather than restating it.
    - **A starting balance does nothing.** It is where an account's counting
      begins, not money that moved, in either direction.
    - **Anything else arriving funds the envelope**: a transfer from
      savings, a deposit filed to it, a loan draw spent through it — exactly
      as an assignment does (`envelope_outcome`'s `funded`).
    - **Anything else leaving unfunds it**: a transfer to a brokerage
      out of an untagged envelope, a principal payment from an envelope not
      tagged Debt principal. It is not spent — it is saving, or paying down
      a debt, which no spending figure counts — but it was not left unspent
      either. It used to do nothing, so the envelope read underspent by the
      whole transfer.
    """
    if cls in counted_classes():
        return PlanEffect(spent=-amount, moved_in=ZERO, moved_out=ZERO)
    if cls == ActivityClass.OPENING_BALANCE.value:
        return NO_EFFECT
    if amount < ZERO:
        if savings_envelope:
            return PlanEffect(spent=-amount, moved_in=ZERO, moved_out=ZERO)
        return PlanEffect(spent=ZERO, moved_in=ZERO, moved_out=-amount)
    if amount > ZERO:
        return PlanEffect(spent=ZERO, moved_in=amount, moved_out=ZERO)
    return NO_EFFECT
