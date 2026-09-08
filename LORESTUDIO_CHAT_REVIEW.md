# LoreStudio chat & AI gateway — review notes

Written while designing an AI chat sidebar for a different app (IGAB, a budgeting
tool) and reading LoreStudio's implementation for prior art. Two halves: things
that look like defects, and things worth keeping exactly as they are.

Paths are relative to `/Users/euclid/repos/LoreStudio`.

---

## 1. Defects and half-wired code

### 1.1 Chat conversations are never persisted

`api.addChronicleMessage` (`frontend/src/api/client.ts:1279`) has **zero call
sites**. `aiStore._pendingChronicle` is declared and never read.

So scene-assistant and story-assistant conversations exist only in memory. The
Chronicle "resume" path (`frontend/src/lib/ai/sessions/talk.ts:98-134`) fetches
the newest unarchived session and offers **Continue / Start Fresh** — but for
these session types there is nothing to continue, because nothing was written.

It looks like it works because interviews and panel interviews *do* persist,
through `backend/app/routers/interviews.py` and `panel_interviews.py`.

**Fix:** call `addChronicleMessage` on `_finalizeMessage` in `aiStore.ts`, or
delete the endpoint and the `_pendingChronicle` field and stop offering resume
for session types that cannot resume. Either is fine; the current middle state is
the problem — the UI promises a capability the storage layer does not have.

### 1.2 Sessions are memory-only by design, and the UI implies otherwise

`frontend/src/stores/aiStore.ts` holds `AISession[]` in memory. Only the
float/dock preference reaches `localStorage`. A refresh loses every open
conversation, which is surprising given there is a Chronicle page listing
conversations.

Worth deciding explicitly: either persist sessions (and 1.1 becomes mandatory) or
make the panel visibly ephemeral so a reload is not a surprise.

### 1.3 Errors are delivered as prose inside the response body

`backend/app/routers/chat.py:122-136`:

```python
async def stream():
    try:
        async for token in ai_gateway.stream(...):
            yield token
    except Exception as e:
        yield f"\n\n[Error: {e}]"
```

The transport has already committed to `200 text/plain`, so a failure is
appended as text. The client cannot distinguish "the model said this" from "the
server broke", the message is saved to history as if the model wrote it, and the
raw exception string is rendered into the UI.

**Fix:** typed events (see 2.1). Until then, at minimum wrap the error in a
sentinel the client recognises and refuses to persist.

### 1.4 The chat endpoint takes unvalidated `dict`s

`backend/app/routers/chat.py` — `messages: list[dict] = Body(...)`, `node_id:
str`, `mode: str | None`. No Pydantic model, so no validation of role, content
shape, or message ordering. A malformed history reaches the provider and fails
somewhere less obvious.

**Fix:** a `ChatRequest` model with `Literal["user","assistant","system"]` roles.
Cheap, and it moves the failure to the boundary.

### 1.5 The provider abstraction exists but is bypassed

`backend/app/services/llm/base.py` defines an `LLMProvider` ABC
(`chat_stream`, `is_available`), but `gateway.py` imports the `ollama_provider`
singleton directly. So the ABC documents an intention the code does not follow,
and swapping providers means editing the gateway.

**Fix:** inject the provider into `AIGateway.__init__`, defaulting to
`ollama_provider`. Two lines, and the ABC becomes load-bearing.

### 1.6 No cost tracking

`_log_call` records tokens and latency but no cost. Correct for local Ollama,
wrong the moment a hosted provider appears — and 1.5 says that is the intended
direction. Add `cost_usd` to the log row now, nullable, rather than migrating a
populated table later.

### 1.7 Thinking is transported as sentinels inside prose

`OllamaProvider.chat_stream_with_metrics` prepends `<|think|>\n` to the system
prompt and the model delimits reasoning with `<|channel>thought … <channel|>`.
`frontend/src/components/ai/shared/MessageList.tsx` then regexes it back out:

```ts
const THINKING_RE = /<\|channel>thought\n([\s\S]*?)<channel\|>/g;
const PARTIAL_THINKING_RE = /<\|channel>thought\n[\s\S]*$/;
```

Three problems: a model that emits that literal text corrupts the transcript;
the parse is duplicated between streaming and final render; and the channel
cannot carry anything else (tool calls, usage, structured status).

This is Gemma-specific plumbing leaking all the way into a React component.

---

## 2. Design changes worth making

### 2.1 Replace the plain-text stream with typed SSE events

Current transport is raw chunked `text/plain`. Suggested:

```
event: thinking    {"delta": "..."}
event: token       {"delta": "..."}
event: tool_call   {"name": "...", "arguments": {...}}
event: usage       {"prompt_tokens": 1204, "eval_tokens": 380}
event: error       {"message": "...", "status": "error"}
event: done        {"call_id": "...", "message_id": "..."}
```

This fixes 1.3 and 1.7 at once, removes the regex from the view layer, and is
the only way tool calling (if it ever lands — see 3) can be shown as it happens.

### 2.2 If porting to async SQLAlchemy, `_log_call` needs rethinking

This one is subtle and worth flagging loudly, because the current code is
**correct for its stack and would silently break in another**.

`_log_call` is synchronous `db.add` / `db.commit`, called from inside an async
generator's `finally`. That is deliberate: you cannot `await` after
`GeneratorExit`, and on a client disconnect the `finally` runs during unwinding.
Sync calls complete; awaited ones do not.

Port that to `AsyncSession` naively — `await session.commit()` in the same
`finally` — and cancelled calls silently stop being logged, which defeats the
entire point of logging in `finally`.

The portable shape is to **enqueue, never await**:

```python
_pending: set[asyncio.Task] = set()

def submit(record) -> None:
    task = asyncio.create_task(_write(record))   # create_task does not await
    _pending.add(task)                            # strong ref: an unreferenced
    task.add_done_callback(_pending.discard)      # task can be GC'd mid-flight
```

