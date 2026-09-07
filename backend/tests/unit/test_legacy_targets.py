"""The retired `needed_for_spending` maps to what it always computed as.

The migration states the mapping in SQL; `normalize_legacy_target` states
it in Python for the snapshot importer. This pins the two against one
table of cases so they cannot drift.
"""

from datetime import date

import pytest

from igab.domain.targets import is_pending, normalize_legacy_target

CASES = [
    ("needed_for_spending", None, "monthly_funding"),
    ("needed_for_spending", date(2026, 12, 1), "savings_balance"),
    ("monthly_funding", None, "monthly_funding"),
    ("weekly_funding", None, "weekly_funding"),
    ("savings_balance", None, "savings_balance"),
    ("savings_balance", date(2026, 12, 1), "savings_balance"),
]


@pytest.mark.parametrize(("stored", "target_date", "expected"), CASES)
def test_the_python_mapping(stored, target_date, expected):
    assert normalize_legacy_target(stored, target_date) == expected


def _sql_mapping(stored: str, target_date: date | None) -> str:
    """The migration's two UPDATE predicates, spelled in Python."""
    if stored == "needed_for_spending" and target_date is None:
        return "monthly_funding"
    if stored == "needed_for_spending" and target_date is not None:
        return "savings_balance"
    return stored


@pytest.mark.parametrize(("stored", "target_date", "expected"), CASES)
def test_the_migration_agrees_with_the_function(stored, target_date, expected):
    assert _sql_mapping(stored, target_date) == normalize_legacy_target(stored, target_date)


def test_the_migration_file_states_both_predicates():
    from pathlib import Path

    src = next(Path("alembic/versions").glob("*targets_consolidate_and_funding_day.py")).read_text()
    assert "target_type = 'needed_for_spending' AND target_date IS NULL" in src
    assert "target_type = 'needed_for_spending' AND target_date IS NOT NULL" in src


class TestIsPending:
    def test_before_the_day_in_the_current_month(self):
        assert is_pending(date(2026, 5, 1), date(2026, 5, 6), 15)

    def test_on_and_after_the_day(self):
        assert not is_pending(date(2026, 5, 1), date(2026, 5, 15), 15)
        assert not is_pending(date(2026, 5, 1), date(2026, 5, 20), 15)

    def test_never_in_a_past_month(self):
        assert not is_pending(date(2026, 4, 1), date(2026, 5, 2), 28)

    def test_always_in_a_future_month(self):
        assert is_pending(date(2026, 6, 1), date(2026, 5, 31), 1)

    def test_day_one_is_never_pending_in_the_current_month(self):
        assert not is_pending(date(2026, 5, 1), date(2026, 5, 1), 1)

    def test_a_day_the_month_does_not_have_arrives_on_its_last_day(self):
        """The reason the bound could be raised from 28 to 31.

        Unclamped, `today.day < 30` is true for every day of February, so a
        target set to "check after the 30th" would read pending all month and
        then flip straight to underfunded on March 1st — never nagged in the
        month it was for.
        """
        february = date(2027, 2, 1)
        assert is_pending(february, date(2027, 2, 27), 30)
        # The 28th IS February's last day, so the day has arrived.
        assert not is_pending(february, date(2027, 2, 28), 30)
        assert not is_pending(february, date(2027, 2, 28), 31)

    def test_a_leap_february_clamps_to_the_29th(self):
        leap = date(2028, 2, 1)
        assert is_pending(leap, date(2028, 2, 28), 31)
        assert not is_pending(leap, date(2028, 2, 29), 31)

    def test_a_long_month_uses_the_day_itself(self):
        # No clamping where the day exists: the 30th of May is the 30th.
        assert is_pending(date(2026, 5, 1), date(2026, 5, 29), 30)
        assert not is_pending(date(2026, 5, 1), date(2026, 5, 30), 30)
