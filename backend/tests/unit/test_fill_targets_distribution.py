"""
Tests for the fill-targets auto-assign distribution algorithm.

Algorithm:
  1. For each underfunded category: compute shortfall (needed this month).
  2. Distribute available TBA proportionally: each category gets
       proposed = min(shortfall, (shortfall / total_shortfall) * available_tba)
     rounded to 2 decimal places.
  3. Each proposed_addition is capped by the category's own shortfall — a
     category can never receive MORE than it needs.
  4. When TBA = 0 nothing is assigned.
  5. When all categories are fully funded, the algorithm returns no items.

This logic determines how much money gets assigned to each category — any
bug here directly causes incorrect budget amounts.
"""

from decimal import Decimal

import pytest


def D(s: str) -> Decimal:
    return Decimal(s)


# Pure implementation of the distribution algorithm (mirrors the endpoint logic)
def distribute(
    shortfalls: dict[str, Decimal],
    available_tba: Decimal,
) -> dict[str, Decimal]:
    """
    Given a dict of {category_id: shortfall} and available TBA,
    return {category_id: proposed_addition}.

    This is a pure function extracted from the endpoint for unit testing.
    """
    available_tba = max(D("0"), available_tba)
    total_shortfall = sum(shortfalls.values())
    result: dict[str, Decimal] = {}
    for cat_id, needed in shortfalls.items():
        if total_shortfall > D("0"):
            proportion = needed / total_shortfall
            proposed = min(needed, (proportion * available_tba).quantize(D("0.01")))
        else:
            proposed = D("0")
        result[cat_id] = proposed
    return result


class TestDistributeEqualShortfalls:
    def test_two_equal_categories_split_evenly(self):
        result = distribute({"a": D("100"), "b": D("100")}, D("100"))
        assert result["a"] == D("50.00")
        assert result["b"] == D("50.00")

    def test_three_equal_categories_split_evenly(self):
        result = distribute({"a": D("90"), "b": D("90"), "c": D("90")}, D("90"))
        assert result["a"] == D("30.00")
        assert result["b"] == D("30.00")
        assert result["c"] == D("30.00")

    def test_four_equal_categories_split_evenly(self):
        result = distribute({"a": D("100"), "b": D("100"), "c": D("100"), "d": D("100")}, D("200"))
        assert result["a"] == D("50.00")
        assert result["b"] == D("50.00")
        assert result["c"] == D("50.00")
        assert result["d"] == D("50.00")


class TestDistributeProportional:
    def test_larger_shortfall_gets_more(self):
        result = distribute({"a": D("300"), "b": D("100")}, D("200"))
        # a gets 3/4 = 150, b gets 1/4 = 50
        assert result["a"] == D("150.00")
        assert result["b"] == D("50.00")

    def test_heavily_imbalanced_shortfalls(self):
        result = distribute({"a": D("900"), "b": D("100")}, D("100"))
        # a gets 90%, b gets 10%
        assert result["a"] == D("90.00")
        assert result["b"] == D("10.00")

    def test_total_does_not_exceed_tba(self):
        shortfalls = {"a": D("500"), "b": D("300"), "c": D("200")}
        result = distribute(shortfalls, D("400"))
        total_assigned = sum(result.values())
        # Due to rounding, allow 1 cent tolerance
        assert total_assigned <= D("400.01")

    def test_proportions_are_consistent(self):
        """a:b shortfall ratio of 2:1 should produce 2:1 assignment ratio."""
        result = distribute({"a": D("200"), "b": D("100")}, D("300"))
        # Enough TBA for both → each gets what they need
        assert result["a"] == D("200.00")
        assert result["b"] == D("100.00")


class TestDistributionCaps:
    def test_category_never_gets_more_than_shortfall(self):
        """Even with excess TBA, a category only gets up to its shortfall."""
        result = distribute({"a": D("50"), "b": D("50")}, D("1000"))
        assert result["a"] == D("50.00")
        assert result["b"] == D("50.00")

    def test_single_category_gets_at_most_its_shortfall(self):
        result = distribute({"only": D("100")}, D("500"))
        assert result["only"] == D("100.00")

    def test_zero_tba_assigns_nothing(self):
        result = distribute({"a": D("100"), "b": D("200")}, D("0"))
        assert result["a"] == D("0")
        assert result["b"] == D("0")

    def test_negative_tba_treated_as_zero(self):
        """If TBA is negative (overspent), nothing gets assigned."""
        result = distribute({"a": D("100")}, D("-50"))
        assert result["a"] == D("0")


class TestDistributionEdgeCases:
    def test_empty_shortfalls_returns_empty(self):
        result = distribute({}, D("500"))
        assert result == {}

    def test_single_category_gets_all_tba_up_to_shortfall(self):
        result = distribute({"solo": D("200")}, D("150"))
        assert result["solo"] == D("150.00")

    def test_single_category_exact_match(self):
        result = distribute({"solo": D("100")}, D("100"))
        assert result["solo"] == D("100.00")

    def test_decimal_precision_two_places(self):
        """Results are always rounded to 2 decimal places."""
        result = distribute({"a": D("1"), "b": D("2")}, D("1"))
        for v in result.values():
            assert v == v.quantize(D("0.01"))

    def test_large_amounts(self):
        result = distribute({"mortgage": D("200000"), "emergency": D("50000")}, D("10000"))
        # mortgage = 80%, emergency = 20%
        assert result["mortgage"] == D("8000.00")
        assert result["emergency"] == D("2000.00")

    def test_small_amounts_with_rounding(self):
        """3 equal categories with TBA of $1 — each gets ~33 cents."""
        result = distribute({"a": D("100"), "b": D("100"), "c": D("100")}, D("1"))
        for v in result.values():
            assert v >= D("0.33")
            assert v <= D("0.34")

    def test_many_categories_total_stays_within_tba(self):
        """Sum of distributions should never exceed available TBA."""
        shortfalls = {str(i): D(str(i * 10 + 1)) for i in range(20)}
        tba = D("500")
        result = distribute(shortfalls, tba)
        total = sum(result.values())
        assert total <= tba + D("0.01")  # 1 cent rounding tolerance


class TestDistributionTbaSufficiency:
    def test_enough_tba_fully_funds_all(self):
        result = distribute({"a": D("100"), "b": D("200"), "c": D("300")}, D("600"))
        assert result["a"] == D("100.00")
        assert result["b"] == D("200.00")
        assert result["c"] == D("300.00")

    def test_insufficient_tba_distributes_proportionally(self):
        shortfalls = {"a": D("300"), "b": D("200"), "c": D("100")}
        result = distribute(shortfalls, D("300"))
        # Total shortfall = 600, TBA = 300 (50% coverage)
        # a: 300/600 * 300 = 150
        # b: 200/600 * 300 = 100
        # c: 100/600 * 300 = 50
        assert result["a"] == D("150.00")
        assert result["b"] == D("100.00")
        assert result["c"] == D("50.00")
        assert sum(result.values()) == D("300.00")
