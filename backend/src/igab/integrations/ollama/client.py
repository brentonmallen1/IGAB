import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

#: Response fields worth keeping off a completion. `prompt_eval_count` and
#: `eval_count` are Ollama's token counts; the app discarded both until the
#: call log needed them.
_META_KEYS = ("thinking", "done_reason", "prompt_eval_count", "eval_count")

#: How long Ollama may send nothing before the call fails. The first gap
#: includes loading the model and reading the image, which is the slow part.
STALL_TIMEOUT_S = 120.0
CONNECT_TIMEOUT_S = 10.0

#: `done_reason` values the app sets itself when it stops a stream. Ollama's
#: own are "stop" and "length".
STOP_DEADLINE = "deadline"
STOP_REPETITION = "repetition"
#: Every reason that means the answer was cut short rather than finished.
CUT_SHORT = frozenset({"length", STOP_DEADLINE, STOP_REPETITION})

#: Given the answer so far, a reason to stop now, or None to keep reading.
StopCheck = Callable[[str], str | None]


def _raise_stream_error(chunk: dict, resp: httpx.Response) -> None:
    """Ollama reports a failure after the 200 as an {"error": ...} line. Raised
    as the 500 it would have been unstreamed, so the retry rules hold."""
    detail = chunk.get("error")
    if not detail:
        return
    raise httpx.HTTPStatusError(
        f"Ollama returned 500: {detail}",
        request=resp.request,
        response=httpx.Response(500, request=resp.request),
    )


def _raise_with_detail(resp: httpx.Response) -> None:
    """raise_for_status, carrying Ollama's own reason. A 500 from Ollama has a
    body like {"error": "prediction aborted, token repeat limit reached"}; the
    bare status said only "Server error", which is how a thinking loop read as
    an unexplained failure. Still an HTTPStatusError, so retry rules hold."""
    if not resp.is_error:
        return
    try:
        body = resp.json()
    except ValueError:
        body = None
    detail = body.get("error") if isinstance(body, dict) else None
    if not isinstance(detail, str) or not detail:
        resp.raise_for_status()
    raise httpx.HTTPStatusError(
        f"Ollama returned {resp.status_code}: {detail}", request=resp.request, response=resp
    )


@dataclass
class _StreamedReply:
    """What a streamed /api/generate call has sent so far. Kept outside the
    read so a deadline that interrupts it still leaves the partial answer."""

    answer: list[str] = field(default_factory=list)
    thinking: list[str] = field(default_factory=list)
    final: dict = field(default_factory=dict)
    stopped: str | None = None

    async def read(self, resp: httpx.Response, stop_when: StopCheck | None) -> None:
        if resp.is_error:
            await resp.aread()
            _raise_with_detail(resp)
        async for line in resp.aiter_lines():
            if not line.strip():
                continue
            chunk = json.loads(line)
            _raise_stream_error(chunk, resp)
            piece = chunk.get("response") or ""
            self.answer.append(piece)
            self.thinking.append(chunk.get("thinking") or "")
            if chunk.get("done"):
                self.final = chunk
                return
            # Only worth checking when something closed: guards look at
            # whole objects.
            if stop_when is not None and "}" in piece:
                self.stopped = stop_when("".join(self.answer))
                if self.stopped:
                    return

    def meta(self) -> dict:
        """The same keys an unstreamed body carried, plus the app's own stop
        reason when it ended the stream."""
        meta = {key: self.final[key] for key in _META_KEYS if key in self.final}
        thinking = "".join(self.thinking)
        if thinking:
            meta["thinking"] = thinking
        if self.stopped:
            meta["done_reason"] = self.stopped
        return meta


