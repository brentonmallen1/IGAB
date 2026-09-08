"""The recorder writes a real row, in its own session.

`call_log._write` opens `AsyncSessionLocal` rather than taking the request's
session, because by the time it runs the response has been sent and
`CommitRoute` has already committed. These tests drive `_write` directly
against the test session factory so the row shape is asserted, not assumed.
"""

from sqlalchemy import select

from igab.ai import call_log
from igab.ai.context import (
    STATUS_ERROR,
    AICallContext,
    AICallResult,
    ToolInvocation,
)
from igab.db.models import AICall, AICallPayload

from .factories import create_budget, create_user


async def _write_through(db_session, result: AICallResult) -> None:
    """Run the recorder against the test session.

    The production path opens its own session; here the fixture's session is
    the one with the schema, so the write is driven through a factory that
    hands it back. The row-building code under test is identical.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        yield db_session

    import igab.db.session as session_module

    original = session_module.AsyncSessionLocal
    session_module.AsyncSessionLocal = factory  # type: ignore[assignment]
    try:
        await call_log._write(result)
    finally:
        session_module.AsyncSessionLocal = original  # type: ignore[assignment]


async def _budget(session):
    return await create_budget(session, await create_user(session))


class TestTheRowsLand:
    async def test_a_successful_call_writes_both_halves(self, db_session):
        budget = await _budget(db_session)
        result = AICallResult(
            context=AICallContext(feature="chat", budget_id=budget.id),
            model="gemma4:31b",
            host="http://localhost:11434",
            endpoint="chat",
            duration_ms=1400,
            prompt_tokens=820,
            completion_tokens=140,
            system="You are a budgeting assistant.",
            messages=[{"role": "user", "content": "Why is Groceries overspent?"}],
            response="Two shops posted after the month turned.",
        )
        await _write_through(db_session, result)

        call = (await db_session.execute(select(AICall))).scalars().one()
        assert call.feature == "chat"
        assert call.status == "ok"
        assert call.prompt_tokens == 820
        assert call.completion_tokens == 140
        assert call.budget_id == budget.id

        payload = (await db_session.execute(select(AICallPayload))).scalars().one()
        assert payload.ai_call_id == call.id
        assert payload.request["system"] == "You are a budgeting assistant."
        assert payload.response == "Two shops posted after the month turned."

    async def test_a_failed_call_is_recorded_with_its_error(self, db_session):
        budget = await _budget(db_session)
        result = AICallResult(
            context=AICallContext(feature="suggest_category", budget_id=budget.id),
            model="gemma4:31b",
            host="http://localhost:11434",
            endpoint="generate",
            status=STATUS_ERROR,
            error="ConnectionError: refused",
        )
        await _write_through(db_session, result)
        call = (await db_session.execute(select(AICall))).scalars().one()
        assert call.status == STATUS_ERROR
        assert "ConnectionError" in call.error

    async def test_the_tool_trace_keeps_raw_and_resolved_arguments(self, db_session):
        """A small model's mistake lives in the difference between what it
        asked for and what actually ran, so both are stored."""
        budget = await _budget(db_session)
        result = AICallResult(
            context=AICallContext(feature="chat", budget_id=budget.id, round=1),
            model="gemma4:31b",
            host="http://localhost:11434",
            endpoint="chat",
            tool_invocations=[
                ToolInvocation(
                    name="spending_by_category",
                    arguments={"months": "three"},
                    resolved_arguments={"months": 3},
                    delegates_to="ReportService.spending_by_category",
                    row_count=12,
                    truncated=False,
                )
            ],
        )
        await _write_through(db_session, result)

        call = (await db_session.execute(select(AICall))).scalars().one()
        assert call.tool_call_count == 1
        assert call.round == 1

        payload = (await db_session.execute(select(AICallPayload))).scalars().one()
        trace = payload.tool_trace[0]
        assert trace["arguments"] == {"months": "three"}
        assert trace["resolved_arguments"] == {"months": 3}
        assert trace["delegates_to"] == "ReportService.spending_by_category"

    async def test_an_installation_call_has_no_budget(self, db_session):
        """The availability probe belongs to the install, not a budget — and a
        budget delete must leave it standing."""
        result = AICallResult(
            context=AICallContext(feature="receipt_gate"),
            model="gemma4:31b",
            host="http://localhost:11434",
            endpoint="generate",
        )
        await _write_through(db_session, result)
        call = (await db_session.execute(select(AICall))).scalars().one()
        assert call.budget_id is None
