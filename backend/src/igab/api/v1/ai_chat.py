"""The chat panel's endpoints, including the one that streams.

**The streaming endpoint does not use the request's session.** `CommitRoute`
commits inside the handler, before the response is sent, and a
`StreamingResponse` returns the moment it is constructed — so by the time the
generator runs, the request's transaction has already been committed and the
connection is wanted back in a pool of five. Anything the stream wrote would be
committed by the dependency teardown *after* the whole answer was sent, which
is exactly the staleness `api/route.py` is a long essay about.

So: durable writes happen before the response is returned, and the generator
opens its own session, the way `tasks/ai_worker.py` already does.
"""

import json
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from igab.ai import chat as chat_engine
from igab.ai.context import AICallContext
from igab.ai.context_window import result_char_budget
from igab.ai.features import FEATURES
from igab.ai.gateway import AIGateway
from igab.ai.prompts import render_page_context
from igab.ai.tools.context import ToolContext
from igab.api.route import CommitRoute
from igab.api.v1.schemas.ai_chat import (
    AICallDetailResponse,
    AICallListResponse,
    AICallResponse,
    ChatMessageResponse,
    ChatRequest,
    ConversationDetailResponse,
    ConversationResponse,
)
from igab.db.models import AIConversation
from igab.dependencies import BudgetAccess, CurrentUser, SessionDep, get_settings_service
from igab.repositories.ai_chat_repo import AIChatRepository
from igab.services.ai_service import AIService
from igab.services.settings_service import SettingsService

router = APIRouter(route_class=CommitRoute)

#: How many prior messages are replayed to the model. A local model's context
#: is the scarce resource, and a budget question rarely depends on twenty
#: turns ago.
HISTORY_LIMIT = 20


async def _require_ai_enabled(settings: SettingsService) -> None:
    """The master switch, enforced.

    It was read in exactly one function before this and enforced by no
    endpoint, so every AI route ran with AI switched off.
    """
    enabled = (await settings.get("ai_enabled") or "false").lower() == "true"
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI features are switched off. Turn them on in System settings.",
        )


def _client_today(raw: str | None) -> date:
    """The browser's date, or the server's.

    Near midnight these disagree about what "this month" means, and the user's
    clock is the one that decides.
    """
    if raw:
        try:
            return date.fromisoformat(raw.strip()[:10])
        except ValueError:
            pass
    return datetime.now(UTC).date()


