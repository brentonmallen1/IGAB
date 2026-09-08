import httpx

#: Response fields worth keeping off a completion. `prompt_eval_count` and
#: `eval_count` are Ollama's token counts; the app discarded both until the
#: call log needed them.
_META_KEYS = ("thinking", "done_reason", "prompt_eval_count", "eval_count")


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
    ) -> str:
        """Call /api/generate.

        images: base64-encoded image bytes (no data-URI prefix).
        format: "json" for JSON mode, or a JSON-schema dict (newer Ollama).
        think: only sent when not None — older servers reject the field.
        options: model options (temperature, num_ctx, ...) passed through as-is.
        """
        payload: dict = {"model": self.model, "prompt": prompt, "stream": False}
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
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self.host}/api/generate", json=payload)
            resp.raise_for_status()
            body = resp.json()
            self.last_meta = {key: body[key] for key in _META_KEYS if key in body}
            return body["response"]

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
            resp.raise_for_status()
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
