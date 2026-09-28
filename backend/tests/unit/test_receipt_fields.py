"""What a receipt's read may write onto an existing row (domain.receipt_fields).

Placing a receipt on the bank's row and reprocessing a receipt used to spell
this rule twice. Each difference between the two copies is a case below,
named for the path that got it wrong.
"""

import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from igab.domain.receipt_fields import (
    FAILURE_STUB_MEMO,
    ExistingRow,
    ReceiptRead,
    receipt_changes,
    writable_fields,
)

PAYEE = uuid.uuid4()
CATEGORY = uuid.uuid4()

#: The scan's own row, untouched since it was read.
OWN = ExistingRow(
    own=True,
    confirmed=False,
    is_split=False,
    is_transfer=False,
    has_payee=True,
    has_category=True,
    memo="Weekly shop",
)
#: The bank's row the receipt was put on.
BANK = replace(OWN, own=False)

READ = ReceiptRead(
    date=date(2026, 8, 3),
    amount=Decimal("-44.00"),
    payee_id=PAYEE,
    category_id=CATEGORY,
    memo="Milk and towels",
)


class TestRefresh:
    def test_the_scans_own_unconfirmed_row_takes_everything(self):
        assert receipt_changes(OWN, READ, refresh=True) == {
            "date": date(2026, 8, 3),
            "amount": Decimal("-44.00"),
            "payee_id": PAYEE,
            "category_id": CATEGORY,
            "memo": "Milk and towels",
        }

    def test_a_confirmed_row_is_refreshed_not_refused(self):
        # Reprocess used to raise on an approved or cleared row. It refreshes
        # payee, category and memo, and the confirmed money stands.
        changes = receipt_changes(replace(OWN, confirmed=True), READ, refresh=True)
        assert changes == {"payee_id": PAYEE, "category_id": CATEGORY, "memo": "Milk and towels"}

    def test_a_bank_row_keeps_the_banks_date_and_amount(self):
        # Reprocess used to write the read's total and date over the bank's
        # own row when the receipt had been matched to it.
        changes = receipt_changes(BANK, READ, refresh=True)
        assert "date" not in changes and "amount" not in changes
        assert changes["category_id"] == CATEGORY

    @pytest.mark.parametrize("field", ["payee_id", "category_id"])
    def test_an_unresolved_value_keeps_the_rows_own(self, field):
        # Reprocess used to send an explicit None, which clears the field.
        changes = receipt_changes(OWN, replace(READ, **{field: None}), refresh=True)
        assert field not in changes

    @pytest.mark.parametrize("memo", [None, "", "   "])
    def test_a_blank_memo_keeps_the_rows_own(self, memo):
        changes = receipt_changes(OWN, replace(READ, memo=memo), refresh=True)
        assert "memo" not in changes

    def test_a_split_keeps_its_lines_category_and_sum(self):
        split = replace(OWN, is_split=True, has_category=False)
        assert writable_fields(split, refresh=True) == {"date", "payee_id", "memo"}

    def test_a_transfer_leg_keeps_its_payee_and_category(self):
        transfer = replace(BANK, is_transfer=True)
        assert writable_fields(transfer, refresh=True) == {"memo"}

    def test_nothing_resolved_on_a_confirmed_row_is_no_change(self):
        read = replace(READ, payee_id=None, category_id=None, memo=None)
        assert receipt_changes(replace(OWN, confirmed=True), read, refresh=True) == {}


class TestPlace:
    """Placing a receipt on an existing row fills only what it is missing."""

    def test_a_filled_row_is_left_alone(self):
        assert receipt_changes(BANK, READ, refresh=False) == {}

    def test_never_the_date_or_amount_even_on_an_ai_row(self):
        bare = replace(OWN, has_payee=False, has_category=False, memo=None)
        assert writable_fields(bare, refresh=False) == {"payee_id", "category_id", "memo"}

    def test_a_missing_payee_is_filled(self):
        # Placing used to leave a bank row with no payee without one, while
        # filling its category and memo from the same read.
        changes = receipt_changes(replace(BANK, has_payee=False), READ, refresh=False)
        assert changes == {"payee_id": PAYEE}

    def test_a_split_is_never_given_a_category(self):
        split = replace(BANK, is_split=True, has_category=False)
        assert "category_id" not in receipt_changes(split, READ, refresh=False)


class TestFailureStubMemo:
    """The placeholder a failed scan leaves is never the user's memo."""

    STUB = replace(OWN, has_payee=False, has_category=False, memo=FAILURE_STUB_MEMO)

    @pytest.mark.parametrize("refresh", [True, False])
    def test_a_read_memo_replaces_it(self, refresh):
        changes = receipt_changes(self.STUB, READ, refresh=refresh)
        assert changes["memo"] == "Milk and towels"

    @pytest.mark.parametrize("refresh", [True, False])
    def test_a_read_with_no_memo_clears_it(self, refresh):
        changes = receipt_changes(self.STUB, replace(READ, memo=None), refresh=refresh)
        assert changes["memo"] is None

    def test_a_users_memo_is_not_cleared(self):
        changes = receipt_changes(OWN, replace(READ, memo=None), refresh=True)
        assert "memo" not in changes
