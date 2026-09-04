"""How a category's available balance carries from one month to the next.

The rule is a month-by-month simulation, not a running total, and the
difference is the zero floor between months: when a category ends a month
negative, that overspending is covered from To Be Assigned and the next month
starts at zero rather than inheriting the debt. Only the month being viewed
may show a negative available.

This lived only inside `BudgetService.get_category_balance`, and a second
caller that needed the same number — the Guide, deciding whether to tell
someone they have no emergency fund — summed assignments and activity over all
time instead. That answer is lower than the budget page's for any category
that has ever overspent and been covered, and it is permanently lower. Stating
it once here is what keeps a roadmap from arguing with the budget it reads.

Pure: takes the two series and the month, returns the number.
"""

from datetime import date
from decimal import Decimal

ZERO = Decimal("0")


def next_carryover(end_of_month: Decimal) -> Decimal:
    """What a month hands to the next one: its end balance, floored at zero.

    The floor *is* the write-off — a negative month was absorbed by To Be
    Assigned, so the next month starts fresh rather than inheriting the debt.

    One line, and it has a name because two walks apply it: this module's
    `monthly_end_balances` and `domain.cards.card_funding`, which runs the same
    simulation with card corrections folded into each month's activity. Written
    twice, the two series would drift, and the whole point of the card walk is
    that its answer and this one are the same rule.
    """
    return max(ZERO, end_of_month)


def monthly_end_balances(
    assignments_by_month: dict[date, Decimal],
    activity_by_month: dict[date, Decimal],
    *,
    opening: tuple[date, Decimal] | None = None,
) -> dict[date, Decimal]:
    """Each data month's raw end-of-month available, in one pass.

    The one loop of the simulation — `available_at` reads its answer out of
    this, and the card set-aside arithmetic (domain/cards.py) reads the
    negatives out of it to split a month's overspending by funding source.
    Values may be negative; the floor is applied *between* entries, so each
    value is what that month ended at before the next month floored it.

    `opening` is an import anchor: `(month B−1, YNAB's own Available then)`.
    The walk emits that raw value as B−1's entry (when non-zero), carries its
    *floored* value forward — the floor rule stays in `next_carryover`, its
    one home — and skips every data month at or before it. Truncation lives
    here, inside the domain, so no caller can apply the seed and forget the
    cut. `opening=None` is byte-for-byte today's walk; `domain.cards.
    card_funding` seeds its per-category carryover from the same rule, and a
    differential test holds the two to one answer.
    """
    out: dict[date, Decimal] = {}
    carryover = ZERO
    start_after: date | None = None
    if opening is not None:
        opening_month, opening_amount = opening
        if opening_amount != ZERO:
            out[opening_month] = opening_amount
        carryover = next_carryover(opening_amount)
        start_after = opening_month
    for m in sorted(set(assignments_by_month) | set(activity_by_month)):
        if start_after is not None and m <= start_after:
            continue
        end_of_month = (
            carryover + assignments_by_month.get(m, ZERO) + activity_by_month.get(m, ZERO)
        )
        out[m] = end_of_month
        # Floor into the next month; the month itself keeps its raw value.
        carryover = next_carryover(end_of_month)
    return out


def sum_through(series: dict[date, Decimal], month_start: date) -> Decimal:
    """A monthly series totalled through `month_start`, inclusive.

    Not the carryover rule — no floor — just "the months up to here". It has a
    name because six call sites spell it, and one of them spelling `<` where
    the others spell `<=` is an off-by-one-month nobody would see on screen.
    """
    return sum((v for m, v in series.items() if m <= month_start), ZERO)


def available_at(end_balances: dict[date, Decimal], month_start: date) -> Decimal:
    """Read one month's available out of a month-end series.

    Only the month with its own data may show negative. A later month starts
    from the floored carryover, because the overspend was absorbed by TBA.
    Months after `month_start` are ignored, so a caller holding the whole
    history — `domain.cards.card_funding`, which must compute every month to
    carry its reservations forward — can ask for any month without slicing
    first.
    """
    if month_start in end_balances:
        return end_balances[month_start]
    earlier = [m for m in end_balances if m < month_start]
    if not earlier:
        return ZERO
    return next_carryover(end_balances[max(earlier)])


def available_through(
    assignments_by_month: dict[date, Decimal],
    activity_by_month: dict[date, Decimal],
    month_start: date,
    *,
    opening: tuple[date, Decimal] | None = None,
) -> Decimal:
    """Available in `month_start`, simulating every month up to it.

    Both dicts are keyed by the first of the month. Months absent from both
    contribute nothing and are skipped — a gap in the calendar is not a month
    that zeroed the carryover. `opening` is the import anchor, applied by
    `monthly_end_balances`; a viewed month at or before the anchor month
    reads the anchor's own figure, not a re-derivation.
    """
    return available_at(
        monthly_end_balances(
            {m: v for m, v in assignments_by_month.items() if m <= month_start},
            {m: v for m, v in activity_by_month.items() if m <= month_start},
            opening=opening,
        ),
        month_start,
    )
