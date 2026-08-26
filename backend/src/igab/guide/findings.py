"""The checkup: metrics against stated targets, and the findings worth a look.

Pure — takes the signals payload and a handful of report figures, returns
rows. No I/O, so every threshold here is a one-line test.

Two rules shape the whole module:

- **No composite score.** Each metric stands on its own against the target the
  roadmap states. A single "72/100" would imply a precision nothing here can
  support.
- **Unknown is not zero.** A concept whose `met` is None — detection could not
  tell, or the user dismissed it — never produces a finding. Guessing that
  someone has no emergency fund is worse than admitting we cannot see one.

Ranking is data: `RULES` is a tuple in severity order, and `evaluate` sorts by
that rank. Adding a finding kind means adding a row, not a branch.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from igab.domain.dates import add_months
from igab.domain.money import quantize_cents
from igab.guide.concepts import (
    FULL_EMERGENCY_FUND_MONTHS_HIGH,
    FULL_EMERGENCY_FUND_MONTHS_LOW,
    HIGH_INTEREST_APR,
    MODERATE_INTEREST_APR,
    RETIREMENT_TARGET_RATE,
    STALE_EXTERNAL_MONTHS,
    STARTER_EMERGENCY_FUND,
)

FindingKind = Literal[
    "high_interest_debt",
    "ef_below_starter",
    "chronic_overspend",
    "ef_below_full",
    "moderate_debt",
    "retirement_below_target",
    "stale_external",
    "unknown_rates",
]

Unit = Literal["money", "months", "percent", "count"]

STARTER = Decimal(STARTER_EMERGENCY_FUND)


@dataclass(frozen=True)
class CheckupInputs:
    """Everything a checkup reads, gathered by the service in one pass."""

    #: `GuideService.signals()["concepts"]`, keyed by concept key.
    signals: Mapping[str, Mapping[str, Any]]
    essentials_monthly: Decimal | None
    chronic_count: int
    chronic_names: list[str]
    #: Categories with a target that Fill Underfunded would leave alone, and
    #: how many carry a target at all.
    funded: int
    with_targets: int
    unknown_rate_names: list[str]
    today: date


@dataclass(frozen=True)
class Finding:
    kind: FindingKind
    rank: int
    concept_key: str | None
    #: A short clause, no figures — the client formats `value` in the budget's
    #: currency and composes the line.
    title: str
    detail: str
    value: Decimal | None = None
    target: Decimal | None = None
    names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    value: Decimal | None
    target: Decimal | None
    unit: Unit
    detail: str
    #: Which finding kinds this row is the home of, so the client can mark it
    #: when one of them fired.
    finding_kinds: list[str] = field(default_factory=list)
    #: A report tab that shows the working, when one exists.
    report: str | None = None


def _sig(inputs: CheckupInputs, key: str) -> Mapping[str, Any]:
    return inputs.signals.get(key, {})


def _unmet(sig: Mapping[str, Any]) -> bool:
    """Tracked, detected, and short of its target — the only shape that speaks."""
    return bool(sig.get("tracked")) and sig.get("met") is False


# ── the rules ────────────────────────────────────────────────────────────────


def _high_interest(inputs: CheckupInputs) -> list[Finding]:
    sig = _sig(inputs, "high_interest_debt")
    if not _unmet(sig):
        return []
    return [
        Finding(
            kind="high_interest_debt",
            rank=1,
            concept_key="high_interest_debt",
            title=f"Debt at {HIGH_INTEREST_APR}% APR or higher",
            detail="The roadmap clears this before almost anything else.",
            value=sig.get("value"),
            target=Decimal("0"),
        )
    ]


def _ef_below_starter(inputs: CheckupInputs) -> list[Finding]:
    sig = _sig(inputs, "emergency_fund")
    value = sig.get("value")
    if not sig.get("tracked") or value is None or value >= STARTER:
        return []
    return [
        Finding(
            kind="ef_below_starter",
            rank=2,
            concept_key="emergency_fund",
            title="Emergency fund is below the starter amount",
            detail="One small cushion first, before anything else on the roadmap.",
            value=value,
            target=STARTER,
        )
    ]


def _chronic(inputs: CheckupInputs) -> list[Finding]:
    if inputs.chronic_count <= 0:
        return []
    return [
        Finding(
            kind="chronic_overspend",
            rank=3,
            concept_key=None,
            title="Categories overspent month after month",
            detail="Chronic overspending pulls from everything else you funded.",
            value=Decimal(inputs.chronic_count),
            target=Decimal("0"),
            names=list(inputs.chronic_names),
        )
    ]


def _ef_below_full(inputs: CheckupInputs) -> list[Finding]:
    sig = _sig(inputs, "emergency_fund")
    value = sig.get("value")
    if not _unmet(sig) or value is None or value < STARTER:
        return []
    return [
        Finding(
            kind="ef_below_full",
            rank=4,
            concept_key="emergency_fund",
            title="Emergency fund covers less than three months",
            detail=(
                f"The roadmap suggests {FULL_EMERGENCY_FUND_MONTHS_LOW}–"
                f"{FULL_EMERGENCY_FUND_MONTHS_HIGH} months of essential spending."
            ),
            value=value,
            target=sig.get("target"),
        )
    ]


def _moderate(inputs: CheckupInputs) -> list[Finding]:
    sig = _sig(inputs, "moderate_interest_debt")
    if not _unmet(sig):
        return []
    return [
        Finding(
            kind="moderate_debt",
            rank=5,
            concept_key="moderate_interest_debt",
            title=f"Debt between {MODERATE_INTEREST_APR}% and {HIGH_INTEREST_APR}% APR",
            detail="Paying it down and investing instead are both defensible here.",
            value=sig.get("value"),
            target=Decimal("0"),
        )
    ]


def _retirement(inputs: CheckupInputs) -> list[Finding]:
    sig = _sig(inputs, "retirement_contributions")
    if not _unmet(sig):
        return []
    return [
        Finding(
            kind="retirement_below_target",
            rank=6,
            concept_key="retirement_contributions",
            title=f"Retirement saving is below {RETIREMENT_TARGET_RATE}% of income",
            detail=(
                "Counting only what IGAB can see — a workplace plan it never sees will not appear."
            ),
            value=sig.get("value"),
            target=Decimal(RETIREMENT_TARGET_RATE),
        )
    ]


def _stale_external(inputs: CheckupInputs) -> list[Finding]:
    cutoff = add_months(inputs.today, -STALE_EXTERNAL_MONTHS)
    out: list[Finding] = []
    for key, sig in inputs.signals.items():
        as_of = sig.get("external_as_of")
        if as_of is None or as_of > cutoff:
            continue
        out.append(
            Finding(
                kind="stale_external",
                rank=7,
                concept_key=key,
                title="A figure you told us is a year old",
                detail="IGAB cannot refresh a number it was told. Is it still right?",
                value=sig.get("external_value"),
            )
        )
    return out


def _unknown_rates(inputs: CheckupInputs) -> list[Finding]:
    if not inputs.unknown_rate_names:
        return []
    return [
        Finding(
            kind="unknown_rates",
            rank=8,
            concept_key="high_interest_debt",
            title="Debts with no interest rate on record",
            detail="Add the rate and the roadmap can place them.",
            value=Decimal(len(inputs.unknown_rate_names)),
            names=list(inputs.unknown_rate_names),
        )
    ]


Rule = tuple[FindingKind, int, Callable[[CheckupInputs], list[Finding]]]

#: Severity order. The rank is what `evaluate` sorts by; the kind is here so
#: the table reads as the rule it is.
RULES: tuple[Rule, ...] = (
    ("high_interest_debt", 1, _high_interest),
    ("ef_below_starter", 2, _ef_below_starter),
    ("chronic_overspend", 3, _chronic),
    ("ef_below_full", 4, _ef_below_full),
    ("moderate_debt", 5, _moderate),
    ("retirement_below_target", 6, _retirement),
    ("stale_external", 7, _stale_external),
    ("unknown_rates", 8, _unknown_rates),
)


def evaluate(inputs: CheckupInputs) -> list[Finding]:
    """Every finding that fires, most severe first. All of them — the client
    decides how many to show, and the step markers need every kind."""
    found: list[Finding] = []
    for _kind, _rank, rule in RULES:
        found.extend(rule(inputs))
    return sorted(found, key=lambda f: (f.rank, f.concept_key or "", f.title))


# ── the metrics ──────────────────────────────────────────────────────────────


def _ef_months(value: Decimal | None, essentials: Decimal | None) -> Decimal | None:
    if value is None or not essentials or essentials <= 0:
        return None
    return quantize_cents(value / essentials)


def metrics(inputs: CheckupInputs) -> list[Metric]:
    """The checkup tab's rows. Each one says where its number came from."""
    ef = _sig(inputs, "emergency_fund")
    high = _sig(inputs, "high_interest_debt")
    moderate = _sig(inputs, "moderate_interest_debt")
    retirement = _sig(inputs, "retirement_contributions")
    rows: list[Metric] = []

    months = _ef_months(ef.get("value"), inputs.essentials_monthly)
    if months is not None:
        rows.append(
            Metric(
                key="emergency_fund",
                label="Emergency fund",
                value=months,
                target=Decimal(FULL_EMERGENCY_FUND_MONTHS_LOW),
                unit="months",
                detail=(
                    f"Months of essential spending. The roadmap suggests "
                    f"{FULL_EMERGENCY_FUND_MONTHS_LOW}–{FULL_EMERGENCY_FUND_MONTHS_HIGH}."
                ),
                finding_kinds=["ef_below_starter", "ef_below_full"],
                report="essentials",
            )
        )
    else:
        rows.append(
            Metric(
                key="emergency_fund",
                label="Emergency fund",
                value=ef.get("value") if ef.get("tracked") else None,
                target=STARTER,
                unit="money",
                detail=(
                    "Against the starter amount — tag what you could not do without "
                    "as Essential and this becomes months of spending."
                    if ef.get("tracked")
                    else "Not tracked."
                ),
                finding_kinds=["ef_below_starter", "ef_below_full"],
                report="essentials",
            )
        )

    rows.append(
        Metric(
            key="high_interest_debt",
            label=f"Debt at {HIGH_INTEREST_APR}%+ APR",
            value=high.get("value") if high.get("tracked") else None,
            target=Decimal("0"),
            unit="money",
            detail=high.get("reason", "") if high.get("tracked") else "Not tracked.",
            finding_kinds=["high_interest_debt", "unknown_rates"],
            report="liabilities",
        )
    )
    rows.append(
        Metric(
            key="moderate_interest_debt",
            label=f"Debt at {MODERATE_INTEREST_APR}–{HIGH_INTEREST_APR}% APR",
            value=moderate.get("value") if moderate.get("tracked") else None,
            target=Decimal("0"),
            unit="money",
            detail=moderate.get("reason", "") if moderate.get("tracked") else "Not tracked.",
            finding_kinds=["moderate_debt"],
            report="liabilities",
        )
    )
    rows.append(
        Metric(
            key="retirement_contributions",
            label="Retirement saving",
            value=retirement.get("value") if retirement.get("tracked") else None,
            target=Decimal(RETIREMENT_TARGET_RATE),
            unit="percent",
            detail=retirement.get("reason", "") if retirement.get("tracked") else "Not tracked.",
            finding_kinds=["retirement_below_target"],
            report="savings-rate",
        )
    )
    rows.append(
        Metric(
            key="chronic_overspend",
            label="Overspent month after month",
            value=Decimal(inputs.chronic_count),
            target=Decimal("0"),
            unit="count",
            detail=(
                ", ".join(inputs.chronic_names[:3])
                + (" …" if len(inputs.chronic_names) > 3 else "")
                if inputs.chronic_names
                else "Over budget in three of the last six months counts as chronic."
            ),
            finding_kinds=["chronic_overspend"],
            report="plan-reality",
        )
    )
    rows.append(
        Metric(
            key="categories_funded",
            label="Targets funded this month",
            value=Decimal(inputs.funded),
            target=Decimal(inputs.with_targets),
            unit="count",
            detail="Categories with a target that Fill Underfunded would leave alone.",
        )
    )
    stale = [f for f in _stale_external(inputs)]
    gaps = len(inputs.unknown_rate_names) + len(stale)
    rows.append(
        Metric(
            key="data_gaps",
            label="Data gaps",
            value=Decimal(gaps),
            target=Decimal("0"),
            unit="count",
            detail=(
                ", ".join(inputs.unknown_rate_names[:3])
                + (" …" if len(inputs.unknown_rate_names) > 3 else "")
                if inputs.unknown_rate_names
                else "Debts with no rate on record, and self-reported figures over a year old."
            ),
            finding_kinds=["unknown_rates", "stale_external"],
            report="liabilities",
        )
    )
    return rows
