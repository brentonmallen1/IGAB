"""The one place this app talks to a model.

Before this, six call sites built their own `OllamaClient` and three of them
recorded nothing, so "what did the AI actually send?" had two answers on the
receipt path and none anywhere else. Adding a chat feature beside them would
have made a seventh. One rule, one implementation: every model call in the app
goes through `AIGateway`, and every one of them is recorded.

**Recording happens in a `finally`**, so a call that raised or was cancelled is
recorded too — see `call_log.submit` for why that `finally` may not await.

The gateway owns transport and the record. It does not own prompts, parsing or
domain meaning: `AIService` still decides what to ask and what an answer means.
That split is what keeps this file from becoming the second place budget rules
live.
"""

import json
import time

from igab.ai import call_log
from igab.ai.context import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_OK,
    AICallContext,
    AICallResult,
)
from igab.ai.features import describe
from igab.integrations.ollama.client import OllamaClient
from igab.services.settings_service import SettingsService

#: Ollama reports token counts under these keys on both /api/generate and
#: /api/chat. The client used to discard the whole metadata block.
_PROMPT_TOKENS = "prompt_eval_count"
_COMPLETION_TOKENS = "eval_count"

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"


class AIGateway:
    """Makes model calls and records them.

    Built per request beside `AIService`, which holds the same
    `SettingsService`, so settings are read through one resolver.
    """

    def __init__(self, settings: SettingsService) -> None:
        self.settings = settings
        #: The most recent call this gateway made. The AI worker copies it onto
        #: the job row so the activity page can show what the model was asked
        #: and what it said — one capture, rendered in two places, rather than
        #: two captures that can disagree.
        self.last_result: AICallResult | None = None

    async def host(self) -> str:
        return await self.settings.get("ollama_host") or DEFAULT_HOST

    async def model(self) -> str:
        return await self.settings.get("ollama_model") or DEFAULT_MODEL

    async def client(self, *, model: str | None = None) -> OllamaClient:
        """A client for `model`, or the configured default."""
        return OllamaClient(await self.host(), model or await self.model())

    async def complete(
        self,
        *,
        context: AICallContext,
        client: OllamaClient,
        prompt: str,
        system: str | None = None,
        images: list[str] | None = None,
        format: str | dict | None = None,
        think: bool | None = None,
        options: dict | None = None,
        timeout: float = 60.0,
    ) -> str:
        """One `/api/generate` call, recorded whatever happens to it.

        Returns the raw response text — parsing stays with the caller, because
        a parse failure must leave the raw text in the log as evidence.
        """
        describe(context.feature)  # an unregistered feature is a bug, not a label
        result = AICallResult(
            context=context,
            model=client.model,
            host=client.host,
            endpoint="generate",
            system=system,
            messages=[{"role": "user", "content": prompt}],
            options=dict(options or {}),
            thinking_enabled=bool(think),
        )
        self.last_result = result
        started = time.monotonic()
        try:
            raw = await client.generate(
                prompt,
                system=system,
                images=images,
                format=format,
                think=think,
                options=options,
                timeout=timeout,
            )
            result.response = raw
            self._absorb_meta(result, client)
            return raw
        except BaseException as exc:  # noqa: BLE001 — recorded, then re-raised
            self._absorb_failure(result, exc)
            raise
        finally:
            result.duration_ms = int((time.monotonic() - started) * 1000)
            call_log.submit(result)

    def _absorb_meta(self, result: AICallResult, client: OllamaClient) -> None:
        """Pull thinking and token counts off the client's last response."""
        meta = client.last_meta or {}
        thinking = meta.get("thinking")
        if isinstance(thinking, str):
            result.thinking = thinking
        prompt_tokens = meta.get(_PROMPT_TOKENS)
        completion_tokens = meta.get(_COMPLETION_TOKENS)
        if isinstance(prompt_tokens, int):
            result.prompt_tokens = prompt_tokens
        if isinstance(completion_tokens, int):
            result.completion_tokens = completion_tokens

    @staticmethod
    def _absorb_failure(result: AICallResult, exc: BaseException) -> None:
        import asyncio

        if isinstance(exc, asyncio.CancelledError):
            result.status = STATUS_CANCELLED
            result.error = "cancelled"
            return
        result.status = STATUS_ERROR
        # Same shape the AI worker records: type plus message, bounded.
        result.error = f"{type(exc).__name__}: {exc}"[:2000]


def json_options(raw: str | None) -> dict:
    """Parse a JSON options setting, tolerating anything a user typed.

    Invalid JSON is rejected when the setting is saved; this is the second
    line, and it must never break a call.
    """
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


__all__ = ["AIGateway", "AICallContext", "STATUS_OK", "json_options"]
