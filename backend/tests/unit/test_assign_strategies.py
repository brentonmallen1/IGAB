"""Unit tests for the pure per-category assign-strategy math.

`strategy_new_assigned` decides each category's target assigned value under
a bulk strategy (None = untouched). This feeds previews, menu totals, AND
apply — a bug here directly mis-assigns money, so every branch and sign
case is pinned.
"""

import uuid
from decimal import Decimal

import pytest
from igab.services.assign_service import (
    ASSIGN_STRATEGIES,
    HISTORY_STRATEGIES,
    distribute_fill,
    strategy_new_assigned,
)
from igab.services.budget_service import CategoryHistory


def D(s: str) -> Decimal:
    return Decimal(s)


def history(
    last_assigned="100.00",
    last_spent="80.00",
    avg_assigned="90.00",
    avg_spent="85.00",
) -> CategoryHistory:
    return CategoryHistory(
        category_id=uuid.uuid4(),
        last_month_assigned=D(last_assigned),
        last_month_spent=D(last_spent),
        average_assigned=D(avg_assigned),
        average_spent=D(avg_spent),
        months_included=6,
    )


class TestHistoryStrategies:
    def test_each_strategy_returns_its_history_field(self):
        h = history("111.11", "222.22", "333.33", "444.44")
        assert strategy_new_assigned("last_month_assigned", D("0"), D("0"), h) == D("111.11")
        assert strategy_new_assigned("last_month_spent", D("0"), D("0"), h) == D("222.22")
        assert strategy_new_assigned("average_assigned", D("0"), D("0"), h) == D("333.33")
        assert strategy_new_assigned("average_spent", D("0"), D("0"), h) == D("444.44")

    def test_set_below_current_produces_negative_delta(self):
        h = history(last_assigned="50.00")
        new = strategy_new_assigned("last_month_assigned", D("200.00"), D("0"), h)
        assert new == D("50.00")
        assert new - D("200.00") == D("-150.00")  # money returns to TBA

    def test_set_equal_to_current_is_a_zero_delta(self):
        h = history(last_assigned="75.00")
        new = strategy_new_assigned("last_month_assigned", D("75.00"), D("10.00"), h)
        assert new == D("75.00")  # caller skips zero deltas

    def test_zero_history_sets_assigned_to_zero(self):
        h = history(last_assigned="0.00")
        assert strategy_new_assigned("last_month_assigned", D("40.00"), D("0"), h) == D("0.00")


class TestResetAvailable:
    def test_positive_available_is_returned_to_tba(self):
        new = strategy_new_assigned("reset_available", D("100.00"), D("35.50"), history())
        assert new == D("64.50")

    def test_result_may_go_negative(self):
        # Available exceeds this month's assigned (carryover from prior months):
        # returning it all pushes assigned negative — legal, mirrors move-money.
        new = strategy_new_assigned("reset_available", D("20.00"), D("120.00"), history())
        assert new == D("-100.00")

    def test_zero_available_untouched(self):
        assert strategy_new_assigned("reset_available", D("50.00"), D("0"), history()) is None

    def test_negative_available_untouched(self):
        # Overspent categories are Cover Overspending's job.
        assert strategy_new_assigned("reset_available", D("50.00"), D("-30.00"), history()) is None


class TestResetAssigned:
    def test_positive_assigned_resets_to_zero(self):
        assert strategy_new_assigned("reset_assigned", D("80.00"), D("10.00"), history()) == D("0")

    def test_negative_assigned_resets_to_zero_pulling_from_tba(self):
        new = strategy_new_assigned("reset_assigned", D("-25.00"), D("0"), history())
        assert new == D("0")
        assert new - D("-25.00") == D("25.00")  # positive delta: pulls from TBA

    def test_zero_assigned_untouched(self):
        assert strategy_new_assigned("reset_assigned", D("0"), D("15.00"), history()) is None


class TestUnknownStrategy:
    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError):
            strategy_new_assigned("bogus", D("0"), D("0"), history())

    def test_strategy_lists_are_consistent(self):
        assert set(HISTORY_STRATEGIES) < set(ASSIGN_STRATEGIES)
        assert "underfunded" in ASSIGN_STRATEGIES
        assert "reset_available" in ASSIGN_STRATEGIES
        assert "reset_assigned" in ASSIGN_STRATEGIES


class TestDistributeFill:
    """The extracted fill-targets distribution (behavior pinned pre-extraction
    by test_fill_targets_distribution.py's mirror copy — this pins the real one)."""

    def test_full_funding_when_tba_covers_all(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        result = distribute_fill({a: D("100"), b: D("50")}, D("200"))
        assert result == {a: D("100"), b: D("50")}

    def test_proportional_when_short(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        result = distribute_fill({a: D("100"), b: D("100")}, D("100"))
        assert result[a] == D("50.00")
        assert result[b] == D("50.00")

    def test_capped_by_own_need(self):
        a = uuid.uuid4()
        result = distribute_fill({a: D("30")}, D("1000"))
        assert result[a] == D("30")

    def test_zero_tba_assigns_nothing(self):
        a = uuid.uuid4()
        assert distribute_fill({a: D("100")}, D("0")) == {a: D("0")}

    def test_negative_tba_treated_as_zero(self):
        a = uuid.uuid4()
        assert distribute_fill({a: D("100")}, D("-50")) == {a: D("0")}

    def test_empty_shortfalls(self):
        assert distribute_fill({}, D("100")) == {}