...draining `_pending` at shutdown. Note also that `BackgroundTask` is **not** a
safe substitute: Starlette skips `self.background()` when a disconnect raises out
of `stream_response` on the ASGI 2.4 branch, and uvicorn's websocket protocols
already advertise 2.4.

### 2.3 Per-feature model selection

`backend/app/services/llm/features.py` rows carry `id, label, group,
classification, description, context, budget`. Model and base URL come from
`User.settings["llm"]`, so every feature runs on one model.

That is a real limitation: a cheap fast model is right for autocomplete-shaped
features and wrong for continuity checking. Adding an optional `model` to the
feature row, falling back to the user setting, is a small change with a large
payoff — and the precedence machinery in `_get_effective_params` already exists
to hang it off.

---

## 3. There is no tool calling — worth knowing before you assume there is

`grep -rniE "tools|tool_call|function_call|tool_use"` over `backend/app` and
`frontend/src` returns only a non-AI `prose_tools.py`. The model is never asked
to fetch anything.

Instead, `backend/app/services/codex/context.py` (725 lines) assembles everything
in Python **before** the call: `build_packet` → `assemble_scene` →
`retrieve_for` (embeddings + `sqlite-vec`) → rendered into the system prompt.

That is a legitimate architecture and in some ways better than tool calling —
deterministic, one round trip, no chance of the model inventing an id. But it
means the model cannot follow up on something it did not anticipate needing.
`generate_structured` (constrained decoding via Ollama's `format` +
`model_json_schema()`) is the nearest thing to a typed call, and it is
output-shaping rather than data-fetching.

If tool calling is ever added, 2.1 becomes a prerequisite, not a nice-to-have.

---

## 4. Keep exactly as-is

These are good and I am copying them.

**4.1 The gateway as a real chokepoint.** `ai_gateway.stream(messages,
feature_prompt, context, db, user, ...)` with `AICallContext` in and
`AICallResult` out, and `backend/tests/services/test_ai_features.py` failing when
a router passes an unregistered `feature=` id. A registry plus a guard test beats
a convention.

**4.2 Logging in `finally`.** Cancelled and errored calls are recorded, and
`_log_call` swallows its own exceptions so telemetry can never break a call.
Both decisions are right.

**4.3 The two-table split.** `ActivityLog` (light, permanent) + `AICallPayload`
(heavy, 1:1, prunable at `ai_payload_retention_days`, user-purgeable via
`DELETE /api/ai/payloads`). Listing stays cheap, detail stays complete, retention
applies only to bulk. This is the single best idea in the codebase.

**4.4 Transparency derived from the object the call used.**
`_blocks_for(packet)` builds the "what was sent" view from the assembled packet
rather than re-querying source rows, and `llm_preview.py`'s `_sources_from(assembled)`
does the same for the pre-call preview. The UI *structurally cannot* claim
context that was not sent. Most transparency features are a second code path that
drifts; this one cannot.

**4.5 Honest fallback in the transparency trigger.**
`useLLMTransparency.open()` shows the call that actually ran when one exists and
falls back to "what would be sent" when it does not — and says which. Resisting
the temptation to show a plausible reconstruction is the right call.

**4.6 Status vocabulary.** `ok | error | cancelled | schema-fallback |
invalid-json | schema-invalid`, with `STATUS_TEXT` rendering a plain-English
banner. Structured output failures are visible rather than silently retried.

**4.7 `StructuredResult` never raises.** Failures surface as statuses, so one bad
generation degrades a feature instead of 500-ing a request.

**4.8 Param precedence with presence checks.** `_get_effective_params`
(`gateway.py:135-158`) resolves request > user settings > config defaults using
`exclude_none` rather than truthiness — there is a comment about the bug that
motivated it. An explicitly-set `0` or `""` must beat a default, and truthiness
gets that wrong.

**4.9 Typed graph walk scoping retrieval.**

```python
EDGE_KINDS_BY_FEATURE = {
    "interview":        ("present_in", "knows", "rel"),
    "scene-chat":       ("present_in", "at", "advances", "follows"),
    "what-if":          ("present_in", "knows", "advances", "links"),
    "continuity-check": ("links", "advances", "follows", "established_in"),
}
```

Retrieval is scoped by a one-hop walk along feature-appropriate edge kinds, and
unconfirmed LLM-proposed edges are excluded (`_settled`). Vector search over a
relevant subgraph beats vector search over everything.

**4.10 Provenance carries a human reason into the prompt.** `walk()` returns
`node_id -> why it was reached` in the author's words ("present in Ch. 7"), and
`attach_passages()` puts the "why" into the packet — so the reason reaches the
model, not just the UI. This is what makes the context meter meaningful rather
than decorative.

**4.11 Feature table → codegen → shared TS.**
`backend/scripts/gen_ai_features.py` renders `features.py` into
`frontend/src/lib/ai/features.generated.ts`, with CI running `--check`. Panel,
palette, Chronicle labels, settings cards and the transparency view all read one
source. (Only worth it because a build step already exists — do not add one to a
repo that has none just for this.)

---

## 5. Suggested order

1. **1.1** — decide persist-or-remove. Currently the UI promises what storage
   does not deliver.
2. **2.1 + 1.3 + 1.7** — one change. Typed SSE fixes error delivery and removes
   the thinking regex from the view layer.
3. **1.4** — request model. Fifteen minutes.
4. **1.5 + 1.6** — inject the provider, add `cost_usd` while the table is small.
5. **2.3** — per-feature model, once 1.5 makes providers swappable.
6. **2.2** — only if async SQLAlchemy is on the roadmap. Harmless to note now,
   expensive to discover later.
