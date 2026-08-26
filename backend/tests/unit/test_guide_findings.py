"""The checkup's thresholds and ranking.

Pure, so every rule in `findings.py` is a one-line case here — including the
ones where the right answer is silence. A finding the app cannot defend is
worse than none, and "we could not tell" must never become "you have nothing".
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from igab.domain.dates import add_months
from igab.guide.concepts import STALE_EXTERNAL_MONTHS
from igab.guide.findings import RULES, CheckupInputs, evaluate, metrics

TODAY = date(2026, 8, 26)


def sig(
    *,
    tracked: bool = True,
    met: bool | None = None,
    value: str | None = None,
    target: str | None = None,
    gaps: tuple[str, ...] = (),
    external_as_of: date | None = None,
    external_value: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    return {
        "tracked": tracked,
        "met": met,
        "value": Decimal(value) if value is not None else None,
        "target": Decimal(target) if target is not None else None,
        "gaps": list(gaps),
        "external_as_of": external_as_of,
        "external_value": Decimal(external_value) if external_value is not None else None,
        "reason": reason,
    }


def inputs(signals: dict[str, dict] | None = None, **kw) -> CheckupInputs:
    defaults: dict[str, Any] = {
        "signals": signals or {},
        "essentials_monthly": None,
        "chronic_count": 0,
        "chronic_names": [],
        "funded": 0,
        "with_targets": 0,
        "unknown_rate_names": [],
        "today": TODAY,
    }
    defaults.update(kw)
    return CheckupInputs(**defaults)


def kinds(found) -> list[str]:
    return [f.kind for f in found]


class TestRanking:
    def test_order_is_the_rule_table_not_insertion_order(self):
        signals = {
            "retirement_contributions": sig(met=False, value="8"),
            "emergency_fund": sig(met=False, value="500", target="9720"),
            "high_interest_debt": sig(met=False, value="3410"),
        }
        assert kinds(evaluate(inputs(signals))) == [
            "high_interest_debt",
            "ef_below_starter",
            "retirement_below_target",
        ]

    def test_high_interest_beats_everything(self):
        signals = {
            "high_interest_debt": sig(met=False, value="3410", gaps=("Unknown card",)),
            "moderate_interest_debt": sig(met=False, value="14200"),
            "emergency_fund": sig(
                met=False, value="4000", target="9720", external_as_of=add_months(TODAY, -24)
            ),
            "retirement_contributions": sig(met=False, value="8"),
        }
        found = evaluate(
            inputs(
                signals,
                chronic_count=2,
                chronic_names=["Dining Out", "Groceries"],
                unknown_rate_names=["Unknown card"],
            )
        )
        assert kinds(found)[0] == "high_interest_debt"
        ranks = [f.rank for f in found]
        assert ranks == sorted(ranks)
        # Every rule that can fire together did, in the table's order. The two
        # emergency-fund rules are exclusive by design — one nag per problem.
        assert kinds(found) == [kind for kind, _, _ in RULES if kind != "ef_below_starter"]

    def test_ties_within_a_rank_sort_by_concept_then_title(self):
        stale = add_months(TODAY, -STALE_EXTERNAL_MONTHS)
        signals = {
            "hsa": sig(external_as_of=stale, external_value="4000"),
            "emergency_fund": sig(met=True, value="9000", external_as_of=stale),
        }
        found = evaluate(inputs(signals))
        assert [f.concept_key for f in found] == ["emergency_fund", "hsa"]


class TestPredicates:
    def test_dismissed_concept_never_yields_a_finding(self):
        signals = {
            "high_interest_debt": sig(tracked=False, met=None),
            "emergency_fund": sig(tracked=False, met=False, value="0"),
        }
        assert evaluate(inputs(signals)) == []

    def test_unknown_met_is_not_a_finding(self):
        # Detection declined to answer. That is not "you have nothing".
        signals = {
            "high_interest_debt": sig(met=None),
            "emergency_fund": sig(met=None, value=None),
            "retirement_contributions": sig(met=None, value=None),
        }
        assert evaluate(inputs(signals)) == []

    def test_ef_exactly_at_starter_is_not_below_it(self):
        signals = {"emergency_fund": sig(met=False, value="1000", target="9720")}
        assert kinds(evaluate(inputs(signals))) == ["ef_below_full"]

    def test_ef_below_starter_suppresses_below_full(self):
        # One finding per problem: a $500 fund is short of the starter, and
        # saying it is also short of three months would be the same nag twice.
        signals = {"emergency_fund": sig(met=False, value="500", target="9720")}
        found = evaluate(inputs(signals))
        assert kinds(found) == ["ef_below_starter"]
        assert found[0].target == Decimal("1000")

    def test_ef_below_full_carries_the_served_target(self):
        signals = {"emergency_fund": sig(met=False, value="4000", target="9720")}
        found = evaluate(inputs(signals))
        assert kinds(found) == ["ef_below_full"]
        assert found[0].target == Decimal("9720")

    def test_negative_ef_value_reads_below_starter(self):
        # An overspent emergency-fund category is worse than an empty one, and
        # still one finding.
        signals = {"emergency_fund": sig(met=False, value="-50", target="9720")}
        found = evaluate(inputs(signals))
        assert kinds(found) == ["ef_below_starter"]
        assert found[0].value == Decimal("-50")

    def test_external_declared_without_a_figure_is_met_and_silent(self):
        signals = {"emergency_fund": sig(met=True, value=None)}
        assert evaluate(inputs(signals)) == []

    def test_chronic_overspend_carries_its_names(self):
        found = evaluate(inputs(chronic_count=2, chronic_names=["Dining Out", "Groceries"]))
        assert kinds(found) == ["chronic_overspend"]
        assert found[0].value == Decimal("2")
        assert found[0].names == ["Dining Out", "Groceries"]

    def test_stale_external_at_exactly_twelve_months(self):
        cutoff = add_months(TODAY, -STALE_EXTERNAL_MONTHS)
        on_the_day = {"emergency_fund": sig(met=True, value="9000", external_as_of=cutoff)}
        assert kinds(evaluate(inputs(on_the_day))) == ["stale_external"]

        a_day_younger = {
            "emergency_fund": sig(met=True, value="9000", external_as_of=cutoff + timedelta(days=1))
        }
        assert evaluate(inputs(a_day_younger)) == []

    def test_one_stale_finding_per_concept(self):
        stale = add_months(TODAY, -STALE_EXTERNAL_MONTHS - 1)
        signals = {
            "emergency_fund": sig(met=True, value="9000", external_as_of=stale),
            "hsa": sig(external_as_of=stale, external_value="4000"),
            "college_savings": sig(external_as_of=TODAY),
        }
        found = evaluate(inputs(signals))
        assert kinds(found) == ["stale_external", "stale_external"]
        assert sorted(f.concept_key for f in found) == ["emergency_fund", "hsa"]
        assert next(f for f in found if f.concept_key == "hsa").value == Decimal("4000")

    def test_unknown_rates_lists_every_gap(self):
        signals = {"high_interest_debt": sig(met=False, value="0", gaps=("A", "B"))}
        found = evaluate(inputs(signals, unknown_rate_names=["A", "B"]))
        gaps = next(f for f in found if f.kind == "unknown_rates")
        assert gaps.names == ["A", "B"]
        assert gaps.value == Decimal("2")

    def test_clean_budget_yields_nothing(self):
        signals = {
            "high_interest_debt": sig(met=True, value="0"),
            "moderate_interest_debt": sig(met=True, value="0"),
            "emergency_fund": sig(met=True, value="12000", target="9720"),
            "retirement_contributions": sig(met=True, value="16"),
        }
        assert evaluate(inputs(signals, funded=3, with_targets=3)) == []


class TestMetrics:
    def test_ef_months_is_cent_quantized(self):
        signals = {"emergency_fund": sig(met=False, value="1240", target="9720")}
        rows = metrics(inputs(signals, essentials_monthly=Decimal("3240")))
        ef = next(m for m in rows if m.key == "emergency_fund")
        assert ef.unit == "months"
        assert ef.value == Decimal("0.38")
        assert ef.target == Decimal("3")

    def test_ef_months_is_none_without_essentials(self):
        # No essentials figure: the row falls back to money against the
        # starter amount rather than dividing by zero into "0 months".
        signals = {"emergency_fund": sig(met=False, value="1240", target="1000")}
        for essentials in (None, Decimal("0")):
            rows = metrics(inputs(signals, essentials_monthly=essentials))
            ef = next(m for m in rows if m.key == "emergency_fund")
            assert ef.unit == "money"
            assert ef.value == Decimal("1240")
            assert ef.target == Decimal("1000")

    def test_untracked_concept_reads_as_not_tracked(self):
        signals = {"high_interest_debt": sig(tracked=False)}
        rows = metrics(inputs(signals))
        high = next(m for m in rows if m.key == "high_interest_debt")
        assert high.value is None
        assert high.detail == "Not tracked."

    def test_every_finding_kind_has_a_metric_home(self):
        rows = metrics(inputs())
        homes = {kind for m in rows for kind in m.finding_kinds}
        assert homes == {kind for kind, _, _ in RULES}

    def test_metric_keys_are_unique(self):
        rows = metrics(inputs())
        assert len({m.key for m in rows}) == len(rows)

    def test_funded_row_counts_what_fill_underfunded_leaves_alone(self):
        rows = metrics(inputs(funded=18, with_targets=21))
        funded = next(m for m in rows if m.key == "categories_funded")
        assert funded.value == Decimal("18")
        assert funded.target == Decimal("21")
        assert funded.finding_kinds == []


class TestNamesTravelWhole:
    """A list cut to three with an ellipsis is information quietly lost."""

    def test_chronic_metric_carries_every_name(self):
        names = [f"Category {i}" for i in range(12)]
        rows = metrics(inputs(chronic_count=12, chronic_names=names))
        row = next(m for m in rows if m.key == "chronic_overspend")
        assert row.names == names
        assert "…" not in row.detail

    def test_data_gaps_metric_names_every_gap_and_stale_figure(self):
        stale = add_months(TODAY, -STALE_EXTERNAL_MONTHS - 1)
        signals = {
            "emergency_fund": sig(met=True, value="9000", external_as_of=stale),
            "hsa": sig(external_as_of=stale, external_value="4000"),
        }
        unknown = [f"Card {i}" for i in range(8)]
        rows = metrics(inputs(signals, unknown_rate_names=unknown))
        row = next(m for m in rows if m.key == "data_gaps")
        assert row.value == Decimal("10")
        assert len(row.names) == 10
        assert row.names[0] == "Card 0 — no rate on record"
        assert any(n.startswith("Emergency fund — told to us") for n in row.names)
        assert any(n.startswith("Health savings account — told to us") for n in row.names)
