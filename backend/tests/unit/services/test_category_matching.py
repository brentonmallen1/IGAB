"""Tolerant AI category-name matching.

Models clean up the names they were shown — "Tech {$10}*" comes back as
"Tech" — and may group-qualify ambiguous names. Matching must recover the
real category without ever guessing between two that stay ambiguous.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from igab.services.ai_draft_service import AIDraftService, parse_extraction
from igab.services.category_matching import (
    canonical_label,
    match_category,
    normalize_category_name,
)

TODAY = date(2026, 8, 16)


class TestNormalize:
    def test_strips_funding_decorations(self):
        assert normalize_category_name("Tech {$10}*") == "tech"
        assert normalize_category_name("Student Loans {$457}") == "student loans"

    def test_collapses_whitespace_and_casefolds(self):
        assert normalize_category_name("  Student   LOANS ") == "student loans"

    def test_plain_name_unchanged_but_casefolded(self):
        assert normalize_category_name("Groceries") == "groceries"


class TestMatchCategory:
    CANDIDATES = [
        ("Tech {$10}*", "Fun"),
        ("Groceries {$800}", "Food"),
        ("VizualVibes (mentorship)", "Fun"),
        ("Gifts", "Household"),
        ("Gifts", "Alex"),
    ]

    def test_exact_match(self):
        assert match_category("Tech {$10}*", self.CANDIDATES) == 0

    def test_case_insensitive(self):
        assert match_category("tech {$10}*", self.CANDIDATES) == 0

    def test_model_cleaned_name_matches_decorated_category(self):
        assert match_category("Tech", self.CANDIDATES) == 0
        assert match_category("groceries", self.CANDIDATES) == 1

    def test_literal_parens_in_name_match_exactly(self):
        assert match_category("VizualVibes (mentorship)", self.CANDIDATES) == 2

    def test_group_qualified_resolves_duplicates(self):
        assert match_category("Gifts (Household)", self.CANDIDATES) == 3
        assert match_category("gifts (alex)", self.CANDIDATES) == 4

    def test_bare_duplicate_name_never_guesses(self):
        assert match_category("Gifts", self.CANDIDATES) is None

    def test_qualified_and_decorated(self):
        assert match_category("Tech (Fun)", self.CANDIDATES) == 0

    def test_invented_name_is_none(self):
        assert match_category("Shipping", self.CANDIDATES) is None

    def test_empty_and_none_are_none(self):
        assert match_category(None, self.CANDIDATES) is None
        assert match_category("", self.CANDIDATES) is None
        assert match_category("   ", self.CANDIDATES) is None

    def test_exact_beats_normalized(self):
        candidates = [("Tech", "A"), ("Tech {$10}", "B")]
        assert match_category("Tech", candidates) == 0
        assert match_category("Tech {$10}", candidates) == 1

    def test_normalized_collision_is_ambiguous(self):
        candidates = [("Tech {$10}", "A"), ("Tech {$20}", "B")]
        assert match_category("Tech", candidates) is None
        assert match_category("Tech (A)", candidates) == 0


class TestCanonicalLabel:
    def test_unique_name_stays_bare(self):
        candidates = [("Tech {$10}*", "Fun"), ("Gifts", "Household")]
        assert canonical_label(0, candidates) == "Tech {$10}*"

    def test_duplicated_name_gets_group_qualifier(self):
        candidates = [("Gifts", "Household"), ("Gifts", "Alex")]
        assert canonical_label(0, candidates) == "Gifts (Household)"
        assert canonical_label(1, candidates) == "Gifts (Alex)"


class TestParseExtractionMatching:
    CATEGORIES = [
        ("Tech {$10}*", "Fun"),
        ("Shipping {$10}", "Bills"),
        ("Gifts", "A"),
        ("Gifts", "B"),
    ]

    def receipt(self, **overrides) -> dict:
        base = {"payee": "Store", "total": 20.0, "date": "2026-08-10", "category": None}
        base.update(overrides)
        return base

    def test_cleaned_category_canonicalized_to_real_name(self):
        draft = parse_extraction(
            self.receipt(category="Tech"),
            kind="receipt",
            client_today=TODAY,
            category_names=self.CATEGORIES,
        )
        assert draft.category_name == "Tech {$10}*"

    def test_ambiguous_category_dropped(self):
        draft = parse_extraction(
            self.receipt(category="Gifts"),
            kind="receipt",
            client_today=TODAY,
            category_names=self.CATEGORIES,
        )
        assert draft.category_name is None

    def test_qualified_duplicate_gets_qualified_label(self):
        draft = parse_extraction(
            self.receipt(category="Gifts (B)"),
            kind="receipt",
            client_today=TODAY,
            category_names=self.CATEGORIES,
        )
        assert draft.category_name == "Gifts (B)"

    def test_split_lines_canonicalized(self):
        raw = self.receipt(
            total=57.0,
            category="Tech",
            suggested_split=[
                {"category": "Tech", "amount": 10.0},
                {"category": "Shipping", "amount": 47.0},
            ],
        )
        draft = parse_extraction(
            raw, kind="receipt", client_today=TODAY, category_names=self.CATEGORIES
        )
        assert draft.suggested_split is not None
        assert [s.category_name for s in draft.suggested_split] == [
            "Tech {$10}*",
            "Shipping {$10}",
        ]

    def test_split_with_unmatchable_line_rejected(self):
        raw = self.receipt(
            total=57.0,
            suggested_split=[
                {"category": "Tech", "amount": 10.0},
                {"category": "Handling", "amount": 47.0},
            ],
        )
        draft = parse_extraction(
            raw, kind="receipt", client_today=TODAY, category_names=self.CATEGORIES
        )
        assert draft.suggested_split is None

    def test_bare_string_names_still_supported(self):
        draft = parse_extraction(
            self.receipt(category="groceries"),
            kind="receipt",
            client_today=TODAY,
            category_names={"Groceries", "Rent"},
        )
        assert draft.category_name == "Groceries"


class TestResolveCategory:
    def service_with(self, pairs) -> AIDraftService:
        txn_svc = MagicMock()
        txn_svc.category_repo.get_all_with_group_names = AsyncMock(return_value=pairs)
        return AIDraftService(txn_svc)

    def category(self, name: str) -> MagicMock:
        cat = MagicMock()
        cat.name = name
        cat.id = uuid.uuid4()
        return cat

    async def test_decorated_name_resolves_from_cleaned_output(self):
        cat = self.category("Tech {$10}*")
        svc = self.service_with([(cat, "Fun")])
        assert await svc.resolve_category(uuid.uuid4(), "Tech") == cat.id

    async def test_ambiguous_bare_name_resolves_to_none(self):
        a, b = self.category("Gifts"), self.category("Gifts")
        svc = self.service_with([(a, "Household"), (b, "Alex")])
        assert await svc.resolve_category(uuid.uuid4(), "Gifts") is None

    async def test_qualified_name_picks_right_group(self):
        a, b = self.category("Gifts"), self.category("Gifts")
        svc = self.service_with([(a, "Household"), (b, "Alex")])
        assert await svc.resolve_category(uuid.uuid4(), "Gifts (Alex)") == b.id

    async def test_no_match_resolves_to_none(self):
        cat = self.category("Groceries")
        svc = self.service_with([(cat, "Food")])
        assert await svc.resolve_category(uuid.uuid4(), "Restaurants") is None
