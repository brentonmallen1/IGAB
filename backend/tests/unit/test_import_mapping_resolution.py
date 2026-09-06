"""The one ladder from three sources to what the mapping step shows.

`build_ynab_preview` used to choose between an Accounts.csv member and a guess
read from the account's name with an `if` in the router. Remembering a person's
last import made that three sources, and the cases below are the divergences
that a third `elif` would have got wrong — each named for what it protects.
"""

from decimal import Decimal

import pytest

from igab.domain.import_mapping import (
    ExportedAccount,
    RememberedChoice,
    _normalize_for_match,
    account_key,
    resolve_account_suggestion,
)

POS = Decimal("1200.00")
NEG = Decimal("-18400.00")


def remembered(**kwargs) -> RememberedChoice:
    base = {"account_type": "checking", "on_budget": True, "skip": False, "close": False}
    return RememberedChoice(**{**base, **kwargs})


class TestWhatAnAccountIs:
    def test_the_export_outranks_memory(self):
        """An IGAB export states the account's stored type. A memory is a
        record of a keystroke about it."""
        s = resolve_account_suggestion(
            "Cascade Point HYSA",
            POS,
            from_export=ExportedAccount(account_type="savings", on_budget=True),
            remembered=remembered(account_type="cash"),
        )
        assert (s.account_type, s.source) == ("savings", "export")

    def test_memory_outranks_the_heuristic(self):
        """The whole feature: a name the guesser reads as `checking` stays
        whatever the person said it was last time."""
        s = resolve_account_suggestion(
            "Northwind Holdings",
            POS,
            remembered=remembered(account_type="investment", on_budget=False),
        )
        assert (s.account_type, s.on_budget, s.source) == ("investment", False, "remembered")

    def test_the_heuristic_is_the_floor(self):
        s = resolve_account_suggestion("Harborstone Mortgage", NEG)
        assert (s.account_type, s.on_budget, s.source) == ("mortgage", False, "heuristic")


class TestWhatToDoWithIt:
    def test_memory_outranks_the_export_for_the_disposition(self):
        """The case a single ladder gets wrong. An IGAB export carries an
        Accounts.csv row for *every* account it contains, so one ladder would
        let the export outrank a remembered skip — and someone who said "leave
        this one out" twice would get it imported on the third try."""
        s = resolve_account_suggestion(
            "Old Harborstone Checking",
            POS,
            from_export=ExportedAccount(account_type="checking", on_budget=True, is_closed=False),
            remembered=remembered(skip=True),
        )
        # The export still supplies the type it genuinely knows...
        assert (s.account_type, s.source) == ("checking", "export")
        # ...and the memory supplies the disposition it genuinely knows.
        assert s.skip is True

    def test_the_export_closed_column_survives_a_re_import(self):
        """budget_export writes `Closed` and the reader ignored it, so every
        account someone had closed came back open."""
        s = resolve_account_suggestion(
            "Sapphire Visa",
            NEG,
            from_export=ExportedAccount(account_type="credit_card", on_budget=True, is_closed=True),
        )
        assert (s.skip, s.close) == (False, True)

    def test_nothing_is_skipped_or_closed_by_default(self):
        s = resolve_account_suggestion("Harborstone Checking", POS)
        assert (s.skip, s.close) == (False, False)

    def test_a_remembered_skip_and_close_cannot_both_survive(self):
        """Same rule as the picker's: a skipped account is never created, so
        there is nothing left to close."""
        s = resolve_account_suggestion(
            "Old Sapphire Visa", NEG, remembered=remembered(skip=True, close=True)
        )
        assert (s.skip, s.close) == (True, False)


class TestTheCheckBadge:
    def test_remembering_a_choice_does_not_silence_it(self):
        """The safety property. "We could not read this name" stays true no
        matter how many times the form has been submitted with the pre-filled
        guess left untouched — and an account wrongly left ON budget throws off
        every total in the budget."""
        s = resolve_account_suggestion("Birchwood Property Ferry", POS, remembered=remembered())
        assert s.needs_review is True
        assert s.source == "remembered"

    def test_the_export_does_silence_it(self):
        """Pinned beside the case above so the difference reads as deliberate:
        the export is stating the type, not guessing at it."""
        s = resolve_account_suggestion(
            "Birchwood Property Ferry",
            POS,
            from_export=ExportedAccount(account_type="other_asset", on_budget=False),
        )
        assert s.needs_review is False

    def test_a_readable_name_needs_no_review_either_way(self):
        assert resolve_account_suggestion("Harborstone Checking", POS).needs_review is False


class TestVersionDrift:
    def test_a_remembered_type_that_is_no_longer_built_in_falls_back_to_the_name(self):
        """`d2e6a9c53b71` changed the account-type key set once already.
        Serving a key the picker has no option for renders the *first* option
        while the form still holds the unknown string — so the person imports
        `checking` believing they chose otherwise."""
        s = resolve_account_suggestion(
            "Harborstone Mortgage", NEG, remembered=remembered(account_type="yacht")
        )
        assert (s.account_type, s.source) == ("mortgage", "heuristic")

    def test_and_its_disposition_goes_with_it(self):
        """A choice we will not honour the type of is not a choice we can
        honour the skip of either — half a remembered row is worse than none."""
        s = resolve_account_suggestion(
            "Harborstone Mortgage", NEG, remembered=remembered(account_type="yacht", skip=True)
        )
        assert s.skip is False


class TestAccountKey:
    @pytest.mark.parametrize(
        "a,b",
        [("Harborstone Checking", "harborstone checking"), ("  Sapphire Visa ", "Sapphire Visa")],
    )
    def test_the_same_account_spelled_differently(self, a, b):
        assert account_key(a) == account_key(b)

    def test_it_is_identity_not_matching(self):
        """`_normalize_for_match` also lowercases, and reusing it as the key
        would fold two accounts the importer creates separately into one
        memory."""
        assert account_key("Vehicle-A") != account_key("Vehicle A")
        assert _normalize_for_match("Vehicle-A") == _normalize_for_match("Vehicle A")
