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

from igab.api.v1.imports import (
    assign_related_groups,
    build_ynab_preview,
    parse_account_types_form,
)
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


class TestRelatedAccounts:
    """Grouping is a prompt to compare, never a merge suggestion.

    Measured on the real export, `rapidfuzz.token_set_ratio` scores 100 for
    "vehicle a" vs "vehicle a loan", "redwood" vs "redwood cc" and
    "harborstone" vs "harborstone savings" — every pair a legitimately
    distinct account. A dedupe feature built on similarity would have told
    the user to destroy real data. A shared leading fragment claims much
    less: these are probably about the same thing, look at them together.
    """

    def _groups(self, *names: str) -> dict[str, str | None]:
        return assign_related_groups(list(names))

    def test_an_asset_groups_with_the_debt_against_it(self):
        """The pair worth putting side by side — comparing their balances is
        how a $27,704 vehicle typed as an auto loan gets noticed."""
        g = self._groups("Vehicle A", "Vehicle A Loan")
        assert g["Vehicle A"] == g["Vehicle A Loan"] == "Vehicle A"

    def test_the_longest_shared_prefix_wins(self):
        """Vehicle A and Vehicle B are different vehicles. Grouping on the
        first token alone would pile all four into one 'Vehicle' bucket and
        lose the pairing that matters."""
        g = self._groups("Vehicle A", "Vehicle A Loan", "Vehicle B", "Vehicle B Loan")
        assert g["Vehicle A"] == g["Vehicle A Loan"] == "Vehicle A"
        assert g["Vehicle B"] == g["Vehicle B Loan"] == "Vehicle B"

    def test_an_institution_keeps_its_accounts_together(self):
        g = self._groups("Redwood", "Redwood CC", "Redwood MM", "Redwood Savings")
        assert set(g.values()) == {"Redwood"}

    def test_two_employers_do_not_merge(self):
        """The reason the cap is not one token: at one, these nine accounts
        become a single 'Employer' pile."""
        g = self._groups(
            "Employer A 401k", "Employer A Stock", "Employer B 401k", "Employer B Co-invest"
        )
        assert g["Employer A 401k"] == g["Employer A Stock"] == "Employer A"
        assert g["Employer B 401k"] == g["Employer B Co-invest"] == "Employer B"

    def test_one_employer_does_not_shatter_into_product_lines(self):
        """The reason the cap exists at all: unbounded, the longest shared
        prefix splits one employer into ESPP, HSA and a remainder."""
        g = self._groups(
            "Employer A ESPP Cash",
            "Employer A ESPP Stock",
            "Employer A HSA Bank",
            "Employer A HSA Fidelity",
            "Employer A 401k",
        )
        assert set(g.values()) == {"Employer A"}

    def test_a_name_shared_by_nobody_is_not_grouped(self):
        g = self._groups("Cash", "Crypto", "TreasuryDirect")
        assert set(g.values()) == {None}

    def test_a_single_account_is_never_a_group_of_one(self):
        assert self._groups("Redwood") == {"Redwood": None}

    def test_the_label_keeps_the_source_casing(self):
        """Title-casing the matched fragment would render this 'Brightpath
        Hsa'. The label is sliced from a member's own name instead."""
        g = self._groups("Brightpath HSA", "Brightpath HSA Investment")
        assert set(g.values()) == {"Brightpath HSA"}

    def test_matching_ignores_case_and_punctuation(self):
        g = self._groups("Employer B 401k - fidelity", "employer b 401k - insperity")
        assert len(set(g.values())) == 1
        assert None not in g.values()

    def test_grouping_reaches_the_preview(self):
        accounts = _preview(
            _txn("Redwood", date(2020, 1, 1)),
            _txn("Redwood CC", date(2020, 1, 1)),
            _txn("Cash", date(2020, 1, 1)),
        )
        assert accounts["Redwood"].related_group == "Redwood"
        assert accounts["Redwood CC"].related_group == "Redwood"
        assert accounts["Cash"].related_group is None
