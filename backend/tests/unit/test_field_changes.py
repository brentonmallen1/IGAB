"""What counts as an edit to a field — the comparison two guards share.

Each case here is a refusal the user could not act on before: the field they
were told to leave alone was one the editor restated unchanged.
"""

from datetime import date
from decimal import Decimal

from igab.domain.field_changes import changed_fields

TODAY = date(2026, 9, 19)


def test_a_restated_value_is_not_a_change():
    assert (
        changed_fields({"amount": Decimal("-17.09")}, {"amount": Decimal("-17.09")}, ["amount"])
        == set()
    )


def test_scale_from_a_numeric_round_trip_is_not_a_change():
    assert (
        changed_fields({"amount": Decimal("12.34")}, {"amount": Decimal("12.3400")}, ["amount"])
        == set()
    )


def test_a_different_value_is_a_change():
    assert changed_fields(
        {"amount": Decimal("-500.00"), "date": TODAY},
        {"amount": Decimal("-600.00"), "date": TODAY},
        ["amount", "date"],
    ) == {"amount"}


def test_an_absent_field_is_untouched():
    assert (
        changed_fields({"amount": Decimal("1.00"), "date": TODAY}, {"date": TODAY}, ["amount"])
        == set()
    )


def test_no_current_value_to_compare_against_counts_as_a_change():
    assert changed_fields({}, {"amount": Decimal("1.00")}, ["amount"]) == {"amount"}


def test_fields_outside_the_asked_set_are_ignored():
    assert changed_fields({"memo": "a"}, {"memo": "b"}, ["amount"]) == set()
