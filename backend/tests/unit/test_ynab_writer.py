"""The writers are the inverses of the readers, and that is pinned here.

Every function in `integrations/ynab/writer.py` exists because its reader
exists in `parser.py`. A format written in one file and parsed in another
drifts the first time someone "fixes" one of them — so these round-trip
through the parser's own functions rather than comparing format strings.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.money import format_csv_amount, parse_csv_amount
from igab.integrations.ynab.parser import (
    _CLEARED_MAP,
    _parse_date,
    _parse_month,
    _SPLIT_MEMO_RE,
)
from igab.integrations.ynab.writer import (
    CLEARED_LABELS,
    format_cleared,
    format_date,
    format_month,
    group_category,
    split_memo,
    transfer_payee,
    write_csv,
)


class TestMoneyRoundTrips:
    @pytest.mark.parametrize(
        "amount",
        [
            Decimal("0.00"),
            Decimal("0.01"),
            Decimal("-0.01"),
            Decimal("12.34"),
            Decimal("-12.34"),
            Decimal("1234.56"),
            Decimal("-1234.56"),
            # Above a thousand on purpose: a writer that added separators
            # would still look right and would no longer read back.
            Decimal("1234567.89"),
            Decimal("-1234567.89"),
        ],
    )
    def test_an_amount_survives_the_trip(self, amount):
        assert parse_csv_amount(format_csv_amount(amount)) == amount

    def test_no_thousands_separator_is_written(self):
        """parse_csv_amount rejects a comma followed by 1-2 digits as an
        ambiguous European decimal. Writing separators at all invites that."""
        assert format_csv_amount(Decimal("1234567.89")) == "1234567.89"

    def test_no_currency_symbol_is_written(self):
        assert "$" not in format_csv_amount(Decimal("5.00"))

    def test_fractional_cents_are_rounded_not_written(self):
        """Numeric(19,4) holds four places; a CSV cell shows two, and the
        rounding is the one the rest of the app uses."""
        assert format_csv_amount(Decimal("1.005")) == "1.00"  # half-even
        assert format_csv_amount(Decimal("1.015")) == "1.02"


class TestDatesRoundTrip:
    @pytest.mark.parametrize(
        "value",
        [date(2026, 1, 1), date(2026, 8, 29), date(2026, 12, 31), date(1999, 3, 7)],
    )
    def test_a_date_survives_the_trip(self, value):
        assert _parse_date(format_date(value)) == value

    @pytest.mark.parametrize(
        "value", [date(2026, 1, 1), date(2026, 6, 1), date(2026, 12, 1), date(2020, 7, 1)]
    )
    def test_a_month_survives_the_trip(self, value):
        assert _parse_month(format_month(value)) == value

    def test_every_month_of_a_year_survives(self):
        for month in range(1, 13):
            value = date(2026, month, 1)
            assert _parse_month(format_month(value)) == value


class TestClearedRoundTrips:
    @pytest.mark.parametrize("state", ["uncleared", "cleared", "reconciled"])
    def test_a_state_survives_the_trip(self, state):
        assert _CLEARED_MAP[format_cleared(state)] == state

    def test_the_two_vocabularies_are_the_same_size(self):
        """CLEARED_LABELS is written out rather than derived; this is what
        holds it to the map it inverts."""
        assert set(CLEARED_LABELS.values()) == set(_CLEARED_MAP)
        assert set(CLEARED_LABELS) == set(_CLEARED_MAP.values())

    def test_an_unknown_state_falls_back_rather_than_raising(self):
        assert format_cleared("something-new") == "Uncleared"


class TestMarkers:
    def test_a_split_memo_reads_back(self):
        memo = split_memo(2, 3, "Groceries and sundries")
        match = _SPLIT_MEMO_RE.match(memo)
        assert match is not None
        assert (int(match.group(1)), int(match.group(2))) == (2, 3)
        assert match.group(3).strip() == "Groceries and sundries"

    def test_a_split_leg_with_no_memo_still_marks_itself(self):
        memo = split_memo(1, 2, None)
        match = _SPLIT_MEMO_RE.match(memo)
        assert match is not None
        assert match.group(3).strip() == ""

    def test_a_transfer_payee_is_the_shape_the_importer_looks_for(self):
        assert transfer_payee("Cascade Point HYSA") == "Transfer : Cascade Point HYSA"

    def test_the_combined_column_needs_both_halves(self):
        assert group_category("Everyday", "Groceries") == "Everyday: Groceries"
        assert group_category(None, "Groceries") == ""
        assert group_category("Everyday", None) == ""


class TestCsv:
    def test_the_header_is_written_even_with_no_rows(self):
        out = write_csv(("A", "B"), [])
        assert out.splitlines()[0] == "A,B"

    def test_missing_keys_are_blank_rather_than_absent(self):
        out = write_csv(("A", "B"), [{"A": "1"}])
        assert out.splitlines()[1] == "1,"

    def test_a_comma_in_a_value_is_quoted(self):
        out = write_csv(("A",), [{"A": "Nordstrom, Seattle"}])
        assert '"Nordstrom, Seattle"' in out
