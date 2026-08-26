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
            "Taken from your average spending over the last 90 days. Tag the "
            "categories or payees you could not do without as Essential and this "
            "narrows to them; point it at specific categories here to override that."
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

#: Kinds of debt the roadmap sets aside when asking about moderate-interest
#: debt. Matched against LiabilityService.resolve_type, which answers with an
#: account-type key for a managed liability and the stored liability_type for
#: an unmanaged one — 'mortgage' is spelt the same either way.
MORTGAGE_KINDS = frozenset({"mortgage"})

#: How a concept was answered. Order matters: see igab.guide.bindings.
BINDING_MODES = ("manual", "external", "dismissed", "answer")
