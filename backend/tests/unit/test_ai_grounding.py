"""Every money figure in an answer has to come from somewhere.

The system prompt tells the model never to invent a figure. This is the part
that checks, because an instruction to a 7-8B model is a request.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from igab.ai.grounding import (
    TOLERANCE,
    check,
    collect_numbers,
    extract_figures,
)

_SHARED = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "money_figures.json").read_text()
)


class TestFindingMoneyInProse:
    @pytest.mark.parametrize("case", _SHARED["cases"], ids=[c["note"] for c in _SHARED["cases"]])
    def test_shared_money_shapes(self, case):
        """One rule, two languages: the frontend styles the same figures this
        module checks, from the same cases. See shared/money_figures.json."""
        values = [f.value for f in extract_figures(case["text"])]
        assert values == [Decimal(v) for v in case["figures"]]

    def test_empty_and_none_safe(self):
        assert extract_figures("") == []
        assert extract_figures(None) == []  # type: ignore[arg-type]


class TestCollectingWhatTheToolsReturned:
    def test_walks_nested_results(self):
        result = {
            "rows": [{"category": "Groceries", "total": 120.0}, {"total": 45.5}],
            "total_amount": 165.5,
        }
        assert collect_numbers(result) >= {Decimal("120"), Decimal("45.5"), Decimal("165.5")}

    def test_spending_stored_negative_counts_as_its_magnitude(self):
        """The ledger stores spending negative and every surface shows it
        positive; a model quoting $120 from a -120 row is quoting what it was
        given."""
        assert Decimal("120") in collect_numbers({"amount": -120.0})

    def test_numbers_inside_a_string_count(self):
        # Tool notes carry figures too: "Showing 25 of 912 rows".
        assert Decimal("912") in collect_numbers({"note": "Showing 25 of 912 rows"})

    def test_booleans_are_not_numbers(self):
        assert collect_numbers({"truncated": True, "ok": False}) == set()

    def test_none_and_empty_containers(self):
        assert collect_numbers(None) == set()
        assert collect_numbers({}) == set()
        assert collect_numbers([]) == set()


class TestTheCheck:
    def test_a_figure_the_tools_returned_is_grounded(self):
        report = check("Groceries came to $120.00.", [{"rows": [{"total": 120.0}]}])
        assert report.clean
        assert len(report.grounded) == 1
        assert report.unsupported == []

    def test_a_figure_nothing_returned_is_unsupported(self):
        """The case this exists for: a confident number nobody can source."""
        report = check("Groceries came to $4,182.33.", [{"rows": [{"total": 120.0}]}])
        assert not report.clean
        assert [f.text for f in report.unsupported] == ["$4,182.33"]

    def test_ordinary_arithmetic_is_not_called_invention(self):
        """Adding two envelopes is the most ordinary thing an answer does. If
        that reads as a fabrication the check cries wolf and stops being read."""
        report = check(
            "Groceries $120.00 and Dining $45.00 come to $165.00.",
            [{"rows": [{"total": 120.0}, {"total": 45.0}]}],
        )
        assert report.clean
        assert len(report.derived) == 1

    def test_a_difference_is_derived_too(self):
        report = check(
            "You are $75.00 under, from $120.00 assigned and $45.00 spent.",
            [{"assigned": 120.0, "spent": 45.0}],
        )
        assert report.clean

    def test_rounding_slack_but_not_a_different_amount(self):
        grounded = [{"total": 120.00}]
        assert check("about $120.01", grounded).clean
        assert not check("about $121.00", grounded).clean

    def test_the_tolerance_boundary_is_exact(self):
        results = [{"total": 100.00}]
        edge = Decimal("100.00") + TOLERANCE
        assert check(f"${edge}", results).clean
        beyond = Decimal("100.00") + TOLERANCE + Decimal("0.01")
        assert not check(f"${beyond}", results).clean

    def test_an_answer_with_no_figures_is_not_claimed_as_checked(self):
        """Nothing to verify is not the same as verified — the UI must be able
        to tell those apart."""
        report = check("I could not find anything for that month.", [{"rows": []}])
        assert report.figures == []
        assert report.checked is False
        assert report.clean is False

    def test_figures_with_no_lookups_at_all_are_unsupported(self):
        """The worst case: it answered with numbers having looked nothing up."""
        report = check("You spent $500.00 last month.", [])
        assert report.lookups == 0
        assert len(report.unsupported) == 1

    def test_several_figures_are_reported_individually(self):
        report = check(
            "Groceries $120.00, Dining $45.00, and Fuel $999.99.",
            [{"rows": [{"total": 120.0}, {"total": 45.0}]}],
        )
        assert len(report.grounded) == 2
        assert [f.text for f in report.unsupported] == ["$999.99"]

    def test_the_record_shape_is_countable(self):
        report = check("$120.00 and $999.99", [{"total": 120.0}])
        record = report.as_record()
        assert record["figures"] == 2
        assert record["grounded"] == 1
        assert record["unsupported"] == ["$999.99"]
        assert record["lookups"] == 1

    def test_lookups_can_be_stated_rather_than_counted(self):
        report = check("no figures here", [{"a": 1}], lookups=3)
        assert report.lookups == 3

    def test_a_large_result_does_not_blow_up_the_pairwise_search(self):
        """The derived pass is quadratic and is capped for that reason."""
        big = [{"rows": [{"total": float(i)} for i in range(2000)]}]
        report = check("The total was $1.00.", big)
        assert report.clean
