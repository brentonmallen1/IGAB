"""The one rule for what reconciliation locks — domain.reconciliation.

Pinned here so the service, undo and the bank-posting rule cannot drift on
which fields a statement vouches for, or on what counts as a change.
"""

import uuid
from datetime import date
from decimal import Decimal

from igab.domain.reconciliation import (
    RECONCILED_LOCKED_FIELDS,
    locked_changes,
    locked_values,
    reconciled_edit_message,
)


class Row:
    def __init__(self) -> None:
        self.amount = Decimal("-12.34")
        self.date = date(2026, 7, 10)
        self.cleared = "reconciled"
        self.account_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        self.memo = "lunch"
        self.category_id = uuid.uuid4()


def test_locked_fields_are_amount_date_cleared_account():
    assert RECONCILED_LOCKED_FIELDS == {"amount", "date", "cleared", "account_id"}


def test_a_changed_locked_value_is_reported():
    row = Row()
    assert locked_changes(locked_values(row), {"amount": Decimal("-99.00")}) == {"amount"}
    assert locked_changes(locked_values(row), {"date": date(2026, 1, 1)}) == {"date"}
    assert locked_changes(locked_values(row), {"cleared": "cleared"}) == {"cleared"}
    assert locked_changes(locked_values(row), {"account_id": uuid.uuid4()}) == {"account_id"}


def test_an_unchanged_locked_value_is_not_a_change():
    row = Row()
    proposed = {"amount": Decimal("-12.34"), "date": date(2026, 7, 10), "memo": "x"}
    assert locked_changes(locked_values(row), proposed) == set()


def test_decimal_scale_does_not_count_as_a_change():
    row = Row()
    assert locked_changes(locked_values(row), {"amount": Decimal("-12.3400")}) == set()


def test_unlocked_fields_are_never_reported():
    row = Row()
    proposed = {"memo": "changed", "category_id": uuid.uuid4(), "payee_id": uuid.uuid4()}
    assert locked_changes(locked_values(row), proposed) == set()


def test_a_locked_field_with_nothing_to_compare_against_counts_as_a_change():
    # Silence must never unlock money: a row that cannot report its current
    # amount cannot vouch that the proposed one is unchanged.
    assert locked_changes({}, {"amount": Decimal("1")}) == {"amount"}


def test_message_names_the_fields_in_a_stable_order():
    assert reconciled_edit_message({"date", "amount"}) == (
        "This transaction is reconciled — unlock it to change amount, date"
    )
