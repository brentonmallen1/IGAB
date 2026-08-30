"""What a card asks for this month.

A minimum payment is a **rule**, not a number. Card issuers overwhelmingly
charge a percentage of the balance with a dollar floor — often "2% or $35,
whichever is greater", sometimes "1% plus this month's interest". Storing the
number a statement happened to show freezes it at one balance, so every
projection built on it drifts the moment the balance moves: a payoff date that
is too optimistic on the way down, and an interest total that is too small.

That distinction is the whole point of this module, and it is also why the
projections it feeds change character. A fixed payment retires a debt on a
schedule. A percentage of a falling balance falls with it, so the debt takes
longer and costs more — and a pure percentage rule with no floor never clears
at all, which the schedule reports honestly rather than looping.

Pure: numbers in, a number out. The rule is built from columns in exactly one
place (``LiabilityService.minimum_payment_rule``), and evaluated here.
"""

from dataclasses import dataclass
from decimal import Decimal

from igab.domain.money import quantize_cents

ZERO = Decimal("0")

FIXED = "fixed"
PERCENT_OF_BALANCE = "percent_of_balance"

#: The kinds a rule can be. Everything already entered is `fixed`, and stays
#: that way: the migration defaults every existing row to it, so no projection
#: anyone has already seen changes.
KINDS = (FIXED, PERCENT_OF_BALANCE)


@dataclass(frozen=True)
class MinimumPaymentRule:
    """How much this debt asks for, given what is owed.

    ``usable`` is what every caller should ask before projecting anything: an
    incomplete rule must leave a projection blank rather than reporting a
    confident zero. That contract is the one
    ``test_liability_terms_optional.py`` has pinned across seventeen cases
    since long before this rule existed.
    """

    kind: str = FIXED
    #: The whole payment, for `fixed`.
    amount: Decimal | None = None
    #: Percent of the balance, e.g. Decimal("2") for 2%.
    percent: Decimal | None = None
    #: The "or $35, whichever is greater" half. Without it a percentage rule
    #: asymptotes and the debt never clears — see the module docstring.
    floor: Decimal | None = None
    #: Issuers that charge a slice of principal *plus* the month's interest.
    plus_interest: bool = False

    @property
    def usable(self) -> bool:
        if self.kind == FIXED:
            return self.amount is not None and self.amount > ZERO
        if self.kind == PERCENT_OF_BALANCE:
            # A percent with no floor is not merely imprecise, it is a rule
            # under which the debt never ends. Treated as incomplete so the
            # UI asks for the floor rather than drawing a curve to infinity.
            return (
                self.percent is not None
                and self.percent > ZERO
                and self.floor is not None
                and self.floor > ZERO
            )
        return False

    def due(self, balance: Decimal, monthly_interest: Decimal = ZERO) -> Decimal:
        """What the rule asks for at this balance — the scheduling answer.

        Deliberately **not** capped at what is owed. In a payoff cascade the
        gap between what a debt asks for and what it can absorb is money the
        person is already spending, and it rolls on to the next debt that
        month. Capping here would swallow it, and a $5 balance against a $100
        minimum would stop freeing $95.

        The final-payment clamp lives where it always did, in
        ``amortization._month_step``, which holds principal to the balance so
        the principal column sums to the starting balance exactly.

        Returns zero for an unusable rule. Callers gate on ``usable`` first —
        the zero is a floor for arithmetic, not an answer.
        """
        if not self.usable:
            return ZERO
        balance = quantize_cents(balance)
        if balance <= ZERO:
            return ZERO

        if self.kind == FIXED:
            return quantize_cents(self.amount or ZERO)

        percent = self.percent or ZERO
        due = quantize_cents(balance * percent / Decimal("100"))
        if self.plus_interest:
            due += quantize_cents(monthly_interest)
        return quantize_cents(max(due, self.floor or ZERO))

    def billed(self, balance: Decimal, monthly_interest: Decimal = ZERO) -> Decimal:
        """What the issuer actually asks for — the display answer.

        The same figure as :meth:`due`, capped at what would clear the debt:
        nobody is billed $35 against a $12 balance. This is what the served
        "minimum due this month" field carries, so the number on screen is a
        number someone could be asked to pay.

        The cap is balance **plus** this month's interest, because that is
        what clearing it costs.
        """
        balance = quantize_cents(balance)
        if balance <= ZERO:
            return ZERO
        payoff = balance + quantize_cents(monthly_interest)
        return min(self.due(balance, monthly_interest), payoff)


def fixed(amount: Decimal | None) -> MinimumPaymentRule:
    """The rule every liability had before rules existed."""
    return MinimumPaymentRule(kind=FIXED, amount=amount)


def as_rule(payment: "Decimal | MinimumPaymentRule") -> MinimumPaymentRule:
    """A scalar payment, seen as the rule it always was.

    This is what lets the amortization loop take either without growing a
    second schedule beside the first — two implementations of amortization,
    one of which would be the tested one.
    """
    if isinstance(payment, MinimumPaymentRule):
        return payment
    return fixed(payment)
