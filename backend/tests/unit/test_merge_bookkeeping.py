"""What a merged transaction reads, and which of its fields were a choice.

`merge_bookkeeping` is the one place this is decided: the merge writes from
it and the preview draws from it. Before it, the merge decided inline and
each of the two dialogs composed its own picture of the result on the client
— one of which showed a split's category as simply gone.

Invented rows: a grocery run entered by hand and the bank's copy of it.
"""

import uuid
from datetime import date

import pytest

from igab.domain.merging import (
    MergeKeep,
    MergeRow,
    keep_violation,
    merge_bookkeeping,
    merged_cleared,
)

GROCER, BANK_GROCER = uuid.uuid4(), uuid.uuid4()
GROCERIES, HOUSEHOLD = uuid.uuid4(), uuid.uuid4()


def row(**over) -> MergeRow:
    base = dict(
        id=uuid.uuid4(),
        date=date(2026, 11, 3),
        payee_id=GROCER,
        category_id=GROCERIES,
        memo=None,
        is_split=False,
        is_leg=False,
        reconciled=False,
    )
    return MergeRow(**{**base, **over})


class TestTheDefaultIsAdditive:
    """No picks: what a merge has always done."""

    def test_the_survivor_keeps_what_it_has(self):
        mine = row(memo="weekly shop")
        theirs = row(date=date(2026, 11, 4), payee_id=BANK_GROCER, category_id=HOUSEHOLD)
        book = merge_bookkeeping(mine, theirs)
        assert book.date.value == date(2026, 11, 3)
        assert book.payee_id.value == GROCER
        assert book.category_id.value == GROCERIES
        assert book.memo.value == "weekly shop"
        assert {book.date.source, book.payee_id.source, book.category_id.source} == {mine.id}

    def test_it_takes_what_it_lacks(self):
        mine = row(payee_id=None, category_id=None, memo=None)
        theirs = row(payee_id=BANK_GROCER, category_id=HOUSEHOLD, memo="card ending 0000")
        book = merge_bookkeeping(mine, theirs)
        assert (book.payee_id.value, book.payee_id.source) == (BANK_GROCER, theirs.id)
        assert (book.category_id.value, book.category_id.source) == (HOUSEHOLD, theirs.id)
        assert (book.memo.value, book.memo.source) == ("card ending 0000", theirs.id)
        # Nothing to choose between: only one row had a value.
        assert not (book.payee_id.choosable or book.category_id.choosable or book.memo.choosable)

    def test_two_different_memos_are_kept_whole(self):
        book = merge_bookkeeping(row(memo="weekly shop"), row(memo="incl. bags"))
        assert book.memo.value == "weekly shop — incl. bags"
        assert book.memo.source == "both"

    def test_the_same_memo_twice_is_not_doubled(self):
        book = merge_bookkeeping(row(memo="weekly shop"), row(memo="weekly shop"))
        assert book.memo.value == "weekly shop"
        assert not book.memo.choosable

    def test_neither_row_having_a_value_is_none_from_nowhere(self):
        book = merge_bookkeeping(row(payee_id=None, memo=None), row(payee_id=None, memo=None))
        assert (book.payee_id.value, book.payee_id.source) == (None, None)
        assert (book.memo.value, book.memo.source) == (None, None)


class TestWhatIsAChoice:
    def test_a_field_both_rows_have_and_disagree_on(self):
        mine = row(memo="a")
        theirs = row(date=date(2026, 11, 4), payee_id=BANK_GROCER, category_id=HOUSEHOLD, memo="b")
        book = merge_bookkeeping(mine, theirs)
        assert all(k.choosable for k in (book.date, book.payee_id, book.category_id, book.memo))

    def test_agreeing_fields_are_not(self):
        book = merge_bookkeeping(row(), row())
        assert not any(k.choosable for k in (book.date, book.payee_id, book.category_id, book.memo))

    def test_a_reconciled_survivors_date_is_the_statements(self):
        mine = row(reconciled=True)
        theirs = row(date=date(2026, 11, 4), payee_id=BANK_GROCER)
        book = merge_bookkeeping(mine, theirs, MergeKeep(date=theirs.id, payee=theirs.id))
        assert (book.date.value, book.date.choosable) == (date(2026, 11, 3), False)
        # The bookkeeping is still free on a reconciled row.
        assert (book.payee_id.value, book.payee_id.choosable) == (BANK_GROCER, True)

    def test_a_date_the_bank_already_decided_is_not_offered(self):
        theirs = row(date=date(2026, 11, 4))
        book = merge_bookkeeping(row(), theirs, MergeKeep(date=theirs.id), date_fixed=True)
        assert not book.date.choosable


