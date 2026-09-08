"""The chat turn, driven against a fake model.

What matters here is not that a model answers well — it is that the loop stays
bounded, records what it did, and never lets a tool failure end the stream.
"""

import asyncio

import pytest

from igab.ai import chat as chat_engine
from igab.ai.context import AICallContext
from igab.ai.gateway import AIGateway
from igab.ai.prompts import render_page_context
from igab.ai.tools import executor


class FakeClient:
    """Stands in for OllamaClient, replaying scripted responses."""

    def __init__(self, replies: list[dict]) -> None:
        self.replies = list(replies)
        self.model = "gemma4:test"
        self.host = "http://localhost:11434"
        self.last_meta: dict = {}
        self.calls: list[dict] = []

    async def chat(self, messages, *, tools=None, think=None, options=None, timeout=120.0):
        self.calls.append({"messages": list(messages), "tools": tools})
        self.last_meta = {"prompt_eval_count": 10, "eval_count": 5}
        if not self.replies:
            return {"message": {"content": "done"}}
        return self.replies.pop(0)


def _text(content: str) -> dict:
    return {"message": {"content": content}}


def _tool(name: str, arguments: dict) -> dict:
    return {
        "message": {
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        }
    }


async def _run(client, tool_ctx=None, use_tools=True) -> tuple[list, chat_engine.ChatOutcome]:
    outcome = chat_engine.ChatOutcome()
    events = []
    async for event in chat_engine.run_turn(
        gateway=AIGateway(settings=None),  # type: ignore[arg-type]
        client=client,
        tool_ctx=tool_ctx,
        messages=[{"role": "user", "content": "why is Groceries overspent?"}],
        context=AICallContext(feature="chat"),
        use_tools=use_tools,
        outcome=outcome,
    ):
        events.append(event)
    return events, outcome


class TestAPlainAnswer:
    async def test_a_model_that_just_answers(self):
        events, outcome = await _run(FakeClient([_text("Two shops posted late.")]))
        kinds = [e.type for e in events]
        assert "token" in kinds and "usage" in kinds
        assert outcome.content == "Two shops posted late."

    async def test_the_system_prompt_is_lifted_onto_the_record(self):
        """The transparency view has a section for it and reads this field
        rather than digging through the transcript."""
        outcome = chat_engine.ChatOutcome()
        async for _ in chat_engine.run_turn(
            gateway=AIGateway(settings=None),  # type: ignore[arg-type]
            client=FakeClient([_text("hi")]),
            tool_ctx=None,
            messages=[
                {"role": "system", "content": "You are the assistant."},
                {"role": "user", "content": "hello"},
            ],
            context=AICallContext(feature="chat"),
            use_tools=False,
            outcome=outcome,
        ):
            pass
        assert outcome.call_results[0].system == "You are the assistant."

    async def test_token_counts_reach_the_record(self):
        _, outcome = await _run(FakeClient([_text("hi")]))
        assert outcome.call_results[0].prompt_tokens == 10
        assert outcome.call_results[0].completion_tokens == 5

    async def test_tools_are_not_offered_when_unsupported(self):
        client = FakeClient([_text("hi")])
        await _run(client, use_tools=False)
        assert client.calls[0]["tools"] is None


