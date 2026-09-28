"""What the roadmap needs to know about a household's money.

A *concept* is one fact the Guide wants — how much emergency fund exists, is
any debt above 10%, does an employer match contributions. Detection answers
most of them from the budget; the user can overrule or extend any answer, and
some (an employer match) have no answer in a budget at all.

These definitions are the contract between three things: the detection
heuristics, the binding UI's picker, and the roadmap content on the frontend,
whose `SignalKey` union must stay in step with `CONCEPT_KEYS` here. Copy is
written for users, following the precedent set by
`igab.domain.account_types.BUILTIN_ACCOUNT_TYPES`.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from igab.domain.dates import month_end
from igab.domain.money import quantize_cents


@dataclass(frozen=True)
class Concept:
    key: str
    label: str
    #: How the answer reads.
    #:   'amount'  a sum of money (emergency fund, high-interest debt)
    #:   'rate'    a percentage (retirement contributions)
    #:   'boolean' a yes/no with no source in the budget (employer match)
    kind: str
    #: What the user may point this at when correcting a guess. Empty means
    #: the concept has nothing to bind — it is answered, not measured.
    binds_to: tuple[str, ...]
    #: Shown above the picker, explaining what the app is looking for.
    prompt: str
    #: Why a guess might be wrong, shown beside the override. Honest about the
    #: limits of the heuristic rather than pretending to certainty.
    caveat: str = ""
    #: Whether detection can attempt this at all.
    auto: bool = True
    #: Whether "I have this, elsewhere" makes sense. False for concepts where
    #: an outside answer is meaningless — you cannot hold debt "elsewhere" in
    #: a way that changes whether you should pay it down.
    allows_external: bool = True
    us_only: bool = False
    aliases: tuple[str, ...] = field(default=())


CONCEPTS: tuple[Concept, ...] = (
    Concept(
        key="budget_exists",
        label="A budget",
        kind="boolean",
        binds_to=(),
        prompt="Whether there is a budget to work from.",
        auto=True,
        allows_external=False,
    ),
    Concept(
        key="essential_expenses",
        label="Essential monthly spending",
        kind="amount",
        binds_to=("category",),
        prompt="Roughly what a lean month costs — what an emergency fund is measured against.",
        caveat=(
            "Taken from your average spending over the last 90 days, with yearly "
            "bills in Long-term expense categories spread over 12 months unless "
            "you turn that off in the reports. Tag the categories you could not do "
            "without as Essential and this narrows to them; point it at specific "
            "categories here to override that."
        ),
        allows_external=False,
    ),
    Concept(
        key="emergency_fund",
        label="Emergency fund",
        kind="amount",
        # Nothing to bind: the fund is chosen by the Emergency fund tag and the
        # account flag, which every report reads too (`services.emergency_fund`).
        # Only "kept elsewhere" is a Guide answer.
        binds_to=(),
        prompt="Money set aside for genuine surprises, that you could reach the same day.",
        caveat=(
            "Counts the envelopes you tag Emergency fund, the off-budget accounts you "
            "mark, and anything you keep elsewhere. Nothing is guessed."
        ),
        allows_external=True,
        aliases=("rainy day", "buffer"),
    ),
    Concept(
        key="employer_match",
        label="Employer match",
        kind="boolean",
        binds_to=(),
        prompt="Whether your employer adds money when you contribute to a retirement account.",
        caveat="Nothing in a budget can tell us this — it lives in your employment paperwork.",
        auto=False,
        allows_external=False,
        us_only=True,
    ),
    Concept(
        key="high_interest_debt",
        label="Debt at 10% APR or higher",
        kind="amount",
        binds_to=("liability",),
        prompt="Debts expensive enough that clearing them beats almost anything else.",
        caveat=(
            "Only debts with a known interest rate can be judged. A card with no rate "
            "recorded is listed separately rather than assumed cheap."
        ),
        allows_external=False,
    ),
    Concept(
        key="moderate_interest_debt",
        label="Debt between about 4% and 10%",
        kind="amount",
        binds_to=("liability",),
        prompt="Debts where paying down and investing instead are both defensible.",
        caveat="Mortgages are left out, as the roadmap does — say otherwise if yours belongs here.",
        allows_external=False,
    ),
    Concept(
        key="retirement_contributions",
        label="Retirement saving",
        kind="rate",
        binds_to=("account", "category"),
        prompt="What share of your income goes towards retirement.",
        caveat=(
            "We count money moved into off-budget investment accounts. Only you know "
            "which of those are for retirement, so this is worth checking — and a "
            "workplace plan IGAB never sees will not appear at all."
        ),
        us_only=False,
    ),
    Concept(
        key="hsa",
        label="Health savings account",
        kind="amount",
        binds_to=("account",),
        prompt="An investable HSA attached to a high-deductible health plan.",
        caveat="There is no reliable way to spot one, so this is yours to point at.",
        auto=False,
        us_only=True,
    ),
    Concept(
        key="college_savings",
        label="Education savings",
        kind="amount",
        binds_to=("account", "category"),
        prompt="Money set aside for a child's education — a 529 or similar.",
        caveat="There is no reliable way to spot one, so this is yours to point at.",
        auto=False,
        us_only=True,
    ),
)

CONCEPTS_BY_KEY: dict[str, Concept] = {c.key: c for c in CONCEPTS}
CONCEPT_KEYS = frozenset(CONCEPTS_BY_KEY)

#: Thresholds the roadmap states, in one place so the copy and the arithmetic
#: cannot disagree. These come from the source flowchart and are stable —
#: unlike contribution limits, which change yearly and are deliberately absent.
HIGH_INTEREST_APR = 10
MODERATE_INTEREST_APR = 4
RETIREMENT_TARGET_RATE = 15
STARTER_EMERGENCY_FUND = 1000
FULL_EMERGENCY_FUND_MONTHS_LOW = 3
FULL_EMERGENCY_FUND_MONTHS_HIGH = 6
#: How old a self-reported figure may be before the checkup asks, once and
#: quietly, whether it is still true. IGAB cannot refresh a number it was told,
#: so the age of the claim is part of the claim.
STALE_EXTERNAL_MONTHS = 12
#: How many COMPLETE months "what a lean month costs" averages — the Guide's
#: essential-expenses signal and through it the emergency-fund target, the
#: Overview card, the Essentials report and the Emergency Fund report all read
#: this one figure (`essentials_at`).
#:
#: It was the last ninety days ÷ 3, through today. A monthly bill moves a
#: rolling ninety days by a whole payment the day it enters and again the day
#: it leaves, so a household whose complete months sat between $3,700 and
#: $4,200 read anywhere from $3,100 to $4,900 over a year — the mortgage alone
#: jumped it by $750 overnight — and the emergency-fund target swung six times
#: that with it. Three complete months hold every monthly bill exactly three
#: times, whatever day it is.
ESSENTIALS_MONTHS = 3


#: Months a sinking fund's bills are spread over. A yearly bill is the reason
#: the tag exists, and a year is the one period every such bill recurs within.
#: Twelve complete months hold a yearly bill paid on the same date exactly
#: once.
SPREAD_MONTHS = 12


@dataclass(frozen=True)
class EssentialsMonthly:
    """What a lean month costs, both ways.

    `as_paid` is the three-complete-month average as the bills landed;
    `spread` swaps the sinking-fund bills in those months for a twelfth of the
    last twelve months'. Both are always served; `spread_on` (the budget's
    setting) says which one the targets, runway and reserve read — `monthly`.
    """

    as_paid: Decimal
    spread: Decimal
    spread_on: bool
    #: The first and last day of the complete months `as_paid` averages — so
    #: every surface can say which months it is quoting. None when there is
    #: no history to average yet.
    window_start: date | None = None
    window_end: date | None = None

    @property
    def monthly(self) -> Decimal:
        return self.spread if self.spread_on else self.as_paid


def trailing_average(
    totals: list[Decimal], index: int, window: int = ESSENTIALS_MONTHS, *, first_data: int = 0
) -> Decimal:
    """Mean of the `window` months ending at `index`, over what exists.

    Early months have less history behind them, and dividing three months of
    spending by three when only one has happened would halve the denominator
    and double the coverage — a chart that opens on a reassuring number it
    then walks back.

    `first_data` is the index of the first month the budget has any history
    for (`domain.dates.history_index`). Months before it are not months a
    household spent nothing — they are months the budget did not exist — and
    averaging their zeros in did exactly what the paragraph above warns against
    from the other direction: a young budget's chart opened at 6.0 months
    covered, because two thirds of its denominator was a period with no data.
    """
    start = max(first_data, index - window + 1)
    span = totals[start : index + 1]
    return quantize_cents(sum(span, Decimal("0")) / len(span)) if span else Decimal("0")


def spread_average(
    totals: list[Decimal], sinking: list[Decimal], index: int, *, first_data: int = 0
) -> Decimal:
    """A month's essentials figure with sinking-fund bills spread.

    `totals` and `sinking` are monthly magnitudes, oldest first; `sinking` is
    the part of each month's total filed to a sinking fund. The rest takes the
    trailing three-month average, cut at the history exactly as
    `trailing_average` is; the sinking part is the twelve months ending at
    `index` divided by twelve. A $2,400 yearly premium is $200 a month whether
    it was paid last month or eight months ago; as paid it is $800 a month for
    one quarter and nothing for the other three. With no sinking-fund rows the
    two agree to the cent.

    The twelve-month part is **not** cut at `first_data`: the months before the
    history hold zeros, and dividing by twelve anyway is what spreading means.
    **A budget younger than a year under-reads** it — a bill it has not seen yet
    is not in the sum — and that is the honest bound: dividing by the months
    that exist would turn one premium into a monthly bill of its full size.
    """
    rest = [t - s for t, s in zip(totals, sinking, strict=True)]
    year = sinking[max(0, index - SPREAD_MONTHS + 1) : index + 1]
    spread = sum(year, Decimal("0")) / SPREAD_MONTHS
    return quantize_cents(trailing_average(rest, index, first_data=first_data) + spread)


def essentials_at(
    months: list[date],
    totals: list[Decimal],
    sinking: list[Decimal],
    index: int,
    *,
    first_data: int = 0,
    spread_on: bool,
) -> EssentialsMonthly:
    """What a lean month costs as of the complete month at `index` — THE
    essentials figure, as paid and spread.

    One function for the headline and every point of a series: the Guide's
    target, the Overview card, the Essentials report and the Emergency Fund
    headline read it at the newest complete month, and the Emergency Fund
    chart reads it at each of its months. The headline used to be a rolling
    ninety days ÷ 3 beside a chart of three-complete-month averages, so the
    newest point and the card over it disagreed by design; now the card IS
    the newest point.

    `months` (first of each month), `totals` and `sinking` are complete months
    only, oldest first, the money as positive magnitudes. With no history at
    `index` (a budget whose history starts this month) both figures are zero
    and the window is None: nothing has been measured yet.
    """
    first = max(first_data, index - ESSENTIALS_MONTHS + 1)
    measured = 0 <= first <= index < len(months)
    return EssentialsMonthly(
        as_paid=trailing_average(totals, index, first_data=first_data),
        spread=spread_average(totals, sinking, index, first_data=first_data),
        spread_on=spread_on,
        window_start=months[first] if measured else None,
        window_end=month_end(months[index]) if measured else None,
    )


def emergency_fund_target(essentials_monthly: Decimal, months: int) -> Decimal:
    """`months` of essential spending, to the cent.

    The one place the roadmap's emergency-fund arithmetic lives: the signal's
    target, the checkup's money figures and the sizer all quote it.
    """
    return quantize_cents(essentials_monthly * months)


def starter_emergency_fund(essentials_monthly: Decimal | None) -> Decimal:
    """The starter cushion — the flat figure or one month of essentials,
    whichever is larger, as the roadmap step says. With no essentials figure
    the flat figure stands."""
    floor = Decimal(STARTER_EMERGENCY_FUND)
    if essentials_monthly is None or essentials_monthly <= 0:
        return floor
    return max(floor, emergency_fund_target(essentials_monthly, 1))


#: Kinds of debt the roadmap sets aside when asking about moderate-interest
#: debt. Matched against LiabilityService.resolve_type, which answers with an
#: account-type key for a managed liability and the stored liability_type for
#: an unmanaged one — 'mortgage' is spelt the same either way.
MORTGAGE_KINDS = frozenset({"mortgage"})

#: How a concept was answered. Order matters: see igab.guide.bindings.
BINDING_MODES = ("manual", "external", "dismissed", "answer")
