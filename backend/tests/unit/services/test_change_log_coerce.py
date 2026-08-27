"""Undo re-applies snapshot values through coerce_value. A payee snapshot
recorded before mapping_samples became a list holds the comma string, and
the column is a non-null list now — that boundary must read both shapes."""

from igab.db.models import Payee
from igab.services.change_log import coerce_value


def test_old_string_snapshot_restores_as_a_list() -> None:
    assert coerce_value(Payee, "mapping_samples", "ADP PAYROLL, ADP TOTALSOURCE") == [
        "ADP PAYROLL",
        "ADP TOTALSOURCE",
    ]


def test_list_snapshot_and_null_restore_as_lists() -> None:
    assert coerce_value(Payee, "mapping_samples", ["A", "a", " B "]) == ["A", "B"]
    assert coerce_value(Payee, "mapping_samples", None) == []


def test_other_fields_are_untouched() -> None:
    assert coerce_value(Payee, "match_pattern", None) is None
    assert coerce_value(Payee, "name", "Costco") == "Costco"
