import asyncio
import base64
import json
import time
import uuid
from collections.abc import Sequence
from datetime import date
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.ai.context import AICallContext
from igab.ai.context_window import resolve_num_ctx
from igab.ai.gateway import AIGateway
from igab.db.models import Category, Payee, Transaction
from igab.domain.payee_names import derived_match_patterns, rank_match_patterns
from igab.integrations.ollama.client import OllamaClient
from igab.services.ai_prompts import DEFAULT_PROMPTS, render_prompt
from igab.services.category_matching import match_category
from igab.services.settings_service import SettingsService

# Images sent to the model: longest side capped and re-encoded as JPEG.
# The stored attachment stays full-quality WebP; vision preprocessors are
# more reliable with JPEG, and base64 blowup makes big payloads slow.
MODEL_IMAGE_MAX_DIM = 1536
MODEL_IMAGE_JPEG_QUALITY = 85

# How many candidate match patterns the suggester hands back. Enough to show
# the tight-versus-general trade-off; few enough to pick from at a glance.
REGEX_CANDIDATES = 3

# /api/show capability probe cache: (host, model) -> (capabilities|None, expiry)
_CAPS_TTL_S = 300
_caps_cache: dict[tuple[str, str], tuple[list[str] | None, float]] = {}


_ctx_cache: dict[tuple[str, str], tuple[int | None, float]] = {}


def invalidate_capabilities() -> None:
    """Drop the cached /api/show probe.

    Call whenever the host or a model setting changes. Without this, a user who
    pulls a vision model and immediately reprocesses a failed receipt can still
    hit a cached 'no vision' answer for up to five minutes and watch the retry
    fail for a reason they already fixed.
    """
    _caps_cache.clear()
    _ctx_cache.clear()
    _ctx_cache.clear()


