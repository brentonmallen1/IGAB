import httpx


class OllamaClient:
    def __init__(self, host: str, model: str) -> None:
        self.host = host.rstrip("/")
        self.model = model
        # Metadata of the last /api/generate response — thinking text and
        # done_reason. Kept so a parse failure can be diagnosed: a thinking
        # model may put its JSON in "thinking" and leave "response" empty,
        # which otherwise looks like the model returned nothing.
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
            self.last_meta = {key: body[key] for key in ("thinking", "done_reason") if key in body}
            return body["response"]

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
