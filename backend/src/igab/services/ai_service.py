import asyncio
import base64
import json
import re
import time
import uuid
from datetime import date
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, Transaction
from igab.integrations.ollama.client import OllamaClient
from igab.services.ai_prompts import DEFAULT_PROMPTS, render_prompt
from igab.services.category_matching import match_category
from igab.services.settings_service import SettingsService

# Images sent to the model: longest side capped and re-encoded as JPEG.
# The stored attachment stays full-quality WebP; vision preprocessors are
# more reliable with JPEG, and base64 blowup makes big payloads slow.
MODEL_IMAGE_MAX_DIM = 1536
MODEL_IMAGE_JPEG_QUALITY = 85

# /api/show capability probe cache: (host, model) -> (capabilities|None, expiry)
_CAPS_TTL_S = 300
_caps_cache: dict[tuple[str, str], tuple[list[str] | None, float]] = {}


def invalidate_capabilities() -> None:
    """Drop the cached /api/show probe.

    Call whenever the host or a model setting changes. Without this, a user who
    pulls a vision model and immediately reprocesses a failed receipt can still
    hit a cached 'no vision' answer for up to five minutes and watch the retry
    fail for a reason they already fixed.
    """
    _caps_cache.clear()


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
        # The exact request of the last extraction/parse call — recorded
        # before the model is invoked so callers can persist it for
        # debugging even when the call itself fails.
        self.last_request: dict | None = None
        # The raw text of the last model response (plus thinking, when the
        # model produced any), captured BEFORE parsing — a JSON-parse failure
        # must leave evidence of what the model actually said.
        self.last_response: dict | None = None

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

    # Thinking transcripts can be enormous; cap what we keep for the log.
    _RESPONSE_KEEP_CHARS = 100_000

    def _record_response(self, raw: str, client: OllamaClient) -> None:
        self.last_response = {
            "response": raw[: self._RESPONSE_KEEP_CHARS],
            **{
                k: (v[: self._RESPONSE_KEEP_CHARS] if isinstance(v, str) else v)
                for k, v in (client.last_meta or {}).items()
            },
        }

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

        if not enabled or not host:
            return {
                "enabled": enabled,
                "available": False,
                "host": host,
                "model": model,
                "vision_model": vision_model,
                "receipt_model": receipt_model,
                "receipt_model_vision": None,
            }

        client = await self._client()
        available = await client.health()
        # Same /api/show probe the worker gates receipt scans on, so the
        # settings UI cannot disagree with what actually happens. None =
        # unknown (Ollama unreachable or too old to report capabilities).
        receipt_model_vision = None
        if available:
            receipt_model_vision, _, _ = await self.check_vision_support()
        return {
            "enabled": enabled,
            "available": available,
            "host": host,
            "model": model,
            "vision_model": vision_model,
            "receipt_model": receipt_model,
            "receipt_model_vision": receipt_model_vision,
        }

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
            }
            for m in data.get("models", [])
        ]

        sem = asyncio.Semaphore(self._SHOW_CONCURRENCY)

        async def enrich(entry: dict) -> None:
            if not entry["name"]:
                return
            async with sem:
                caps = await self._capabilities(OllamaClient(host, entry["name"]))
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
        raw = await client.generate(
            prompt,
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
        self.last_request = {
            "prompt": prompt,
            "system": system,
            "model": client.model,
            "think": think,
            "format": None if think else "json",
        }
        self.last_response = None
        raw = await client.generate(
            prompt,
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
        self._record_response(raw, client)
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
        self.last_request = {
            "prompt": prompt,
            "system": system,
            "model": client.model,
            "think": think,
            "format": None if think else "json",
        }
        self.last_response = None
        raw = await client.generate(
            prompt,
            system=system,
            # Same think/format conflict as extract_receipt: grammar kills thinking.
            format=None if think else "json",
            think=think,
            options=await self._merged_options(vision=False, task_defaults={"temperature": 0}),
        )
        self._record_response(raw, client)
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
            raw = await client.generate(
                prompt,
                system,
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

    async def suggest_regex(self, names: list[str]) -> str | None:
        """Suggest a match pattern generalizing a set of raw payee names.

        Returns None when the model produces nothing usable — the caller falls
        back to the frontend's structural heuristic.
        """
        cleaned = [n.strip() for n in names if n.strip()]
        if not cleaned:
            return None
        prompt = await self._prompt("ai_prompt_suggest_regex", {"names": "\n".join(cleaned)})
        try:
            client = await self._client()
            raw = await client.generate(
                prompt,
                format="json",
                options=await self._merged_options(vision=False, task_defaults={"temperature": 0}),
            )
            data = _json_from_response(raw)
            pattern = data.get("pattern")
            if not isinstance(pattern, str) or not pattern.strip():
                return None
            # Trim newline junk only — a trailing space is significant in a
            # regex ("^ACH DEPOSIT PAYROLL " must keep it).
            pattern = pattern.strip("\r\n")
            re.compile(pattern)
            return pattern
        except Exception:
            return None

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
            return await client.generate(prompt, system)
        except Exception:
            return "Unable to generate insights — check Ollama connection in Settings."

    async def suggest_payee_merges(self, budget_id: uuid.UUID) -> list[dict]:
        """Return groups of payees that appear to be the same vendor."""
        from igab.db.models import Payee

        result = await self.session.execute(
            select(Payee.id, Payee.name)
            .where(
                Payee.budget_id == budget_id,
                Payee.is_deleted == False,  # noqa: E712
                Payee.transfer_account_id.is_(None),
            )
            .order_by(Payee.name)
        )
        payees = [{"id": str(r.id), "name": r.name} for r in result.all()]
        if len(payees) < 2:
            return []

        names_list = "\n".join(f"- {p['id']}: {p['name']}" for p in payees)
        prompt = (
            "Below is a list of payee names from a personal budget app (id: name).\n"
            "Identify groups of payees that are likely the same vendor "
            "(e.g. 'AMAZON', 'Amazon.com', 'AMAZON PRIME' are all Amazon).\n"
            "Return a JSON array of groups, each with:\n"
            '  {"canonical": "<display name>", "ids": ["<uuid>", ...]}\n'
            "Only include groups with 2+ entries. Output only valid JSON array.\n\n"
            f"Payees:\n{names_list}"
        )
        system = "You are a data-deduplication assistant. Return only a JSON array."
        try:
            client = await self._client()
            raw = await client.generate(prompt, system)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
                raw = raw.rstrip("`").strip()
            groups = json.loads(raw)
            payee_map = {p["id"]: p["name"] for p in payees}
            result_groups = []
            for g in groups:
                valid_ids = [i for i in g.get("ids", []) if i in payee_map]
                if len(valid_ids) >= 2:
                    result_groups.append(
                        {
                            "canonical": g.get("canonical", payee_map[valid_ids[0]]),
                            "payees": [{"id": i, "name": payee_map[i]} for i in valid_ids],
                        }
                    )
            return result_groups
        except Exception:
            return []

    async def _get_categories(self, budget_id: uuid.UUID) -> list[dict]:
        from igab.db.models import CategoryGroup

        result = await self.session.execute(
            select(Category.id, Category.name, CategoryGroup.name.label("group"))
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Category.budget_id == budget_id,
                Category.is_deleted == False,  # noqa: E712
                Category.is_hidden == False,  # noqa: E712
            )
        )
        return [{"id": r.id, "name": r.name, "group": r.group} for r in result.all()]
