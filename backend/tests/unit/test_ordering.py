"""domain.ordering — the one rule for reordering a list the user arranges.

Groups and categories both go through `merge_reorder`; the cases here are the
ones the group reorder used to pin on its own, plus the one hiding the Income
group added: a system group the grid never draws may be left out of the list.
"""

from uuid import uuid4

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.domain.ordering import merge_reorder, renumber


class TestMergeReorder:
    def test_a_full_list_is_taken_as_given(self):
        a, b, c = uuid4(), uuid4(), uuid4()
        live = [(a, False), (b, False), (c, False)]
        assert merge_reorder(live, [c, a, b], noun="group") == [c, a, b]

    def test_an_omitted_hidden_row_keeps_its_slot(self):
        """Re-showing it later must find it where the user left it."""
        a, b, c = uuid4(), uuid4(), uuid4()
        live = [(a, False), (b, True), (c, False)]
        assert merge_reorder(live, [c, a], noun="group") == [c, b, a]

    def test_an_omitted_system_group_keeps_its_slot(self):
        """The grid does not draw the Income group, so it cannot list it; the
        caller marks it omittable and the merge treats it like a hidden one."""
        income, bills, wants = uuid4(), uuid4(), uuid4()
        live = [(income, True), (bills, False), (wants, False)]
        assert merge_reorder(live, [wants, bills], noun="group") == [income, wants, bills]

    def test_an_omittable_row_may_still_be_listed(self):
        """Show-hidden mode sends the full list; that keeps working."""
        a, b, c = uuid4(), uuid4(), uuid4()
        live = [(a, True), (b, False), (c, False)]
        assert merge_reorder(live, [b, a, c], noun="group") == [b, a, c]

    def test_a_duplicate_is_refused(self):
        a, b = uuid4(), uuid4()
        with pytest.raises(InvariantViolation, match="at most once"):
            merge_reorder([(a, False), (b, False)], [a, a], noun="group")

    def test_an_unknown_id_is_refused(self):
        a, b = uuid4(), uuid4()
        with pytest.raises(InvariantViolation, match="this budget does not have"):
            merge_reorder([(a, False), (b, False)], [a, b, uuid4()], noun="group")

    def test_a_missing_required_row_is_refused(self):
        """The stale client — a row added in another tab — fails loudly."""
        a, b, c = uuid4(), uuid4(), uuid4()
        with pytest.raises(InvariantViolation, match="visible groups"):
            merge_reorder([(a, False), (b, False), (c, False)], [c, a], noun="group")

    def test_the_messages_name_the_list_they_are_about(self):
        a, b = uuid4(), uuid4()
        live = [(a, False), (b, False)]
        with pytest.raises(InvariantViolation, match="this group's visible categories"):
            merge_reorder(live, [a], noun="category", plural="categories", scope="group")
        with pytest.raises(InvariantViolation, match="a category this group does not have"):
            merge_reorder(
                live, [a, b, uuid4()], noun="category", plural="categories", scope="group"
            )

    def test_an_empty_list_reorders_nothing_when_everything_is_omittable(self):
        a = uuid4()
        assert merge_reorder([(a, True)], [], noun="group") == [a]


class TestRenumber:
    def test_contiguous_and_order_preserving(self):
        a, b, c = uuid4(), uuid4(), uuid4()
        assert renumber([c, a, b]) == {c: 0, a: 1, b: 2}

    def test_empty(self):
        assert renumber([]) == {}