def prepare_image_for_model(file_content: bytes) -> str:
    """Downscale + JPEG-encode an uploaded image and return base64 for Ollama.

    PDFs are rasterized (first page) before encoding — vision models only
    take pixels."""
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    from igab.utils.pdf import is_pdf, render_pdf_first_page

    register_heif_opener()

    if is_pdf(file_content):
        file_content = render_pdf_first_page(file_content)

    img = Image.open(BytesIO(file_content))
    # Phones store a portrait photo as landscape pixels plus an EXIF rotation
    # tag; PIL does not apply it. Without this the model is handed a receipt
    # lying on its side, and vision models read rotated text markedly worse.
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > MODEL_IMAGE_MAX_DIM or img.height > MODEL_IMAGE_MAX_DIM:
        img.thumbnail((MODEL_IMAGE_MAX_DIM, MODEL_IMAGE_MAX_DIM), Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=MODEL_IMAGE_JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _json_from_response(raw: str) -> dict:
    """Parse a model response that should be a JSON object; tolerates code
    fences. Raises json.JSONDecodeError / ValueError on junk (retryable —
    the model may produce valid JSON on the next attempt)."""
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")
    return data


class AIService:
    def __init__(self, session: AsyncSession, settings: SettingsService) -> None:
        self.session = session
        self.settings = settings
        # Every model call goes through here, and the gateway records it. The
        # `last_request` / `last_response` fields this class used to carry are
        # gone: they were a second, partial copy of what the call log now holds
        # for every feature rather than only for the two that remembered to set
        # them.
        self.gateway = AIGateway(settings)
        #: Set by the receipt and NL paths so the job row can link to the call
        #: the worker just made. The record itself lives in `ai_calls`.
        self.last_call: AICallContext | None = None

    async def _client(self) -> OllamaClient:
        host = await self.settings.get("ollama_host") or "http://localhost:11434"
        model = await self.settings.get("ollama_model") or "llama3.2"
        return OllamaClient(host, model)

    async def _resolve_vision_model(self) -> tuple[str, bool]:
        """The model receipt scans will use, and whether the vision override
        supplied it (False = fell through to the main model / default).

        This is the single owner of the fallback chain — the status endpoint
        reports its result so the UI never re-implements the resolution."""
        override = await self.settings.get("ollama_vision_model")
        if override:
            return override, True
        return await self.settings.get("ollama_model") or "llama3.2", False

    async def _vision_client(self) -> OllamaClient:
        """Client for vision tasks: the vision-model override when set,
        otherwise the primary model."""
        host = await self.settings.get("ollama_host") or "http://localhost:11434"
        model, _ = await self._resolve_vision_model()
        return OllamaClient(host, model)

    async def _capabilities(self, client: OllamaClient) -> list[str] | None:
        """Model capabilities via /api/show, cached briefly. None means the
        server doesn't report capabilities (older Ollama) — callers must
        degrade gracefully, never hard-fail."""
        key = (client.host, client.model)
        cached = _caps_cache.get(key)
        now = time.monotonic()
        if cached and cached[1] > now:
            return cached[0]
        caps = await client.capabilities()
        _caps_cache[key] = (caps, now + _CAPS_TTL_S)
        return caps

    async def _context_length(self, client: OllamaClient) -> int | None:
        """The model's advertised context, cached beside the capabilities."""
        key = (client.host, client.model)
        cached = _ctx_cache.get(key)
        now = time.monotonic()
        if cached and cached[1] > now:
            return cached[0]
        length = await client.context_length()
        _ctx_cache[key] = (length, now + _CAPS_TTL_S)
        return length

    async def _resolve_chat_model(self) -> tuple[str, bool]:
        """(model, from_override): the assistant's model through its fallback
        chain, the same shape as the vision one."""
        override = await self.settings.get("ollama_chat_model")
        if override:
            return override, True
        return await self.settings.get("ollama_model") or "llama3.2", False

    async def chat_window(self, client: OllamaClient) -> tuple[int, int | None]:
        """(num_ctx to request, the model's own maximum or None)."""
        model_max = await self._context_length(client)
        setting = await self.settings.get("ai_chat_num_ctx")
        return resolve_num_ctx(setting, model_max), model_max

    async def _resolve_think(self, client: OllamaClient) -> bool | None:
        """auto = think only when the model advertises it; on/off force.
        Returns None (field omitted) rather than False for off — older
        servers reject the field entirely."""
        mode = await self.settings.get("ai_thinking") or "auto"
        if mode == "on":
            return True
        if mode == "off":
            return None
        caps = await self._capabilities(client)
        return True if caps and "thinking" in caps else None

    async def _merged_options(self, *, vision: bool, task_defaults: dict) -> dict:
        """options = task defaults < ollama_options < ollama_vision_options.
        The pass-through JSON settings are the model-agnostic escape hatch
        for model-specific tuning (image tokens, num_ctx, ...)."""
        options = dict(task_defaults)
        keys = ["ollama_options"] + (["ollama_vision_options"] if vision else [])
        for key in keys:
            raw = await self.settings.get(key) or "{}"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue  # invalid user JSON is rejected at save; never break a call
            if isinstance(parsed, dict):
                options.update(parsed)
        return options

    async def _prompt(self, key: str, values: dict[str, str]) -> str:
        template = await self.settings.get(key) or DEFAULT_PROMPTS[key]
        return render_prompt(template, values)

    async def check_availability(self) -> dict:
        """Check if AI is enabled and Ollama is reachable."""
        enabled = (await self.settings.get("ai_enabled") or "false").lower() == "true"
        host = await self.settings.get("ollama_host")
        model = await self.settings.get("ollama_model")
        vision_model = await self.settings.get("ollama_vision_model") or None
        # Resolved through the real fallback chain so the settings UI can say
        # "receipts are scanned by X" without re-implementing the resolution.
        receipt_model, _ = await self._resolve_vision_model()
        chat_model, _ = await self._resolve_chat_model()
        result: dict = {
            "enabled": enabled,
            "available": False,
            "host": host,
            "model": model,
            "vision_model": vision_model,
            "receipt_model": receipt_model,
            "receipt_model_vision": None,
            "chat_model": chat_model,
            "chat_model_tools": None,
            "chat_model_context_length": None,
            "chat_num_ctx": None,
        }
        if not enabled or not host:
            return result

        client = await self._client()
        available = await client.health()
        result["available"] = available
        # Same /api/show probe the worker gates receipt scans on and the chat
        # route gates tools on, so the settings UI cannot disagree with what
        # actually happens. None = unknown (Ollama unreachable or too old to
        # report capabilities).
        if available:
            result["receipt_model_vision"], _, _ = await self.check_vision_support()
            chat_client = await self.gateway.client(model=chat_model)
            caps = await self._capabilities(chat_client)
            result["chat_model_tools"] = None if caps is None else "tools" in caps
            num_ctx, model_max = await self.chat_window(chat_client)
            result["chat_model_context_length"] = model_max
            result["chat_num_ctx"] = num_ctx
        return result

    # /api/show probes fan out one request per model; keep the burst small
    # so a remote Ollama isn't hammered just to render the settings page.
    _SHOW_CONCURRENCY = 8

    async def list_models(self) -> list[dict]:
        """List available models from the configured Ollama instance.

        /api/tags carries a capabilities list, but it under-reports: for some
        models (the gemma4 family, notably) it omits the "vision" that
        /api/show reports for the very same tag. Receipt scans are gated on
        /api/show, so a UI built on the tags list contradicts what the worker
        does — it labeled a working vision model "does not support vision".
        Probe /api/show per model (cached, concurrent) and let it win.
        """
        host = await self.settings.get("ollama_host")
        if not host:
            return []

        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.get(f"{host.rstrip('/')}/api/tags")
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        models = [
            {
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "capabilities": m.get("capabilities", []),
                "context_length": None,
            }
            for m in data.get("models", [])
        ]

        sem = asyncio.Semaphore(self._SHOW_CONCURRENCY)

        async def enrich(entry: dict) -> None:
            if not entry["name"]:
                return
            async with sem:
                client = OllamaClient(host, entry["name"])
                caps = await self._capabilities(client)
                entry["context_length"] = await self._context_length(client)
            # None = the server didn't report capabilities; keep the tags
            # value rather than blanking the list.
            if caps is not None:
                entry["capabilities"] = caps

        await asyncio.gather(*(enrich(m) for m in models))
        return models

    async def check_vision_support(self) -> tuple[bool | None, str, bool]:
        """(supported, model, from_override): True/False when the server
        reports capabilities, None when it doesn't (unknown — let the job
        try). from_override says whether the vision override supplied the
        model — the failure copy must name where the model came from, since
        "set a vision model" is the wrong advice when the fix is changing
        the main model."""
        model, from_override = await self._resolve_vision_model()
        client = await self._vision_client()
        caps = await self._capabilities(client)
        if caps is None:
            return None, model, from_override
        return "vision" in caps, model, from_override

    async def is_receipt_image(self, image_b64: str) -> bool | None:
        """Cheap gate before full extraction: is this even a receipt?

        Kept deliberately light — tiny output budget, thinking never enabled.
        Returns None when inconclusive (unparseable answer): the gate must
        never block a real receipt, so inconclusive proceeds to extraction.
        Transport errors propagate — they'd fail extraction anyway and the
        worker's retry/backoff should see them.
        """
        prompt = await self._prompt("ai_prompt_receipt_gate", {})
        client = await self._vision_client()
        raw = await self.gateway.complete(
            context=AICallContext(feature="receipt_gate"),
            client=client,
            prompt=prompt,
            system="You are an image classifier. Return only valid JSON.",
            images=[image_b64],
            format="json",
            options=await self._merged_options(
                vision=True, task_defaults={"temperature": 0, "num_predict": 64}
            ),
            timeout=float(await self.settings.get("ai_vision_timeout_s") or "300"),
        )
        try:
            data = _json_from_response(raw)
        except Exception:
            return None
        value = data.get("is_receipt")
        return value if isinstance(value, bool) else None

    async def extract_receipt(
        self, budget_id: uuid.UUID, image_b64: str, client_today: date
    ) -> dict:
        """Vision extraction of a receipt photo into the JSON contract that
        ai_draft_service.parse_extraction() consumes."""
        categories = await self._get_categories(budget_id)
        cat_list = "\n".join(f"- {c['name']} ({c['group']})" for c in categories)
        prompt = await self._prompt(
            "ai_prompt_receipt_extract",
            {"categories": cat_list, "today": client_today.isoformat()},
        )
        client = await self._vision_client()
        think = await self._resolve_think(client)
        system = "You are a receipt data extraction engine. Return only valid JSON."
        self.last_call = AICallContext(feature="receipt_extract", budget_id=budget_id)
        raw = await self.gateway.complete(
            context=self.last_call,
            client=client,
            prompt=prompt,
            system=system,
            images=[image_b64],
            # The JSON grammar constrains decoding from the first token, which
            # silently suppresses the thinking phase — never combine the two.
            # _json_from_response tolerates the fenced output this produces.
            format=None if think else "json",
            think=think,
            options=await self._merged_options(vision=True, task_defaults={"temperature": 0}),
            timeout=float(await self.settings.get("ai_vision_timeout_s") or "300"),
        )
        return _json_from_response(raw)

    async def parse_nl_transaction(
        self, budget_id: uuid.UUID, text: str, client_today: date
    ) -> dict:
        """Parse a natural-language description ("coffee starbucks 5.50
        yesterday") into the NL JSON contract for parse_extraction()."""
        categories = await self._get_categories(budget_id)
        cat_list = "\n".join(f"- {c['name']} ({c['group']})" for c in categories)
        prompt = await self._prompt(
            "ai_prompt_nl_parse",
            {"text": text, "categories": cat_list, "today": client_today.isoformat()},
        )
        client = await self._client()
        think = await self._resolve_think(client)
        system = "You are a transaction parser. Return only valid JSON."
        self.last_call = AICallContext(feature="nl_parse", budget_id=budget_id)
        raw = await self.gateway.complete(
            context=self.last_call,
            client=client,
            prompt=prompt,
            system=system,
            # Same think/format conflict as extract_receipt: grammar kills thinking.
            format=None if think else "json",
            think=think,
            options=await self._merged_options(vision=False, task_defaults={"temperature": 0}),
        )
        return _json_from_response(raw)

    async def suggest_category(
        self,
        budget_id: uuid.UUID,
        payee_name: str,
        amount: float,
        memo: str | None = None,
    ) -> dict:
        categories = await self._get_categories(budget_id)
        if not categories:
            return {"category_id": None, "category_name": None, "confidence": 0.0}

        cat_list = "\n".join(f"- {c['name']} ({c['group']})" for c in categories)
        prompt = await self._prompt(
            "ai_prompt_suggest_category",
            {
                "payee_name": payee_name,
                "amount": str(amount),
                "memo": memo or "",
                "categories": cat_list,
            },
        )
        system = "You are a financial transaction categorizer. Return only JSON."

        try:
            client = await self._client()
            raw = await self.gateway.complete(
                context=AICallContext(feature="suggest_category", budget_id=budget_id),
                client=client,
                prompt=prompt,
                system=system,
                format="json",
                options=await self._merged_options(vision=False, task_defaults={"temperature": 0}),
            )
            data = _json_from_response(raw)
            name = data.get("category")
            confidence = float(data.get("confidence", 0.5))
            index = match_category(
                name if isinstance(name, str) else None,
                [(c["name"], c["group"]) for c in categories],
            )
            matched = categories[index] if index is not None else None
            return {
                "category_id": str(matched["id"]) if matched else None,
                "category_name": matched["name"] if matched else None,
                "confidence": confidence,
            }
        except Exception:
            return {"category_id": None, "category_name": None, "confidence": 0.0}

    async def suggest_regex(self, budget_id: uuid.UUID, names: list[str]) -> list[str]:
        """Candidate match patterns generalizing a set of raw payee names,
        best first.

        The model is a source of guesses, not of answers. Three things make
        the result dependable rather than a coin flip, and all three are
        verification rather than prompting:

        - Every candidate is CHECKED against the names, by the same
          `pattern_matches` the importer uses, and ranked by how many it
          covers. A pattern that does not do the job cannot come first.
        - Over-generality is measured, not guessed: the budget's other payees
          go in as `avoid`, so `.*` and `^A` — which "match every name" — sink
          below anything that does not also swallow the register.
        - `derived_match_patterns` appends candidates computed from the names
          themselves, the last of which matches all of them by construction.
          So a model that returns nonsense, times out, or is not installed at
          all still produces a working answer instead of an empty list.
        """
        cleaned = [n.strip() for n in names if n.strip()]
        if not cleaned:
            return []
        candidates: list[object] = []
        prompt = await self._prompt("ai_prompt_suggest_regex", {"names": "\n".join(cleaned)})
        try:
            client = await self._client()
            raw = await self.gateway.complete(
                context=AICallContext(feature="suggest_regex", budget_id=budget_id),
                client=client,
                prompt=prompt,
                format="json",
                options=await self._merged_options(vision=False, task_defaults={"temperature": 0}),
            )
            data = _json_from_response(raw)
            # A saved override of the older prompt still answers with one
            # "pattern".
            proposed = data.get("patterns")
            candidates = list(proposed) if isinstance(proposed, list) else [data.get("pattern")]
        except Exception:
            # No model, no network, unparseable JSON — the derived patterns
            # below are the whole answer, and they are still a usable one.
            candidates = []
        candidates.extend(derived_match_patterns(cleaned))
        return rank_match_patterns(
            candidates,
            cleaned,
            REGEX_CANDIDATES,
            avoid=await self._other_payee_names(budget_id, cleaned),
        )

    async def _other_payee_names(self, budget_id: uuid.UUID, names: Sequence[str]) -> list[str]:
        """The budget's payees that are NOT the ones being merged.

        What "too general" is checked against. Names only — the pattern is
        judged on strings, and loading the rows keeps this one query.
        """
        chosen = {n.casefold() for n in names}
        rows = await self.session.execute(
            select(Payee.name).where(
                Payee.budget_id == budget_id,
                Payee.is_deleted == False,  # noqa: E712
            )
        )
        return [name for (name,) in rows if name and name.casefold() not in chosen]

    async def spending_insights(self, budget_id: uuid.UUID, month: date) -> str:
        month_start = month.replace(day=1)
        next_month = month_start.replace(
            year=month_start.year + (1 if month_start.month == 12 else 0),
            month=1 if month_start.month == 12 else month_start.month + 1,
        )

        q = (
            select(
                Category.name,
                Transaction.amount,
            )
            .join(Transaction, Transaction.category_id == Category.id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.date >= month_start,
                Transaction.date < next_month,
                Transaction.parent_transaction_id.is_(None),
            )
        )
        result = await self.session.execute(q)
        rows = result.all()

        if not rows:
            return "No transaction data available for this month."

        summary = {}
        for name, amt in rows:
            summary[name] = summary.get(name, 0) + float(amt)

        summary_text = "\n".join(
            f"- {name}: ${abs(total):.2f} ({'expense' if total < 0 else 'income'})"
            for name, total in sorted(summary.items(), key=lambda x: x[1])
        )

        prompt = (
            f"Monthly budget summary for {month_start.strftime('%B %Y')}:\n{summary_text}\n\n"
            "Provide 2-3 sentences of spending insights and one actionable suggestion."
        )
        system = "You are a helpful personal finance advisor."
        try:
            client = await self._client()
            return await self.gateway.complete(
                context=AICallContext(feature="spending_insights", budget_id=budget_id),
                client=client,
                prompt=prompt,
                system=system,
            )
        except Exception:
            return "Unable to generate insights — check Ollama connection in Settings."

    async def _get_categories(self, budget_id: uuid.UUID) -> list[dict]:
        from igab.db.models import CategoryGroup

        result = await self.session.execute(
            select(Category.id, Category.name, CategoryGroup.name.label("group"))
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Category.budget_id == budget_id,
                Category.is_deleted == False,  # noqa: E712
                Category.is_archived == False,  # noqa: E712
            )
        )
        return [{"id": r.id, "name": r.name, "group": r.group} for r in result.all()]