class TestToolCalls:
    async def test_a_tool_call_is_announced_before_and_after(self, monkeypatch):
        """The panel shows what it reached for while it runs, then what came
        back — a wrong lookup is caught next to the answer it produced."""

        async def fake_run(ctx, name, arguments):
            from igab.ai.context import ToolInvocation

            return ToolInvocation(
                name=name,
                arguments=arguments,
                resolved_arguments={"months": 3},
                delegates_to="ReportService.spending_by_category",
                result={"rows": []},
                row_count=0,
            )

        monkeypatch.setattr(executor, "run", fake_run)
        client = FakeClient(
            [_tool("spending_by_category", {"months": "3"}), _text("You spent less.")]
        )
        events, outcome = await _run(client, tool_ctx=object())
        kinds = [e.type for e in events]
        assert kinds.index("tool_call") < kinds.index("tool_result")
        result_event = next(e for e in events if e.type == "tool_result")
        # Raw beside resolved: the difference is where a bad model is visible.
        assert result_event.data["arguments"] == {"months": "3"}
        assert result_event.data["resolved_arguments"] == {"months": 3}
        assert result_event.data["delegates_to"] == "ReportService.spending_by_category"
        assert outcome.content == "You spent less."

    async def test_the_same_call_twice_is_answered_from_cache(self, monkeypatch):
        """The cheapest loop a small model falls into."""
        runs: list[str] = []

        async def counting_run(ctx, name, arguments):
            from igab.ai.context import ToolInvocation

            runs.append(name)
            return ToolInvocation(name=name, arguments=arguments, result={"rows": []})

        monkeypatch.setattr(executor, "run", counting_run)
        client = FakeClient(
            [
                _tool("list_categories", {}),
                _tool("list_categories", {}),
                _text("Here you go."),
            ]
        )
        _, outcome = await _run(client, tool_ctx=object())
        assert runs == ["list_categories"]  # ran once
        assert len(outcome.tool_invocations) == 2  # recorded twice
        assert "already asked" in outcome.tool_invocations[1].result["note"]

    async def test_a_tool_that_fails_does_not_end_the_stream(self, monkeypatch):
        async def failing(ctx, name, arguments):
            from igab.ai.context import ToolInvocation

            return ToolInvocation(
                name=name, arguments=arguments, error="boom", result={"error": "boom"}
            )

        monkeypatch.setattr(executor, "run", failing)
        client = FakeClient([_tool("list_categories", {}), _text("I could not look that up.")])
        events, outcome = await _run(client, tool_ctx=object())
        assert outcome.content == "I could not look that up."
        assert any(e.type == "tool_result" and e.data["error"] for e in events)


class TestTheLoopIsBounded:
    async def test_the_last_turn_drops_the_tools(self, monkeypatch):
        """A stream that ends with no assistant text reads as a crash, so the
        model is forced to answer in prose rather than simply stopped."""

        async def always(ctx, name, arguments):
            from igab.ai.context import ToolInvocation

            return ToolInvocation(name=name, arguments=arguments, result={"n": len(ctx or [])})

        monkeypatch.setattr(executor, "run", always)
        # A model that never stops asking.
        client = FakeClient([_tool("list_categories", {"i": i}) for i in range(10)])
        events, outcome = await _run(client, tool_ctx=[])
        assert client.calls[-1]["tools"] is None
        assert outcome.content  # it says something
        kinds = [e.type for e in events]
        assert "token" in kinds
        # The answer is checked before the turn is called finished.
        assert kinds[-1] == "grounding"

    async def test_the_call_cap_is_checked_per_call_not_per_turn(self, monkeypatch):
        """A model can ask for a dozen tools in one message. Reading the cap
        only between turns let every one of them run."""
        runs: list[str] = []

        async def counting(ctx, name, arguments):
            from igab.ai.context import ToolInvocation

            runs.append(name)
            return ToolInvocation(name=name, arguments=arguments, result={"n": len(runs)})

        monkeypatch.setattr(executor, "run", counting)
        many = {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "list_categories", "arguments": {"i": i}}}
                    for i in range(20)
                ],
            }
        }
        client = FakeClient([many, _text("done")])
        await _run(client, tool_ctx=object())
        assert len(runs) <= executor.MAX_TOOL_CALLS

    async def test_turn_and_call_caps_are_real(self):
        assert executor.MAX_TURNS >= 2
        assert executor.MAX_TOOL_CALLS >= 4