class OllamaClient:
    def __init__(self, host: str, model: str) -> None:
        self.host = host.rstrip("/")
        self.model = model
        # Metadata of the last /api/generate response — thinking text,
        # done_reason and token counts. Kept so a parse failure can be
        # diagnosed: a thinking model may put its JSON in "thinking" and leave
        # "response" empty, which otherwise looks like the model returned
        # nothing. The counts are what the call log reports as tokens.
        self.last_meta: dict | None = None

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        *,
        images: list[str] | None = None,
        format: str | dict | None = None,
        think: bool | None = None,
        options: dict | None = None,
        timeout: float = 60.0,
        stop_when: StopCheck | None = None,
    ) -> str:
        """Call /api/generate, streamed, and return the whole answer text.

        images: base64-encoded image bytes (no data-URI prefix).
        format: "json" for JSON mode, or a JSON-schema dict (newer Ollama).
        think: only sent when not None — older servers reject the field.
        options: model options (temperature, num_ctx, ...) passed through as-is.

        Streamed so that `timeout` can be a deadline on the whole call rather
        than the only thing that ends it. Unstreamed, a model looping in its
        answer ran until httpx's read timeout, and the stop reason Ollama
        would have given never arrived. Now:

        - Ollama going silent for `STALL_TIMEOUT_S` still raises ReadTimeout.
        - Reaching `timeout` stops reading and returns what arrived, with
          `done_reason` "deadline".
        - `stop_when(answer_so_far)` returning a reason stops the same way,
          with that reason as `done_reason`.

        Leaving the stream closes the connection, which is what makes Ollama
        stop generating.
        """
        payload: dict = {"model": self.model, "prompt": prompt, "stream": True}
        if system:
            payload["system"] = system
        if images:
            payload["images"] = images
        if format is not None:
            payload["format"] = format
        if think is not None:
            payload["think"] = think
        if options:
            payload["options"] = options
        reply = _StreamedReply()
        http_timeout = httpx.Timeout(min(timeout, STALL_TIMEOUT_S), connect=CONNECT_TIMEOUT_S)
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            try:
                async with asyncio.timeout(timeout):
                    async with client.stream(
                        "POST", f"{self.host}/api/generate", json=payload
                    ) as resp:
                        await reply.read(resp, stop_when)
            except TimeoutError:
                reply.stopped = STOP_DEADLINE
        self.last_meta = reply.meta()
        return "".join(reply.answer)

    async def chat(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        think: bool | None = None,
        options: dict | None = None,
        timeout: float = 120.0,
    ) -> dict:
        """Call /api/chat and return the whole response body.

        A separate method rather than a flag on `generate`: that one posts to
        a different endpoint, hardcodes `stream: False`, and returns a string.
        This returns the body because the caller needs `message.tool_calls`
        alongside the text, and the token counts beside both.

        Non-streaming on purpose. A tool round trip has nothing to show until
        the model has decided which tool to call, and the chat endpoint streams
        its own typed events rather than passing tokens straight through.
        """
        payload: dict = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        if think is not None:
            payload["think"] = think
        if options:
            payload["options"] = options
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self.host}/api/chat", json=payload)
            _raise_with_detail(resp)
            body = resp.json()
            self.last_meta = {key: body[key] for key in _META_KEYS if key in body}
            message = body.get("message") or {}
            # Ollama puts a thinking model's reasoning on the message, not at
            # the top level as /api/generate does.
            if message.get("thinking"):
                self.last_meta["thinking"] = message["thinking"]
            return body

    async def show(self, model: str | None = None) -> dict:
        """Call /api/show for model metadata. Returns {} when unavailable.

        Newer Ollama includes a "capabilities" list ("completion", "vision",
        "thinking", ...); callers must tolerate its absence on older servers.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.host}/api/show", json={"model": model or self.model}
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return {}

    async def context_length(self, model: str | None = None) -> int | None:
        """The model's maximum context, from /api/show's model_info, or None.

        The key is architecture-prefixed ("gemma4.context_length",
        "llama.context_length"), so it is found by suffix. This is what the
        model *can* take, not what the server will allocate — that is
        ``num_ctx``, which the caller decides.
        """
        info = await self.show(model)
        model_info = info.get("model_info")
        if not isinstance(model_info, dict):
            return None
        for key, value in model_info.items():
            if str(key).endswith(".context_length") and isinstance(value, int) and value > 0:
                return value
        return None

    async def capabilities(self, model: str | None = None) -> list[str] | None:
        """Model capabilities, or None when the server doesn't report them."""
        info = await self.show(model)
        caps = info.get("capabilities")
        if isinstance(caps, list):
            return [str(c) for c in caps]
        return None

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.host}/")
                return resp.status_code < 500
        except Exception:
            return False
