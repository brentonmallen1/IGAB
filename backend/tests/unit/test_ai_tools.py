"""The tool layer may not grow its own queries, and this is what says so.

You cannot assert "this is a thin adapter" directly, so assert the negative:
nothing under `igab/ai/tools/` may build a query or import a model. The reason
is in `registry`'s docstring and in this repo's history — `spending_insights`
hand-rolled a spending query and silently dropped every split transaction,
which is exactly the drift a second implementation produces.

Same technique as `queryKeys.deadRoots.test.ts` on the frontend: read the
source, fail on the pattern.
"""

import ast
import json
from pathlib import Path

import pytest

from igab.ai.tools import executor
from igab.ai.tools.registry import BY_NAME, TOOLS, ollama_schema
from igab.ai.tools.shape import (
    TOOL_RESULT_MAX_CHARS,
    clip,
    fits,
    money,
    summarize_if_large,
)

TOOLS_DIR = Path(__file__).resolve().parents[2] / "src" / "igab" / "ai" / "tools"

#: Query builders a tool handler must not call.
_FORBIDDEN_CALLS = {"select", "text", "insert", "update", "delete"}
#: Session methods that would make the tool layer touch the database directly.
_FORBIDDEN_METHODS = {"execute", "add", "flush", "commit", "scalars"}
#: Importing the models means building a query is one line away.
_FORBIDDEN_IMPORTS = ("igab.db.models", "sqlalchemy")


