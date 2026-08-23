"""The preview step's non-guessing facts: the activity window, and the
include / close / skip choice.

Dates were the piece already being parsed and thrown away. `YNABTransaction`
reads a date on every row and `build_ynab_preview` looked only at counts and
amounts, so nothing could say that 14 of a real export's 47 accounts had seen
no activity since 2019–2021. A list of 47 accounts with no way to tell the
live ones from the archived ones is what read as "accounts appearing from
nowhere".
"""

import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from igab.api.v1.imports import build_ynab_preview, parse_account_types_form
from igab.integrations.ynab.models import YNABBudget, YNABTransaction


def _txn(account: str, when: date, amount: str = "-5.00") -> YNABTransaction:
    return YNABTransaction(
        account_name=account,
        date=when,
        payee="Shop",
        category_group="Everyday",
        category="Groceries",
        memo=None,
        amount=Decimal(amount),
        cleared="cleared",
    )


def _preview(*transactions: YNABTransaction):
    result = build_ynab_preview(YNABBudget(transactions=list(transactions), budget_entries=[]))
    return {a.name: a for a in result.accounts}


class TestTheActivityWindow:
    def test_one_transaction_is_both_ends_of_the_window(self):
        accounts = _preview(_txn("Checking", date(2021, 3, 4)))
        assert accounts["Checking"].first_activity == date(2021, 3, 4)
        assert accounts["Checking"].last_activity == date(2021, 3, 4)

    def test_out_of_order_rows_still_give_the_true_window(self):
        """min/max, not first/last row. A YNAB export is not guaranteed to be
        date-ordered, and one late row read as `last_activity` would report a
        dormant account as live — the exact judgement this feeds."""
        accounts = _preview(
            _txn("Checking", date(2020, 6, 1)),
            _txn("Checking", date(2019, 1, 15)),
            _txn("Checking", date(2021, 12, 31)),
            _txn("Checking", date(2020, 2, 2)),
        )
        assert accounts["Checking"].first_activity == date(2019, 1, 15)
        assert accounts["Checking"].last_activity == date(2021, 12, 31)

    def test_each_account_keeps_its_own_window(self):
        accounts = _preview(
            _txn("Checking", date(2026, 8, 1)),
            _txn("Old Savings", date(2019, 4, 2)),
            _txn("Old Savings", date(2019, 5, 9)),
        )
        assert accounts["Checking"].last_activity == date(2026, 8, 1)
        assert accounts["Old Savings"].last_activity == date(2019, 5, 9)
        assert accounts["Old Savings"].first_activity == date(2019, 4, 2)

    def test_the_window_does_not_disturb_the_existing_facts(self):
        accounts = _preview(
            _txn("Checking", date(2020, 1, 1), "-10.00"),
            _txn("Checking", date(2020, 2, 1), "30.00"),
        )
        assert accounts["Checking"].transaction_count == 2
        assert accounts["Checking"].implied_balance == Decimal("20.00")


class TestTheImportChoice:
    def _form(self, **choices) -> str:
        return json.dumps(
            {
                name: {"account_type": "checking", "on_budget": True, **flags}
                for name, flags in choices.items()
            }
        )

    def test_close_round_trips(self):
        _, skipped, closed = parse_account_types_form(self._form(Old={"close": True}))
        assert closed == {"Old"}
        assert skipped == set()

    def test_close_defaults_off_so_existing_clients_are_unaffected(self):
        type_map, skipped, closed = parse_account_types_form(self._form(Checking={}))
        assert closed == set()
        assert skipped == set()
        assert type_map == {"Checking": ("checking", True)}

    def test_a_closed_account_is_still_imported(self):
        """The distinction that matters: close is not a quiet skip. The account
        keeps its place in the type map, so it is created and its transactions
        arrive."""
        type_map, _, closed = parse_account_types_form(self._form(Old={"close": True}))
        assert "Old" in type_map
        assert "Old" in closed

    def test_skip_wins_when_a_caller_sends_both(self):
        """Nonsense input, but it must resolve one way rather than creating an
        account nobody asked for. A skipped account is never created, so there
        is nothing left to close."""
        type_map, skipped, closed = parse_account_types_form(
            self._form(Old={"skip": True, "close": True})
        )
        assert skipped == {"Old"}
        assert closed == set()
        assert "Old" not in type_map

    def test_an_empty_form_asks_for_nothing(self):
        assert parse_account_types_form(None) == ({}, set(), set())

    def test_an_unknown_type_is_still_rejected(self):
        with pytest.raises(HTTPException) as exc:
            parse_account_types_form(
                json.dumps({"X": {"account_type": "nonsense", "on_budget": True}})
            )
        assert exc.value.status_code == 400
