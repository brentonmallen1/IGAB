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

from igab.domain.dates import trailing_start
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
        binds_to=("category", "account"),
        prompt="Money set aside for genuine surprises, that you could reach the same day.",
        caveat=(
            "We look for a savings-tagged category or account whose name mentions an "
            "emergency, a rainy day or a buffer. If yours is named something else — or "
            "lives at another bank — say so and we will use that instead."
        ),
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
#: How far back "what a lean month costs" looks — the Guide's essentials
#: signal and the Overview's essentials card share it, so the emergency-fund
#: target and the card can never quote different months.
ESSENTIALS_WINDOW_DAYS = 90
#: The essentials window said in months: what its total is divided by, and how
#: many months a monthly series averages for the same figure.
TRAILING_MONTHS = 3


def essentials_since(today: date) -> date:
    """The first day of the essentials window: `ESSENTIALS_WINDOW_DAYS` days
    ending today, both included. It was `today - 90` in the Guide and the
    report alike — 91 days beside the Overview's 90-day burn."""
    return trailing_start(today, ESSENTIALS_WINDOW_DAYS)


def essentials_per_month(window_total: Decimal) -> Decimal:
    """A total over the essentials window as a monthly figure — ninety days
    is three months. The Guide's target and the Overview card each divided
    for themselves."""
    return quantize_cents(abs(window_total) / TRAILING_MONTHS)


#: Months a sinking fund's bills are spread over. A yearly bill is the reason
#: the tag exists, and a year is the one period every such bill recurs within.
SPREAD_MONTHS = 12
#: How far back the sinking-fund part of the essentials figure looks: 365 days
#: ending today, both included, through the same `trailing_start` the 90-day
#: window uses — so the two windows end on the same day and are spelled one
#: way. Days rather than calendar months for the same reason the 90-day window
#: is days: it slides daily instead of jumping on the 1st. A yearly bill paid on
#: the same date each year lands in it exactly once — last year's payment is
#: day 366.
SINKING_WINDOW_DAYS = 365


def sinking_since(today: date) -> date:
    """The first day of the sinking-fund window: `SINKING_WINDOW_DAYS` days
    ending today, both included."""
    return trailing_start(today, SINKING_WINDOW_DAYS)


@dataclass(frozen=True)
class EssentialsWindows:
    """Signed sums of essential spending (outflows are negative).

    `recent` is every essential row over the 90-day window; `recent_sinking`
    is the part of it filed to a sinking fund; `year_sinking` is sinking-fund
    rows over the 365-day window.
    """

    recent: Decimal
    recent_sinking: Decimal
    year_sinking: Decimal


@dataclass(frozen=True)
class EssentialsMonthly:
    """What a lean month costs, both ways.

    `as_paid` is the 90-day figure as the bills landed; `spread` swaps the
    sinking-fund bills in those 90 days for a twelfth of the year's. Both are
    always served; `spread_on` (the budget's setting) says which one the
    targets, runway and reserve read — `monthly`.
    """

    as_paid: Decimal
    spread: Decimal
    spread_on: bool

    @property
    def monthly(self) -> Decimal:
        return self.spread if self.spread_on else self.as_paid


def essentials_monthly(windows: EssentialsWindows, *, spread_on: bool) -> EssentialsMonthly:
    """The essentials figure as paid and spread.

    As paid: the 90-day total ÷ 3 (`essentials_per_month`). Spread: the
    non-sinking part of the 90 days ÷ 3, plus the year's sinking-fund bills ÷
    12. A $2,400 yearly premium is $200 a month whether it was paid last week
    or eight months ago; as paid it is $800 a month for one quarter and nothing
    for the other three. With no sinking-fund rows the two agree to the cent.

    **A budget younger than a year under-reads** the spread part: a bill it has
    not seen yet is not in the sum, and the divisor is twelve regardless. That
    is the honest bound — dividing by the months that exist would turn one
    premium into a monthly bill of its full size.
    """
    non_sinking = (windows.recent - windows.recent_sinking) / TRAILING_MONTHS
    spread = non_sinking + windows.year_sinking / SPREAD_MONTHS
    return EssentialsMonthly(
        as_paid=essentials_per_month(windows.recent),
        spread=quantize_cents(abs(spread)),
        spread_on=spread_on,
    )


def trailing_average(
    totals: list[Decimal], index: int, window: int = TRAILING_MONTHS, *, first_data: int = 0
) -> Decimal:
    """Mean of the `window` months ending at `index`, over what exists.

    Early months have less history behind them, and dividing three months of
    spending by three when only one has happened would halve the denominator
    and double the coverage — a chart that opens on a reassuring number it
    then walks back.

    `first_data` is the index of the first month the budget has any history
    for (`emergency_coverage.history_index`). Months before it are not months a
    household spent nothing — they are months the budget did not exist — and
    averaging their zeros in did exactly what the paragraph above warns against
    from the other direction: a young budget's chart opened at 6.0 months of
    runway, because two thirds of its denominator was a period with no data.

    **The one deliberate divergence.** The headline (the served essentials
    figure) is the Guide's, 90 days divided by three whatever the budget's
    age. For a budget with under three complete months of history, the newest
    point here divides by the months that exist and the headline still by
    three, so the two differ — by at most a factor of three, and only until the
    third complete month. Pinned in `test_emergency_coverage.py`.
    """
    start = max(first_data, index - window + 1)
    span = totals[start : index + 1]
    return quantize_cents(sum(span, Decimal("0")) / len(span)) if span else Decimal("0")


def spread_average(
    totals: list[Decimal], sinking: list[Decimal], index: int, *, first_data: int = 0
) -> Decimal:
    """A month's essentials denominator with sinking-fund bills spread.

    `totals` and `sinking` are monthly magnitudes, oldest first; `sinking` is
    the part of each month's total filed to a sinking fund. The rest takes the
    trailing three-month average, cut at the history exactly as
    `trailing_average` is; the sinking part is the twelve months ending at
    `index` divided by twelve — the month-shaped twin of `essentials_monthly`.

    The twelve-month part is **not** cut at `first_data`: the months before the
    history hold zeros, and dividing by twelve anyway is what spreading means.
    The same bound as the headline — a budget younger than a year under-reads
    bills it has not seen.
    """
    rest = [t - s for t, s in zip(totals, sinking, strict=True)]
    year = sinking[max(0, index - SPREAD_MONTHS + 1) : index + 1]
    spread = sum(year, Decimal("0")) / SPREAD_MONTHS
    return quantize_cents(trailing_average(rest, index, first_data=first_data) + spread)


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