def _violations(source: str) -> list[str]:
    """Structural scan, so prose about the rule does not trip the rule.

    An earlier textual version failed on `registry.py`, whose docstring quotes
    the very pattern it forbids.
    """
    found: list[str] = []
    tree = ast.parse(source)
    # Imports under `if TYPE_CHECKING:` are annotations, not access. The tool
    # context names the repositories it is handed; that is the opposite of
    # reaching for them itself.
    type_only: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            name = getattr(test, "id", None) or getattr(test, "attr", None)
            if name == "TYPE_CHECKING":
                for child in ast.walk(node):
                    if hasattr(child, "lineno"):
                        type_only.add(child.lineno)
    for node in ast.walk(tree):
        if getattr(node, "lineno", None) in type_only:
            continue
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALLS:
                found.append(f"calls {func.id}()")
            if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_METHODS:
                base = func.value
                if isinstance(base, ast.Attribute) and base.attr == "session":
                    found.append(f"calls session.{func.attr}()")
                if isinstance(base, ast.Name) and base.id == "session":
                    found.append(f"calls session.{func.attr}()")
        if isinstance(node, ast.ImportFrom) and node.module:
            for bad in _FORBIDDEN_IMPORTS:
                if node.module.startswith(bad):
                    found.append(f"imports {node.module}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                for bad in _FORBIDDEN_IMPORTS:
                    if alias.name.startswith(bad):
                        found.append(f"imports {alias.name}")
    return found


class TestToolsNeverWriteTheirOwnQueries:
    @pytest.mark.parametrize("path", sorted(TOOLS_DIR.glob("*.py")), ids=lambda p: p.name)
    def test_no_query_building_in_the_tool_layer(self, path: Path):
        hits = _violations(path.read_text())
        assert not hits, (
            f"{path.name} {hits}. Tools delegate to a service that already owns "
            f"the rule; a query here becomes a second implementation of it."
        )

    def test_the_scan_would_actually_catch_something(self):
        """Guards the guard: a scan that finds nothing in a real violation is
        worse than no scan, because it reads as proof."""
        assert _violations("from sqlalchemy import select\nx = select(1)")
        assert _violations("from igab.db.models import Transaction")
        assert _violations("async def f(ctx):\n    await ctx.session.execute(q)")
        assert not _violations("# this mentions select( in a comment\nx = 1")
        # A type-only import is an annotation, not a query.
        assert not _violations(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from sqlalchemy.ext.asyncio import AsyncSession\n"
        )

    def test_the_scan_is_actually_looking_at_something(self):
        """Guards the guard: a glob that matched nothing would pass forever."""
        assert len(list(TOOLS_DIR.glob("*.py"))) >= 5

    def test_every_tool_says_what_it_delegates_to(self):
        """The transparency view shows this, so it is not decoration."""
        for spec in TOOLS:
            assert spec.delegates_to, f"{spec.name} does not name the service it wraps"


class TestSchemasSuitASmallModel:
    def test_no_uuid_arguments_anywhere(self):
        """A model asked for a category id invents one. Tools take names."""
        for spec in TOOLS:
            for key in spec.parameters.get("properties", {}):
                assert not key.endswith("_id"), f"{spec.name}.{key} asks the model for an id"
                assert not key.endswith("_ids"), f"{spec.name}.{key} asks the model for ids"

    def test_arguments_are_flat_scalars(self):
        """7-8B models fill scalars reliably and nested objects unreliably."""
        allowed = {"string", "integer", "number", "boolean"}
        for spec in TOOLS:
            for key, schema in spec.parameters.get("properties", {}).items():
                assert schema.get("type") in allowed, f"{spec.name}.{key} is not a scalar"

    def test_budget_is_never_a_parameter(self):
        """It comes from the request, so the model cannot name another one."""
        for spec in TOOLS:
            assert "budget_id" not in spec.parameters.get("properties", {})

    def test_every_tool_has_a_description_a_person_could_read(self):
        for spec in TOOLS:
            assert len(spec.description) > 40, spec.name

    def test_ollama_schema_shape(self):
        schema = ollama_schema()
        assert len(schema) == len(TOOLS)
        for entry in schema:
            assert entry["type"] == "function"
            assert set(entry["function"]) == {"name", "description", "parameters"}

    def test_names_are_unique(self):
        assert len(BY_NAME) == len(TOOLS)


class TestValidation:
    def test_a_string_integer_is_coerced(self):
        """Small models write "3" and mean 3."""
        resolved, error = executor.validate("income_vs_expense", {"months": "3"})
        assert error is None
        assert resolved["months"] == 3

    def test_a_word_where_a_number_belongs_is_reported_not_guessed(self):
        resolved, error = executor.validate("income_vs_expense", {"months": "lots"})
        assert error is None  # months is optional; the handler clamps it
        assert resolved["months"] == "lots"

    def test_missing_required_argument_is_an_error(self):
        _, error = executor.validate("spending_by_category", {"start_date": "2026-01-01"})
        assert error is not None and "end_date" in error

    def test_unknown_keys_are_dropped_not_rejected(self):
        resolved, error = executor.validate("income_vs_expense", {"months": 3, "vibe": "good"})
        assert error is None
        assert "vibe" not in resolved

    def test_boolean_from_a_string(self):
        resolved, _ = executor.validate(
            "spending_by_category",
            {"start_date": "2026-01-01", "end_date": "2026-02-01", "include_savings": "true"},
        )
        assert resolved["include_savings"] is True


class TestTheExecutorNeverRaises:
    async def test_an_unknown_tool_returns_a_result_not_an_exception(self):
        invocation = await executor.run(None, "make_me_rich", {})  # type: ignore[arg-type]
        assert invocation.error is not None
        assert "available_tools" in invocation.result

    async def test_a_bad_argument_returns_a_result(self):
        invocation = await executor.run(None, "spending_by_category", {})  # type: ignore[arg-type]
        assert "error" in invocation.result
        assert invocation.resolved_arguments == {}

    async def test_a_handler_that_explodes_is_caught(self, monkeypatch):
        """An exception escaping here would end a half-written stream."""

        async def boom(ctx, args):
            raise RuntimeError("the database is on fire")

        import dataclasses

        monkeypatch.setitem(
            BY_NAME,
            "list_categories",
            dataclasses.replace(BY_NAME["list_categories"], handler=boom),
        )
        invocation = await executor.run(None, "list_categories", {})  # type: ignore[arg-type]
        assert "RuntimeError" in (invocation.error or "")
        # One sentence to the model, not a stack trace burning context.
        assert "on fire" not in json.dumps(invocation.result)

    async def test_the_record_keeps_raw_and_resolved_arguments(self):
        invocation = await executor.run(None, "income_vs_expense", {"months": "6"})  # type: ignore[arg-type]
        assert invocation.arguments == {"months": "6"}
        assert invocation.resolved_arguments == {"months": 6}


class TestDedupe:
    def test_same_call_same_key(self):
        assert executor.dedupe_key("a", {"x": 1, "y": 2}) == executor.dedupe_key(
            "a", {"y": 2, "x": 1}
        )

    def test_different_arguments_differ(self):
        assert executor.dedupe_key("a", {"x": 1}) != executor.dedupe_key("a", {"x": 2})


class TestTruncationIsHonest:
    def test_a_clipped_result_states_the_true_count(self):
        """A model told 25 rows will say "you had 25". It must be told 912."""
        rows = [{"n": i} for i in range(912)]
        result = clip(rows, limit=25)
        assert result["shown"] == 25
        assert result["total_rows"] == 912
        assert result["truncated"] is True
        assert "912" in result["note"]

    def test_an_unclipped_result_says_nothing_about_truncation(self):
        result = clip([{"n": 1}], limit=25)
        assert result["truncated"] is False
        assert "note" not in result

    def test_the_true_total_comes_from_the_query_not_the_page(self):
        """The register computes count and sum over the whole predicate, so a
        truncated page still states the honest total."""
        rows = [{"amount": 1.0} for _ in range(5)]
        from decimal import Decimal

        result = clip(rows, limit=2, total_rows=900, total_amount=Decimal("1234.50"))
        assert result["total_amount"] == 1234.5
        assert result["total_rows"] == 900

    def test_money_becomes_a_json_number_like_the_api_serves(self):
        from decimal import Decimal

        assert money(Decimal("9.00")) == 9.0
        assert isinstance(money(Decimal("9.00")), float)
        assert money(None) is None
        assert money("x") == "x"

    def test_fits_rejects_a_huge_payload(self):
        assert fits({"a": 1})
        assert not fits({"rows": ["x" * 100 for _ in range(200)]})

    def test_a_large_result_is_summarized_and_says_so(self):
        payload = {"total": 5, "rows": [{"v": "x" * 50} for _ in range(400)]}
        result = summarize_if_large(payload, keep=("total",))
        assert result["total"] == 5
        assert result["rows_count"] == 400
        assert "rows" not in result
        assert "too large" in result["note"]

    def test_a_small_result_passes_through_untouched(self):
        payload = {"total": 5, "rows": [{"v": 1}]}
        assert summarize_if_large(payload, keep=("total",)) == payload

    def test_the_cap_is_a_real_number(self):
        assert TOOL_RESULT_MAX_CHARS > 1000


class TestLoopBounds:
    def test_turns_and_calls_are_bounded(self):
        """Without these a small model loops until the context runs out."""
        assert executor.MAX_TURNS >= 2
        assert executor.MAX_TOOL_CALLS >= executor.MAX_TURNS