class TestTheAnswerIsChecked:
    """The prompt asks the model not to invent a figure. This is the part that
    checks whether it did."""

    async def test_a_grounded_answer_is_reported_clean(self, monkeypatch):
        async def lookup(ctx, name, arguments):
            from igab.ai.context import ToolInvocation

            return ToolInvocation(
                name=name, arguments=arguments, result={"rows": [{"total": 120.0}]}
            )

        monkeypatch.setattr(executor, "run", lookup)
        client = FakeClient(
            [_tool("spending_by_category", {}), _text("Groceries came to $120.00.")]
        )
        events, outcome = await _run(client, tool_ctx=object())
        grounding = next(e for e in events if e.type == "grounding")
        assert grounding.data["unsupported"] == []
        assert grounding.data["grounded"] == 1
        assert outcome.grounding is not None

    async def test_an_invented_figure_is_named(self, monkeypatch):
        async def lookup(ctx, name, arguments):
            from igab.ai.context import ToolInvocation

            return ToolInvocation(
                name=name, arguments=arguments, result={"rows": [{"total": 120.0}]}
            )

        monkeypatch.setattr(executor, "run", lookup)
        client = FakeClient(
            [_tool("spending_by_category", {}), _text("Groceries came to $4,182.33.")]
        )
        events, _ = await _run(client, tool_ctx=object())
        grounding = next(e for e in events if e.type == "grounding")
        assert grounding.data["unsupported"] == ["$4,182.33"]

    async def test_figures_with_no_lookups_are_reported(self):
        """The worst case: numbers with nothing behind them."""
        events, _ = await _run(FakeClient([_text("You spent $500.00.")]), use_tools=False)
        grounding = next(e for e in events if e.type == "grounding")
        assert grounding.data["lookups"] == 0
        assert grounding.data["unsupported"] == ["$500.00"]

    async def test_an_answer_with_no_figures_claims_nothing(self):
        events, _ = await _run(FakeClient([_text("I could not find that.")]), use_tools=False)
        grounding = next(e for e in events if e.type == "grounding")
        assert grounding.data["figures"] == 0
        assert grounding.data["unsupported"] == []


class TestCancellation:
    async def test_a_cancelled_call_is_recorded_and_re_raised(self):
        """Closing the panel is not an error. Recording it as one fabricates a
        failure, and swallowing it stops the request unwinding."""

        class Cancelling(FakeClient):
            async def chat(self, *a, **k):
                raise asyncio.CancelledError()

        outcome = chat_engine.ChatOutcome()
        with pytest.raises(asyncio.CancelledError):
            async for _ in chat_engine.run_turn(
                gateway=AIGateway(settings=None),  # type: ignore[arg-type]
                client=Cancelling([]),
                tool_ctx=None,
                messages=[{"role": "user", "content": "q"}],
                context=AICallContext(feature="chat"),
                use_tools=False,
                outcome=outcome,
            ):
                pass
        assert outcome.call_results[0].status == "cancelled"
        assert outcome.error is None


class TestFailure:
    async def test_a_transport_error_becomes_one_readable_event(self):
        class Broken(FakeClient):
            async def chat(self, *a, **k):
                import httpx

                raise httpx.ConnectError("refused")

        events, outcome = await _run(Broken([]))
        assert events[-1].type == "error"
        assert "Ollama" in events[-1].data["message"]
        assert outcome.call_results[0].status == "error"

    async def test_the_message_never_leaks_the_host(self):
        """A connection error's repr carries host and port; that belongs in
        the log, not in a chat bubble."""

        class Broken(FakeClient):
            async def chat(self, *a, **k):
                import httpx

                raise httpx.ConnectError("connection refused to 10.0.0.5:11434")

        events, _ = await _run(Broken([]))
        assert "10.0.0.5" not in events[-1].data["message"]


class TestPageContextBecomesOneSentence:
    def test_a_known_page(self):
        assert "budget grid" in render_page_context({"kind": "budget", "month": "2026-09"})

    def test_selected_envelopes_are_named(self):
        rendered = render_page_context(
            {"kind": "budget", "month": "2026-09", "selected_category_names": ["Groceries"]}
        )
        assert "Groceries" in rendered

    def test_an_unknown_page_says_nothing(self):
        """A wrong statement about what someone is looking at is worse than
        no statement."""
        assert render_page_context({"kind": "spaceship"}) == ""

    def test_no_context_says_nothing(self):
        assert render_page_context(None) == ""

    def test_a_page_missing_its_field_says_nothing(self):
        assert render_page_context({"kind": "reports"}) == ""

    @pytest.mark.parametrize(
        "kind",
        ["accounts", "transactions", "liabilities", "guide", "payees", "settings"],
    )
    def test_every_simple_page_has_a_phrase(self, kind: str):
        assert render_page_context({"kind": kind})
