"""The rows a plan report counts as spent, as a WHERE clause — for the drill
that opens one of its figures.

Plan vs Spent, Volatility and Anomalies all read
`services.plan_ledger`, whose "spent" is `domain.plan.plan_effect` over
`PLAN_LEDGER_ROW`: spending either way (a refund lowers it) and anything
leaving a Savings envelope. Their drills listed `direction=outflow` rows of
the category instead, so a refund-heavy month opened a list totalling more
than its figure, a savings envelope's transfer out was missing from a list
whose figure counted it, and a brokerage transfer out of an untagged envelope
— moved out, never spent — was listed as if it had been.

**Derived, not restated.** `plan_effect` depends on three facts of a row — the
sign of its amount, its activity class, and whether its envelope is a savings
category — and each has finitely many values. So the predicate is built by
asking `plan_effect` about every combination and OR-ing the ones it counts as
spent. A change to the rule changes the drill with it; there is no second
statement to keep in step.

Here rather than in `txn_filters` because it reads `ACTIVITY_CLASS`, which is
built from that module's constants, and rather than in `domain.activity_class`
because `domain.plan` already imports that module.
"""

from decimal import Decimal

from sqlalchemy import ColumnElement, and_, false, not_, or_

from igab.db.models import Transaction
from igab.domain.activity_class import ACTIVITY_CLASS, ActivityClass
from igab.domain.plan import plan_effect
from igab.repositories.category_filters import IS_SAVINGS_CATEGORY
from igab.repositories.txn_filters import PLAN_LEDGER_ROW, row_category

_IN_SAVINGS_ENVELOPE = row_category(IS_SAVINGS_CATEGORY)


def _spent_classes(sign: Decimal, savings_envelope: bool) -> list[str]:
    """The classes whose rows of this sign, in this kind of envelope,
    `plan_effect` counts as spent."""
    return sorted(
        c.value
        for c in ActivityClass
        if plan_effect(sign, c.value, savings_envelope=savings_envelope).spent != 0
    )


def _spent_predicate() -> ColumnElement[bool]:
    arms = []
    for sign, side in (
        (Decimal("-1"), Transaction.amount < 0),
        (Decimal("1"), Transaction.amount > 0),
    ):
        plain = _spent_classes(sign, savings_envelope=False)
        savings = _spent_classes(sign, savings_envelope=True)
        if plain == savings:
            if plain:
                arms.append(and_(side, ACTIVITY_CLASS.in_(plain)))
            continue
        if plain:
            arms.append(and_(side, not_(_IN_SAVINGS_ENVELOPE), ACTIVITY_CLASS.in_(plain)))
        if savings:
            arms.append(and_(side, _IN_SAVINGS_ENVELOPE, ACTIVITY_CLASS.in_(savings)))
    return and_(PLAN_LEDGER_ROW, or_(*arms) if arms else false())


#: A row whose amount the plan ledger counts in `spent` — the rows behind every
#: plan-family Spent figure, and nothing else. The caller must apply
#: `apply_class_joins` (it reads `ACTIVITY_CLASS`).
PLAN_SPENT_ROW = _spent_predicate()
