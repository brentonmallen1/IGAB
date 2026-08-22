"""Precedence rules for Guide concept bindings.

These decide whether someone's roadmap tells them the truth, so every rule in
the module docstring gets a test — including the ones that look obvious.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from igab.guide.bindings import resolve, resolve_all


@dataclass
class Row:
    concept_key: str = "emergency_fund"
    mode: str = "manual"
    entity_type: str | None = None
    entity_id: UUID | None = None
    answer: bool | None = None
    amount: Decimal | None = None
    as_of: date | None = None
    note: str | None = None


def manual(entity_type: str = "category", entity_id: UUID | None = None, **kw) -> Row:
    return Row(mode="manual", entity_type=entity_type, entity_id=entity_id or uuid4(), **kw)


def external(amount: str | None = None, **kw) -> Row:
    return Row(mode="external", amount=Decimal(amount) if amount is not None else None, **kw)


class TestNoRows:
    def test_no_rows_is_automatic(self):
        r = resolve("emergency_fund", [])
        assert r.source == "auto"
        assert r.tracked is True
        assert r.uses_detection is True
        assert r.external_amount is None

    def test_rows_for_other_concepts_are_ignored(self):
        r = resolve("emergency_fund", [Row(concept_key="hsa", mode="dismissed")])
        assert r.source == "auto"


class TestDismissed:
    def test_dismissed_stops_tracking(self):
        r = resolve("emergency_fund", [Row(mode="dismissed")])
        assert r.source == "dismissed"
        assert r.tracked is False
        assert r.uses_detection is False

    def test_dismissed_beats_everything_else(self):
        # Leftover rows must not resurrect a claim the user switched off.
        r = resolve("emergency_fund", [manual(), external("9000"), Row(mode="dismissed")])
        assert r.source == "dismissed"
        assert r.external_amount is None
        assert r.entities == {}

    def test_dismissal_keeps_its_note(self):
        r = resolve("emergency_fund", [Row(mode="dismissed", note="not relevant to me")])
        assert r.note == "not relevant to me"


class TestAnswer:
    def test_stored_answer_is_used(self):
        r = resolve("employer_match", [Row(concept_key="employer_match", mode="answer", answer=True)])
        assert r.source == "answer"
        assert r.answer is True
        assert r.uses_detection is False

    def test_a_no_is_not_mistaken_for_unanswered(self):
        r = resolve("employer_match", [Row(concept_key="employer_match", mode="answer", answer=False)])
        assert r.source == "answer"
        assert r.answer is False

    def test_answer_row_with_no_answer_falls_back(self):
        # A stale row from an edited concept must not assert anything.
        r = resolve("employer_match", [Row(concept_key="employer_match", mode="answer", answer=None)])
        assert r.source == "auto"
        assert r.answer is None


class TestManual:
    def test_manual_entities_are_collected_by_type(self):
        cat, acct = uuid4(), uuid4()
        r = resolve("emergency_fund", [
            manual("category", cat),
            manual("account", acct),
        ])
        assert r.source == "manual"
        assert r.entities == {"category": (cat,), "account": (acct,)}
        # Detection must stop guessing once the user has pointed at something.
        assert r.uses_detection is False

    def test_several_entities_of_one_type(self):
        a, b = uuid4(), uuid4()
        r = resolve("emergency_fund", [manual("category", a), manual("category", b)])
        assert r.entities["category"] == (a, b)

    def test_incomplete_manual_rows_are_skipped(self):
        r = resolve("emergency_fund", [Row(mode="manual", entity_type="category", entity_id=None)])
        assert r.source == "auto"


class TestExternal:
    def test_external_amount_is_recorded(self):
        r = resolve("emergency_fund", [external("9000")])
        assert r.source == "external"
        assert r.external_amount == Decimal("9000")
        assert r.external_declared is True

    def test_external_without_an_amount_still_counts_as_declared(self):
        # "I have this covered" is a complete answer; demanding a figure
        # invites an invented one.
        r = resolve("emergency_fund", [external(None)])
        assert r.source == "external"
        assert r.external_declared is True
        assert r.external_amount is None

    def test_no_amount_is_not_zero(self):
        r = resolve("emergency_fund", [external(None)])
        assert r.external_amount is not Decimal("0")
        assert r.external_amount is None

    def test_several_external_rows_sum(self):
        r = resolve("emergency_fund", [external("9000"), external("1500")])
        assert r.external_amount == Decimal("10500")

    def test_external_keeps_detection_running(self):
        # Half here and half elsewhere is the ordinary case.
        r = resolve("emergency_fund", [external("9000")])
        assert r.uses_detection is True

    def test_newest_as_of_wins(self):
        r = resolve("emergency_fund", [
            external("1000", as_of=date(2026, 1, 1)),
            external("2000", as_of=date(2026, 8, 1)),
        ])
        assert r.external_as_of == date(2026, 8, 1)

    def test_as_of_survives_rows_without_one(self):
        r = resolve("emergency_fund", [external("1000"), external("2000", as_of=date(2026, 8, 1))])
        assert r.external_as_of == date(2026, 8, 1)


class TestCombined:
    def test_manual_and_external_are_additive(self):
        cat = uuid4()
        r = resolve("emergency_fund", [manual("category", cat), external("9000")])
        assert r.source == "manual+external"
        assert r.entities == {"category": (cat,)}
        assert r.external_amount == Decimal("9000")
        # Manual entities are counted by the caller, so detection stays off.
        assert r.uses_detection is False

    def test_answer_beats_manual_and_external(self):
        r = resolve("employer_match", [
            Row(concept_key="employer_match", mode="answer", answer=True),
            Row(concept_key="employer_match", mode="manual", entity_type="account", entity_id=uuid4()),
        ])
        assert r.source == "answer"


class TestResolveAll:
    def test_every_requested_key_gets_an_entry(self):
        keys = ["emergency_fund", "hsa", "employer_match"]
        out = resolve_all(keys, [external("9000")])
        assert set(out) == set(keys)
        assert out["emergency_fund"].source == "external"
        assert out["hsa"].source == "auto"

    @pytest.mark.parametrize("mode", ["manual", "external", "dismissed", "answer"])
    def test_no_mode_ever_raises(self, mode):
        # Rows can go stale as concepts and content change; resolution must
        # degrade rather than crash a whole page.
        resolve("emergency_fund", [Row(mode=mode)])