class TestPicks:
    def test_each_field_is_picked_on_its_own(self):
        mine = row(memo="a")
        theirs = row(date=date(2026, 11, 4), payee_id=BANK_GROCER, category_id=HOUSEHOLD, memo="b")
        book = merge_bookkeeping(mine, theirs, MergeKeep(payee=theirs.id, memo=mine.id))
        assert (book.payee_id.value, book.payee_id.source) == (BANK_GROCER, theirs.id)
        assert (book.memo.value, book.memo.source) == ("a", mine.id)
        # Unpicked fields stay the survivor's.
        assert book.date.value == date(2026, 11, 3)
        assert book.category_id.value == GROCERIES

    def test_the_other_rows_memo_alone(self):
        mine, theirs = row(memo="a"), row(memo="b")
        assert merge_bookkeeping(mine, theirs, MergeKeep(memo=theirs.id)).memo.value == "b"
        assert merge_bookkeeping(mine, theirs, MergeKeep(memo="both")).memo.value == "a — b"

    def test_a_pick_for_a_field_that_is_no_choice_changes_nothing(self):
        mine = row(payee_id=GROCER)
        theirs = row(payee_id=None)
        book = merge_bookkeeping(mine, theirs, MergeKeep(payee=theirs.id))
        assert book.payee_id.value == GROCER, "a pick never blanks a value"

    def test_a_pick_must_name_one_of_the_pair(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        assert keep_violation(MergeKeep(date=a, memo="both"), a, b) is None
        assert keep_violation(MergeKeep(), a, b) is None
        assert "payee" in keep_violation(MergeKeep(payee=uuid.uuid4()), a, b)
        assert "date" in keep_violation(MergeKeep(date=uuid.uuid4()), a, b)


class TestSplits:
    """A split's categories live on its lines, which always carry over."""

    def test_a_split_survivor_offers_no_category_and_no_date(self):
        mine = row(is_split=True, category_id=None)
        theirs = row(date=date(2026, 11, 4), category_id=HOUSEHOLD, payee_id=BANK_GROCER)
        book = merge_bookkeeping(mine, theirs, MergeKeep(category=theirs.id, date=theirs.id))
        assert (book.category_id.value, book.category_id.choosable) == (None, False)
        assert book.category_id.source == mine.id, "the lines are the split's"
        assert (book.date.value, book.date.choosable) == (date(2026, 11, 3), False)
        # The payee is still a choice.
        assert book.payee_id.choosable

    def test_a_split_being_taken_in_keeps_its_lines_over_a_plain_category(self):
        """The reconciled bank row meeting the receipt someone itemised."""
        mine = row(reconciled=True, category_id=GROCERIES)
        theirs = row(is_split=True, category_id=None)
        book = merge_bookkeeping(mine, theirs, MergeKeep(category=mine.id))
        assert (book.category_id.value, book.category_id.source) == (None, theirs.id)
        assert not book.category_id.choosable


class TestTransferLegs:
    def test_a_leg_keeps_its_payee_and_category_even_none(self):
        mine = row(is_leg=True, category_id=None)
        theirs = row(payee_id=BANK_GROCER, category_id=HOUSEHOLD, date=date(2026, 11, 4))
        book = merge_bookkeeping(
            mine, theirs, MergeKeep(payee=theirs.id, category=theirs.id, date=theirs.id)
        )
        assert (book.payee_id.value, book.payee_id.choosable) == (GROCER, False)
        assert (book.category_id.value, book.category_id.choosable) == (None, False)
        assert (book.date.value, book.date.choosable) == (date(2026, 11, 3), False)

    def test_a_legs_memo_is_still_a_choice(self):
        mine, theirs = row(is_leg=True, memo="a"), row(memo="b")
        assert merge_bookkeeping(mine, theirs, MergeKeep(memo=theirs.id)).memo.value == "b"

    def test_a_row_becoming_a_leg_takes_what_it_lacks_but_offers_nothing(self):
        mine = row(category_id=None)
        theirs = row(payee_id=BANK_GROCER, category_id=HOUSEHOLD)
        book = merge_bookkeeping(mine, theirs, MergeKeep(payee=theirs.id), becomes_leg=True)
        assert (book.payee_id.value, book.payee_id.choosable) == (GROCER, False)
        assert (book.category_id.value, book.category_id.choosable) == (HOUSEHOLD, False)


class TestClearedStatus:
    @pytest.mark.parametrize(
        ("survivor", "deleted", "expected"),
        [
            ("uncleared", "cleared", "cleared"),
            ("cleared", "uncleared", "cleared"),
            ("cleared", "reconciled", "reconciled"),
            ("reconciled", "cleared", "reconciled"),
            ("uncleared", "reconciled", "reconciled"),
            # A hold has not posted: it stands where an uncleared row does,
            # and a tie is the survivor's.
            ("uncleared", "pending", "uncleared"),
            ("pending", "uncleared", "pending"),
            ("pending", "cleared", "cleared"),
            ("cleared", "pending", "cleared"),
        ],
    )
    def test_the_further_along_of_the_two(self, survivor, deleted, expected):
        assert merged_cleared(survivor, deleted) == expected