async def _tool_context(session, budget_id: uuid.UUID, today: date) -> ToolContext:
    """Build the services a tool may delegate to.

    Constructed directly rather than through the request's dependency graph,
    because the streaming path builds this against its own session.
    """
    from igab.guide.service import GuideService
    from igab.repositories.account_repo import AccountRepository
    from igab.repositories.category_repo import (
        BudgetAssignmentRepository,
        CategoryGroupRepository,
        CategoryRepository,
    )
    from igab.repositories.payee_repo import PayeeRepository
    from igab.repositories.snapshot_repo import SnapshotRepository
    from igab.repositories.transaction_repo import TransactionRepository
    from igab.services.budget_service import BudgetService
    from igab.services.report_service import ReportService

    category_repo = CategoryRepository(session)
    account_repo = AccountRepository(session)
    transaction_repo = TransactionRepository(session)
    return ToolContext(
        budget_id=budget_id,
        today=today,
        session=session,
        reports=ReportService(session),
        budgets=BudgetService(
            account_repo,
            category_repo,
            CategoryGroupRepository(session),
            BudgetAssignmentRepository(session),
            transaction_repo,
            snapshot_repo=SnapshotRepository(session),
        ),
        guide=GuideService(session),
        categories=category_repo,
        accounts=account_repo,
        transactions=transaction_repo,
        payees=PayeeRepository(session),
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _title_from(message: str) -> str:
    cleaned = " ".join(message.split())
    return cleaned[:80] if len(cleaned) <= 80 else cleaned[:77] + "…"


@router.post("/{budget_id}/ai/chat")
async def chat(
    budget_id: BudgetAccess,
    body: ChatRequest,
    current_user: CurrentUser,
    session: SessionDep,
    settings: Annotated[SettingsService, Depends(get_settings_service)],
) -> StreamingResponse:
    """Ask a question and stream the answer as typed events."""
    await _require_ai_enabled(settings)

    repo = AIChatRepository(session)
    if body.conversation_id is not None:
        conversation = await repo.get_conversation(body.conversation_id, budget_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No such conversation"
            )
    else:
        conversation = await repo.create_conversation(
            budget_id, current_user.id, _title_from(body.message)
        )

    page_context = body.page_context.model_dump(mode="json") if body.page_context else None
    await repo.add_message(
        conversation.id,
        role="user",
        content=body.message,
        page_context=page_context,
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in await repo.messages(conversation.id)
        if m.role in ("user", "assistant") and m.content
    ][-HISTORY_LIMIT:]

    ai = AIService(session, settings)
    model, _ = await ai._resolve_chat_model()
    client = await ai.gateway.client(model=model)
    caps = await ai._capabilities(client)
    # None means the server is too old to say. Unlike the vision path, which
    # lets a background job try and retry, an unknown here would surface as an
    # error mid-stream in front of the user — so it declines instead.
    supports_tools = bool(caps and "tools" in caps)
    think = await ai._resolve_think(client)
    # The window is stated on every call. Ollama's default is small enough
    # that a month grid plus the tool schema overflowed it, and an overflow
    # is truncated from the front — the system prompt goes first.
    num_ctx, _ = await ai.chat_window(client)
    options = await ai._merged_options(vision=False, task_defaults={"num_ctx": num_ctx})
    result_max_chars = result_char_budget(int(options.get("num_ctx") or num_ctx))
    timeout = float(await settings.get("ai_chat_timeout_s") or "120")

    system = await ai._prompt(
        "ai_prompt_chat_system",
        {
            "today": _client_today(body.client_today).isoformat(),
            "page_context": render_page_context(page_context),
        },
    )
    if not supports_tools:
        system += (
            "\n\nYou have NO tools in this conversation, so you cannot look "
            "anything up. Say so plainly rather than guessing at figures."
        )

    conversation_id = conversation.id
    today = _client_today(body.client_today)
    messages = [{"role": "system", "content": system}, *history]

    async def stream():
        from igab.ai import call_log
        from igab.db.session import AsyncSessionLocal

        outcome = chat_engine.ChatOutcome()
        gateway = AIGateway(settings)
        persisted = False
        yield _sse("start", {"conversation_id": str(conversation_id), "tools": supports_tools})
        try:
            # Its own session: the request's has been committed and handed back.
            async with AsyncSessionLocal() as stream_session:
                tool_ctx = await _tool_context(stream_session, budget_id, today)
                tool_ctx.result_max_chars = result_max_chars
                async for event in chat_engine.run_turn(
                    gateway=gateway,
                    client=client,
                    tool_ctx=tool_ctx,
                    messages=messages,
                    context=AICallContext(
                        feature="chat",
                        budget_id=budget_id,
                        conversation_id=conversation_id,
                    ),
                    use_tools=supports_tools,
                    think=think,
                    options=options,
                    timeout=timeout,
                    outcome=outcome,
                ):
                    yield _sse(event.type, event.data)

            # The normal path, where awaiting and yielding both still work.
            message_id = await _persist_answer(conversation_id, outcome)
            persisted = True
            yield _sse("done", {"message_id": str(message_id) if message_id else None})
        finally:
            # This also runs while the generator is being closed after a client
            # disconnect, where an `await` re-raises and a `yield` raises
            # outright. So nothing here may do either: every write is enqueued.
            for result in outcome.call_results:
                call_log.submit(result)
            if not persisted:
                # The user closed the panel mid-answer. What the model had
                # already said is still worth keeping.
                call_log.enqueue(
                    _persist_answer(conversation_id, outcome),
                    what="interrupted chat answer",
                )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _persist_answer(
    conversation_id: uuid.UUID, outcome: chat_engine.ChatOutcome
) -> uuid.UUID | None:
    """Write the assistant turn, in a session of its own.

    A dropped stream is a lost turn by design: the message is written once, at
    the end, so a half-written answer never lands looking complete.
    """
    from igab.db.session import AsyncSessionLocal

    if not outcome.content and not outcome.tool_invocations:
        return None
    try:
        async with AsyncSessionLocal() as session:
            repo = AIChatRepository(session)
            message = await repo.add_message(
                conversation_id,
                role="assistant",
                content=outcome.content,
                thinking=outcome.thinking,
                tool_calls=[t.as_record() for t in outcome.tool_invocations] or None,
                # Kept with the message: reopening a conversation tomorrow
                # should show the same verdict it showed when it was written.
                grounding=outcome.grounding.as_record() if outcome.grounding else None,
            )
            conversation = await session.get(AIConversation, conversation_id)
            if conversation is not None:
                # Bumped by hand: the assistant turn is written in a session of
                # its own, so the parent's onupdate never fires.
                conversation.updated_at = datetime.now(UTC)
            await session.commit()
            return message.id
    except Exception:
        import logging

        logging.getLogger(__name__).exception("ai: could not persist chat answer")
        return None


@router.get("/{budget_id}/ai/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ConversationResponse]:
    repo = AIChatRepository(session)
    rows, _ = await repo.list_conversations(budget_id, limit=limit)
    counts = await repo.message_counts([c.id for c in rows])
    return [
        ConversationResponse(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=counts.get(c.id, 0),
        )
        for c in rows
    ]


@router.get(
    "/{budget_id}/ai/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
)
async def get_conversation(
    budget_id: BudgetAccess,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> ConversationDetailResponse:
    repo = AIChatRepository(session)
    conversation = await repo.get_conversation(conversation_id, budget_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such conversation")
    messages = await repo.messages(conversation_id)
    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            ChatMessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                thinking=m.thinking,
                tool_calls=m.tool_calls,
                grounding=m.grounding,
                created_at=m.created_at,
                ai_call_id=m.ai_call_id,
            )
            for m in messages
        ],
    )


@router.delete(
    "/{budget_id}/ai/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    budget_id: BudgetAccess,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    repo = AIChatRepository(session)
    conversation = await repo.get_conversation(conversation_id, budget_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such conversation")
    await repo.delete_conversation(conversation)


@router.get("/{budget_id}/ai/calls", response_model=AICallListResponse)
async def list_calls(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: SessionDep,
    feature: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AICallListResponse:
    repo = AIChatRepository(session)
    rows, total = await repo.list_calls(budget_id, feature=feature, limit=limit, offset=offset)
    return AICallListResponse(
        calls=[
            AICallResponse(
                id=c.id,
                feature=c.feature,
                feature_label=FEATURES.get(c.feature, c.feature),
                model=c.model,
                endpoint=c.endpoint,
                status=c.status,
                error=c.error,
                round=c.round,
                duration_ms=c.duration_ms,
                prompt_tokens=c.prompt_tokens,
                completion_tokens=c.completion_tokens,
                tool_call_count=c.tool_call_count,
                created_at=c.created_at,
            )
            for c in rows
        ],
        total_count=total,
    )


# Registered BEFORE /calls/{call_id}: FastAPI matches in declaration order, and
# the parameterised route would otherwise swallow "payloads" and fail to parse
# it as a UUID.
@router.delete("/{budget_id}/ai/calls/payloads", status_code=status.HTTP_200_OK)
async def purge_payloads(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict:
    """Drop every stored prompt and response, keeping the call list."""
    repo = AIChatRepository(session)
    removed = await repo.delete_payloads(budget_id)
    return {"removed": removed}


@router.get("/{budget_id}/ai/calls/{call_id}", response_model=AICallDetailResponse)
async def get_call(
    budget_id: BudgetAccess,
    call_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> AICallDetailResponse:
    repo = AIChatRepository(session)
    call = await repo.get_call(call_id, budget_id)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such call")
    payload = call.payload
    request = (payload.request if payload else {}) or {}
    return AICallDetailResponse(
        id=call.id,
        feature=call.feature,
        feature_label=FEATURES.get(call.feature, call.feature),
        model=call.model,
        endpoint=call.endpoint,
        status=call.status,
        error=call.error,
        round=call.round,
        duration_ms=call.duration_ms,
        prompt_tokens=call.prompt_tokens,
        completion_tokens=call.completion_tokens,
        tool_call_count=call.tool_call_count,
        created_at=call.created_at,
        system=request.get("system"),
        messages=request.get("messages") or [],
        tools=request.get("tools") or [],
        response=payload.response if payload else None,
        thinking=payload.thinking if payload else None,
        tool_trace=(payload.tool_trace if payload else None) or [],
        # Retention drops the heavy half and keeps the light one, so "no
        # payload" means aged out rather than never recorded.
        payload_pruned=payload is None,
    )
