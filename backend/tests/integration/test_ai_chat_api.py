"""The chat endpoints, including the two traps that make streaming here hard.

The important assertions are not "a model answered". They are:

- the master switch is actually enforced, which it was not for any AI route;
- a conversation id from another budget does not resolve;
- the assistant turn is persisted after the stream ends — the `CommitRoute`
  trap, where a StreamingResponse returns before its body has produced anything
  and the request's transaction is committed empty.
"""

import json
import uuid

from sqlalchemy import select

from igab.db.models import AICall, AIConversation, AIMessage

from .factories import create_budget, create_user


async def _enable_ai(api_client) -> None:
    await api_client.put("/api/v1/settings/ai_enabled", json={"value": "true"})


async def _budget(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.flush()
    return budget


def _events(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) pairs."""
    out = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        name, payload = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
        if name is not None:
            out.append((name, payload or {}))
    return out


class TestTheMasterSwitchIsEnforced:
    async def test_chat_refuses_when_ai_is_off(self, api_client, db_session):
        """`ai_enabled` was read in one function and enforced by no endpoint,
        so every AI route ran with AI switched off."""
        budget = await _budget(api_client, db_session)
        response = await api_client.post(f"/api/v1/{budget.id}/ai/chat", json={"message": "hello"})
        assert response.status_code == 403
        assert "switched off" in response.json()["detail"]

    async def test_no_conversation_is_created_when_refused(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        await api_client.post(f"/api/v1/{budget.id}/ai/chat", json={"message": "hello"})
        rows = (await db_session.execute(select(AIConversation))).scalars().all()
        assert rows == []


class TestRequestValidation:
    async def test_an_empty_message_is_rejected(self, api_client, db_session):
        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        response = await api_client.post(f"/api/v1/{budget.id}/ai/chat", json={"message": ""})
        assert response.status_code == 422

    async def test_an_unknown_page_context_kind_is_rejected(self, api_client, db_session):
        """The union is discriminated, so a page nobody declared is a 422
        rather than a blob silently ignored."""
        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        response = await api_client.post(
            f"/api/v1/{budget.id}/ai/chat",
            json={"message": "hi", "page_context": {"kind": "spaceship"}},
        )
        assert response.status_code == 422

    async def test_a_known_page_context_is_accepted(self, api_client, db_session, monkeypatch):
        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        _fake_model(monkeypatch, [{"message": {"content": "ok"}}])
        response = await api_client.post(
            f"/api/v1/{budget.id}/ai/chat",
            json={
                "message": "hi",
                "page_context": {"kind": "budget", "month": "2026-09-01"},
            },
        )
        assert response.status_code == 200


def _fake_model(monkeypatch, replies: list[dict]) -> None:
    """Replace the transport, keeping every layer above it real."""
    from igab.integrations.ollama.client import OllamaClient

    queue = list(replies)

    async def fake_chat(self, messages, **kwargs):
        self.last_meta = {"prompt_eval_count": 12, "eval_count": 4}
        return queue.pop(0) if queue else {"message": {"content": "done"}}

    async def fake_caps(self, model=None):
        return ["completion"]  # no "tools"

    monkeypatch.setattr(OllamaClient, "chat", fake_chat)
    monkeypatch.setattr(OllamaClient, "capabilities", fake_caps)


class TestTheStreamAndWhatItLeavesBehind:
    async def test_the_answer_streams_as_typed_events(self, api_client, db_session, monkeypatch):
        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        _fake_model(monkeypatch, [{"message": {"content": "Two shops posted late."}}])

        response = await api_client.post(
            f"/api/v1/{budget.id}/ai/chat", json={"message": "why is Groceries over?"}
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _events(response.text)
        kinds = [name for name, _ in events]
        assert kinds[0] == "start"
        assert "token" in kinds
        assert kinds[-1] == "done"

    async def test_a_model_without_tools_says_so(self, api_client, db_session, monkeypatch):
        """It still answers, degraded, rather than pretending to have looked
        something up."""
        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        _fake_model(monkeypatch, [{"message": {"content": "I cannot look that up."}}])
        response = await api_client.post(f"/api/v1/{budget.id}/ai/chat", json={"message": "hi"})
        start = next(data for name, data in _events(response.text) if name == "start")
        assert start["tools"] is False

    async def test_the_user_message_is_persisted(self, api_client, db_session, monkeypatch):
        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        _fake_model(monkeypatch, [{"message": {"content": "ok"}}])
        await api_client.post(f"/api/v1/{budget.id}/ai/chat", json={"message": "a question"})
        rows = (await db_session.execute(select(AIMessage))).scalars().all()
        assert any(m.role == "user" and m.content == "a question" for m in rows)

    async def test_a_conversation_is_titled_from_the_first_message(
        self, api_client, db_session, monkeypatch
    ):
        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        _fake_model(monkeypatch, [{"message": {"content": "ok"}}])
        await api_client.post(
            f"/api/v1/{budget.id}/ai/chat", json={"message": "why is Groceries overspent?"}
        )
        conversation = (await db_session.execute(select(AIConversation))).scalars().one()
        assert conversation.title == "why is Groceries overspent?"


class TestConversationScoping:
    async def test_another_budgets_conversation_is_not_found(
        self, api_client, db_session, monkeypatch
    ):
        """A conversation id alone must not reach across budgets."""
        await _enable_ai(api_client)
        mine = await _budget(api_client, db_session)
        other_user = await create_user(db_session)
        theirs = await create_budget(db_session, other_user)
        await db_session.flush()

        from igab.repositories.ai_chat_repo import AIChatRepository

        conversation = await AIChatRepository(db_session).create_conversation(
            theirs.id, other_user.id, "theirs"
        )
        await db_session.flush()

        _fake_model(monkeypatch, [{"message": {"content": "ok"}}])
        response = await api_client.post(
            f"/api/v1/{mine.id}/ai/chat",
            json={"message": "hi", "conversation_id": str(conversation.id)},
        )
        assert response.status_code == 404

    async def test_listing_and_fetching_a_conversation(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        from igab.repositories.ai_chat_repo import AIChatRepository

        repo = AIChatRepository(db_session)
        conversation = await repo.create_conversation(budget.id, api_client.test_user.id, "Hello")
        await repo.add_message(conversation.id, role="user", content="a question")
        await db_session.flush()

        listing = await api_client.get(f"/api/v1/{budget.id}/ai/conversations")
        assert listing.status_code == 200
        assert listing.json()[0]["title"] == "Hello"
        assert listing.json()[0]["message_count"] == 1

        detail = await api_client.get(f"/api/v1/{budget.id}/ai/conversations/{conversation.id}")
        assert detail.status_code == 200
        assert detail.json()["messages"][0]["content"] == "a question"

    async def test_deleting_a_conversation(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        from igab.repositories.ai_chat_repo import AIChatRepository

        conversation = await AIChatRepository(db_session).create_conversation(
            budget.id, api_client.test_user.id, "Bye"
        )
        await db_session.flush()
        response = await api_client.delete(
            f"/api/v1/{budget.id}/ai/conversations/{conversation.id}"
        )
        assert response.status_code == 204

    async def test_a_missing_conversation_is_404(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        response = await api_client.get(f"/api/v1/{budget.id}/ai/conversations/{uuid.uuid4()}")
        assert response.status_code == 404


class TestTheCallLogEndpoints:
    async def _a_call(self, db_session, budget, **overrides):
        call = AICall(
            budget_id=budget.id,
            feature=overrides.pop("feature", "chat"),
            model="gemma4:31b",
            host="http://localhost:11434",
            endpoint="chat",
            status="ok",
            round=0,
            **overrides,
        )
        db_session.add(call)
        await db_session.flush()
        return call

    async def test_listing_calls(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        await self._a_call(db_session, budget)
        response = await api_client.get(f"/api/v1/{budget.id}/ai/calls")
        assert response.status_code == 200
        body = response.json()
        assert body["total_count"] == 1
        assert body["calls"][0]["feature_label"].startswith("Answering")

    async def test_installation_calls_are_listed_too(self, api_client, db_session):
        """A probe with no budget still happened on this install, and hiding
        it would make "Ollama is unreachable" invisible."""
        budget = await _budget(api_client, db_session)
        db_session.add(
            AICall(
                budget_id=None,
                feature="receipt_gate",
                model="m",
                host="h",
                endpoint="generate",
                status="error",
                error="TimeoutError",
                round=0,
            )
        )
        await db_session.flush()
        response = await api_client.get(f"/api/v1/{budget.id}/ai/calls")
        assert response.json()["total_count"] == 1

    async def test_call_detail_reports_a_pruned_payload_honestly(self, api_client, db_session):
        """Retention drops the heavy half, so "no payload" means aged out —
        not that the call was never recorded."""
        budget = await _budget(api_client, db_session)
        call = await self._a_call(db_session, budget)
        response = await api_client.get(f"/api/v1/{budget.id}/ai/calls/{call.id}")
        assert response.status_code == 200
        assert response.json()["payload_pruned"] is True

    async def test_purging_payloads_keeps_the_calls(self, api_client, db_session):
        from igab.db.models import AICallPayload

        budget = await _budget(api_client, db_session)
        call = await self._a_call(db_session, budget)
        db_session.add(AICallPayload(ai_call_id=call.id, request={}, response="secret"))
        await db_session.flush()

        response = await api_client.delete(f"/api/v1/{budget.id}/ai/calls/payloads")
        assert response.status_code == 200
        assert response.json()["removed"] == 1
        remaining = (await db_session.execute(select(AICall))).scalars().all()
        assert len(remaining) == 1

    async def test_payloads_is_not_parsed_as_a_call_id(self, api_client, db_session):
        """The literal route must be declared before /calls/{call_id}."""
        budget = await _budget(api_client, db_session)
        response = await api_client.delete(f"/api/v1/{budget.id}/ai/calls/payloads")
        assert response.status_code == 200

    async def test_a_missing_call_is_404(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        response = await api_client.get(f"/api/v1/{budget.id}/ai/calls/{uuid.uuid4()}")
        assert response.status_code == 404


class TestTheStreamsOwnSession:
    """The CommitRoute trap, pinned.

    `CommitRoute` commits inside the handler, before the response is sent, and
    a StreamingResponse returns the moment it is constructed. So the request's
    transaction is committed empty and its connection wanted back in a pool of
    five, while the generator has produced nothing yet. Anything the stream
    writes through the request session would land after the whole answer was
    sent — the exact staleness `api/route.py` is an essay about.

    These patch `AsyncSessionLocal` to hand back the test session, which is
    what the generator reaches for, so the writes are visible to assertions.
    """

    @staticmethod
    def _own_session(monkeypatch, db_session, *, quiet_log: bool = True):
        """Point the generator's session factory at the test session.

        Production opens two independent sessions here — one for the assistant
        turn, one per call-log row — and they never contend. Handing both the
        *same* session, as this must to make the writes visible to assertions,
        puts two operations on one asyncpg connection at once. So the call log
        is silenced by default; it is asserted at its own boundary below and
        against a real database in test_ai_call_log_writes.py.
        """
        from contextlib import asynccontextmanager

        import igab.db.session as session_module
        from igab.ai import call_log

        @asynccontextmanager
        async def factory():
            yield db_session

        monkeypatch.setattr(session_module, "AsyncSessionLocal", factory)
        if quiet_log:
            monkeypatch.setattr(call_log, "submit", lambda result: None)

    async def test_the_assistant_turn_lands_after_the_stream_ends(
        self, api_client, db_session, monkeypatch
    ):
        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        _fake_model(monkeypatch, [{"message": {"content": "Two shops posted late."}}])
        self._own_session(monkeypatch, db_session)

        response = await api_client.post(f"/api/v1/{budget.id}/ai/chat", json={"message": "why?"})
        assert response.status_code == 200

        rows = (await db_session.execute(select(AIMessage))).scalars().all()
        assistant = [m for m in rows if m.role == "assistant"]
        assert len(assistant) == 1
        assert assistant[0].content == "Two shops posted late."

    async def test_the_done_event_names_the_persisted_message(
        self, api_client, db_session, monkeypatch
    ):
        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        _fake_model(monkeypatch, [{"message": {"content": "ok"}}])
        self._own_session(monkeypatch, db_session)

        response = await api_client.post(f"/api/v1/{budget.id}/ai/chat", json={"message": "hi"})
        done = next(data for name, data in _events(response.text) if name == "done")
        assert done["message_id"] is not None

    async def test_the_model_call_is_submitted_to_the_log(
        self, api_client, db_session, monkeypatch
    ):
        """Every round trip is handed to the recorder.

        Asserted at the submit boundary rather than in the database, because
        production writes it from a session of its own — sharing one here would
        put the write inside another session's flush. That the row then lands
        is `test_ai_call_log_writes.py`.
        """
        from igab.ai import call_log

        submitted = []
        monkeypatch.setattr(call_log, "submit", submitted.append)

        await _enable_ai(api_client)
        budget = await _budget(api_client, db_session)
        _fake_model(monkeypatch, [{"message": {"content": "ok"}}])
        # This test owns the submit patch, so the helper must not replace it.
        self._own_session(monkeypatch, db_session, quiet_log=False)

        await api_client.post(f"/api/v1/{budget.id}/ai/chat", json={"message": "hi"})

        assert len(submitted) == 1
        result = submitted[0]
        assert result.context.feature == "chat"
        assert result.context.budget_id == budget.id
        assert result.prompt_tokens == 12
        assert result.status == "ok"
