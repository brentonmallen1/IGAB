"""A split parent's class, rolled up from its legs — one home, two readers.

`rolled_up_classes` is what the Timeline and the transaction editor's
classification both use; `TimelineTransaction` must refuse a row that forgot
to carry the answer rather than fill in "spending".
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from igab.api.v1.schemas.report import TimelineTransaction
from igab.domain.activity_class import class_label, explain, rolled_up_classes, split_reason


class TestRolledUpClasses:
    def test_one_distinct_class_is_the_parents_class(self):
        rows = [("p1", "savings"), ("p1", "savings")]
        assert rolled_up_classes(rows) == {"p1": "savings"}

    def test_legs_that_disagree_have_no_class(self):
        rows = [("p1", "savings"), ("p1", "spending"), ("p2", "income")]
        assert rolled_up_classes(rows) == {"p1": None, "p2": "income"}

    def test_a_parent_with_no_live_legs_is_absent(self):
        assert rolled_up_classes([]) == {}


class TestLabelAndReason:
    def test_a_class_reads_its_label(self):
        assert class_label("debt_principal") == "Debt payment"

    def test_no_class_reads_split(self):
        assert class_label(None) == "Split"

    def test_a_split_reason_has_copy(self):
        assert explain(split_reason("savings")) == "every line of the split counts this way"
        assert explain(split_reason(None)).startswith("its lines count in different ways")


class TestTimelineTransactionRequiresTheClass:
    """`activity_class` defaulted to "spending" and `activity_label` to
    "Spending". None now means the legs disagree, so a producer that forgot the
    keys would have drawn an all-savings split as Spending with no error."""

    BASE = {
        "id": "7a0e1f2c-3d4b-4c5d-8e6f-7a8b9c0d1e2f",
        "date": date(2026, 8, 1),
        "amount": Decimal("-900.00"),
        "payee_name": None,
        "category_name": None,
        "memo": None,
    }

    @pytest.mark.parametrize("missing", ["activity_class", "activity_label"])
    def test_a_row_without_its_class_is_refused(self, missing):
        payload = {**self.BASE, "activity_class": None, "activity_label": "Split"}
        del payload[missing]
        with pytest.raises(ValidationError):
            TimelineTransaction.model_validate(payload)

    def test_none_is_a_served_answer(self):
        payload = {**self.BASE, "activity_class": None, "activity_label": "Split"}
        assert TimelineTransaction.model_validate(payload).activity_class is None
