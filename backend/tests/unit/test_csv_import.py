"""Reading one account's CSV export.

The risk here is not failing to import — it is importing something other than
what the file said. A date format that fits most rows, a debit column read as
a credit, a row dropped without a word: each of those puts a wrong number in
a budget and nothing on screen says so. Hence the cases below.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.csv_import import (
    detect_date_format,
    normalize_header,
    parse_csv,
    suggest_mapping,
)


class TestHeaders:
    def test_normalizes_punctuation_and_case(self):
        assert normalize_header("  Posted_Date ") == "posted date"
        assert normalize_header("Transaction-DATE") == "transaction date"

    def test_suggests_the_obvious_columns(self):
        assert suggest_mapping(["Date", "Description", "Amount", "Memo"]) == {
            "date": "Date",
            "payee": "Description",
            "amount": "Amount",
            "memo": "Memo",
        }

    def test_prefers_the_more_specific_header(self):
        # A file with both: "transaction date" is the one that means the
        # transaction, and "date" here is likely the date it posted.
        picked = suggest_mapping(["Date", "Transaction Date", "Amount"])
        assert picked["date"] == "Transaction Date"

    def test_recognises_separate_debit_and_credit_columns(self):
        picked = suggest_mapping(["Date", "Description", "Debit", "Credit"])
        assert picked["debit"] == "Debit"
        assert picked["credit"] == "Credit"
        assert "amount" not in picked

    def test_leaves_an_unrecognised_column_alone(self):
        # A wrong guess is worse than none: a filled-in form gets skimmed.
        assert suggest_mapping(["Fecha", "Importe"]) == {}

    def test_never_assigns_one_column_to_two_fields(self):
        picked = suggest_mapping(["Name", "Amount"])
        assert list(picked.values()).count("Name") == 1


class TestDateFormat:
    def test_picks_the_format_that_reads_every_row(self):
        assert detect_date_format(["2026-01-05", "2026-02-11"]) == "%Y-%m-%d"

    def test_refuses_a_format_that_only_fits_most_rows(self):
        # 13/02 cannot be month-first. A format that parses 90% of a file is
        # wrong about the other 10%, and those rows land on invented dates.
        fmt = detect_date_format(["01/05/2026", "13/02/2026"])
        assert fmt == "%d/%m/%Y"

    def test_returns_none_when_nothing_fits(self):
        assert detect_date_format(["last tuesday"]) is None

    def test_ignores_blanks_when_sniffing(self):
        assert detect_date_format(["", "2026-03-01", "  "]) == "%Y-%m-%d"


BASIC = {"date": "Date", "payee": "Description", "amount": "Amount", "memo": "Memo"}


def rows(*records):
    return parse_csv(list(records), BASIC)


class TestParsing:
    def test_reads_a_plain_file(self):
        out = rows(
            {"Date": "2026-01-05", "Description": "Harborstone", "Amount": "-42.10", "Memo": "x"},
        )
        assert [r.amount for r in out.rows] == [Decimal("-42.10")]
        assert out.rows[0].date == date(2026, 1, 5)
        assert out.rows[0].payee == "Harborstone"
        assert out.rows[0].memo == "x"

    def test_keeps_the_sign_the_file_gave(self):
        out = rows(
            {"Date": "2026-01-05", "Description": "a", "Amount": "-10", "Memo": ""},
            {"Date": "2026-01-06", "Description": "b", "Amount": "25.50", "Memo": ""},
        )
        assert [r.amount for r in out.rows] == [Decimal("-10"), Decimal("25.50")]

    def test_blank_optional_fields_become_none(self):
        out = rows({"Date": "2026-01-05", "Description": "", "Amount": "-1", "Memo": "  "})
        assert out.rows[0].memo is None
        assert out.rows[0].payee == ""


class TestDebitAndCredit:
    MAPPING = {"date": "Date", "payee": "D", "debit": "Debit", "credit": "Credit"}

    def test_a_debit_is_money_leaving(self):
        out = parse_csv(
            [{"Date": "2026-01-05", "D": "Shop", "Debit": "42.10", "Credit": ""}], self.MAPPING
        )
        assert out.rows[0].amount == Decimal("-42.10")

    def test_a_credit_is_money_arriving(self):
        out = parse_csv(
            [{"Date": "2026-01-05", "D": "Pay", "Debit": "", "Credit": "1200"}], self.MAPPING
        )
        assert out.rows[0].amount == Decimal("1200")

    def test_a_debit_written_negative_does_not_flip_twice(self):
        # Some exports sign the debit column as well as separating it.
        out = parse_csv(
            [{"Date": "2026-01-05", "D": "Shop", "Debit": "-42.10", "Credit": ""}], self.MAPPING
        )
        assert out.rows[0].amount == Decimal("-42.10")

    def test_both_columns_filled_is_refused_not_guessed(self):
        out = parse_csv(
            [{"Date": "2026-01-05", "D": "?", "Debit": "10", "Credit": "10"}], self.MAPPING
        )
        assert out.rows == []
        assert "both a debit and a credit" in out.skipped[0].reason


class TestNothingIsDroppedSilently:
    def test_a_bad_row_is_skipped_with_a_line_and_a_reason(self):
        out = rows(
            {"Date": "2026-01-05", "Description": "ok", "Amount": "-1", "Memo": ""},
            {"Date": "", "Description": "no date", "Amount": "-1", "Memo": ""},
            {"Date": "2026-01-07", "Description": "no amount", "Amount": "", "Memo": ""},
        )
        assert len(out.rows) == 1
        assert [(s.line, s.reason) for s in out.skipped] == [(3, "no date"), (4, "empty amount")]

    def test_line_numbers_match_a_spreadsheet(self):
        # Row 1 is the header, so the first record is line 2.
        out = rows({"Date": "", "Description": "", "Amount": "", "Memo": ""})
        assert out.skipped[0].line == 2

    def test_every_row_is_accounted_for(self):
        out = rows(
            {"Date": "2026-01-05", "Description": "a", "Amount": "-1", "Memo": ""},
            {"Date": "nope", "Description": "b", "Amount": "-1", "Memo": ""},
        )
        assert out.total == 2

    def test_an_unreadable_date_column_skips_everything_rather_than_inventing(self):
        out = rows({"Date": "last tuesday", "Description": "a", "Amount": "-1", "Memo": ""})
        assert out.rows == []
        assert out.date_format is None
        assert out.skipped[0].reason == "unreadable date"


class TestWhatItRefusesToStart:
    def test_no_date_column(self):
        with pytest.raises(ValueError, match="date column"):
            parse_csv([], {"amount": "Amount"})

    def test_no_amount_column_of_any_kind(self):
        with pytest.raises(ValueError, match="amount column"):
            parse_csv([], {"date": "Date"})

    def test_debit_alone_is_enough(self):
        parse_csv([], {"date": "Date", "debit": "Debit"})
