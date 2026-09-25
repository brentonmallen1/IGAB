"""Capability-driven behavior: options merge precedence and think gating.

These are the model-agnostic mechanisms that replace per-model code paths —
any model's quirks flow through settings, not through the codebase.
"""

import asyncio
import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

import igab.services.ai_service as ai_service_module
from igab.ai.context import debug_view
from igab.ai.reply_json import ReplyNotJSON
from igab.integrations.ollama.client import OllamaClient
from igab.services.ai_draft_service import NL_REPLY_SCHEMA, RECEIPT_REPLY_SCHEMA
from igab.services.ai_service import AIService
from igab.services.settings_service import DEFAULTS


@pytest.fixture(autouse=True)
def clear_probe_caches():
    ai_service_module._caps_cache.clear()
    ai_service_module._ctx_cache.clear()
    yield
    ai_service_module._caps_cache.clear()
    ai_service_module._ctx_cache.clear()


def model_reports(monkeypatch, *, caps=None, context_length=None) -> None:
    """What /api/show says about every model, without a network."""
    monkeypatch.setattr(OllamaClient, "capabilities", AsyncMock(return_value=caps))
    monkeypatch.setattr(OllamaClient, "context_length", AsyncMock(return_value=context_length))


def make_service(overrides: dict[str, str] | None = None) -> AIService:
    values = dict(DEFAULTS)
    values.update(overrides or {})
    settings = MagicMock()
    settings.get = AsyncMock(side_effect=lambda key: values.get(key))
    return AIService(session=MagicMock(), settings=settings)


class TestOptionsMerge:
    """options = context window < task defaults < ollama_options <
    ollama_vision_options."""

    CLIENT = OllamaClient("http://x:11434", "m")

    @pytest.fixture(autouse=True)
    def a_128k_model(self, monkeypatch):
        model_reports(monkeypatch, context_length=131_072)

    async def test_task_defaults_over_the_window(self):
        svc = make_service()
        opts = await svc._merged_options(
            self.CLIENT, vision=False, task_defaults={"temperature": 0}
        )
        assert opts == {"num_ctx": 32_768, "temperature": 0}

    async def test_global_options_override_task_defaults_and_the_window(self):
        svc = make_service({"ollama_options": '{"temperature": 0.4, "num_ctx": 8192}'})
        opts = await svc._merged_options(
            self.CLIENT, vision=False, task_defaults={"temperature": 0}
        )
        assert opts == {"temperature": 0.4, "num_ctx": 8192}

    async def test_vision_options_win_for_vision_tasks_only(self):
        svc = make_service(
            {
                "ollama_options": '{"num_ctx": 8192}',
                "ollama_vision_options": '{"num_ctx": 4096, "image_tokens": 512}',
            }
        )
        vision = await svc._merged_options(self.CLIENT, vision=True)
        assert vision == {"num_ctx": 4096, "image_tokens": 512}
        text = await svc._merged_options(self.CLIENT, vision=False)
        assert text == {"num_ctx": 8192}

    async def test_invalid_json_never_breaks_a_call(self):
        svc = make_service({"ollama_options": "{not json"})
        opts = await svc._merged_options(
            self.CLIENT, vision=False, task_defaults={"temperature": 0}
        )
        assert opts == {"num_ctx": 32_768, "temperature": 0}

    async def test_non_object_json_ignored(self):
        svc = make_service({"ollama_options": '["a", "b"]'})
        assert await svc._merged_options(self.CLIENT, vision=False) == {"num_ctx": 32_768}


class TestEveryCallStatesTheSameWindow:
    """Ollama reloads a model whose num_ctx changes, and a call that states
    none gets the server's default — 4,096 on a GPU under 24 GB, where a
    thinking model reading 180 categories ran out of room mid-answer."""

    async def test_gate_scan_nl_and_suggestions_agree(self, monkeypatch):
        sent: list[dict] = []

        async def fake_generate(self, prompt, system=None, **kwargs):
            sent.append(kwargs["options"])
            return '{"is_receipt": true, "total": 1, "category": null}'

        monkeypatch.setattr(OllamaClient, "generate", fake_generate)
        model_reports(monkeypatch, caps=["vision", "thinking"], context_length=131_072)
        svc = make_service()
        monkeypatch.setattr(svc, "_get_categories", AsyncMock(return_value=[]))
        await svc.is_receipt_image("aW1n")
        await svc.extract_receipt(uuid.uuid4(), "aW1n", date(2026, 9, 25))
        await svc.parse_nl_transaction(uuid.uuid4(), "coffee 5.50", date(2026, 9, 25))
        monkeypatch.setattr(
            svc, "_get_categories", AsyncMock(return_value=[{"id": 1, "name": "G", "group": "E"}])
        )
        await svc.suggest_category(uuid.uuid4(), "Harborstone Market", -4.0)
        assert [o["num_ctx"] for o in sent] == [32_768] * 4


class TestThinkGating:
    def client_with_caps(self, caps):
        client = OllamaClient("http://x:11434", "m")
        client.capabilities = AsyncMock(return_value=caps)  # type: ignore[method-assign]
        return client

    async def test_auto_enables_when_advertised(self):
        svc = make_service({"ai_thinking": "auto"})
        assert await svc._resolve_think(self.client_with_caps(["completion", "thinking"])) is True

    async def test_auto_omits_when_not_advertised(self):
        svc = make_service({"ai_thinking": "auto"})
        assert await svc._resolve_think(self.client_with_caps(["completion"])) is None

    async def test_auto_omits_when_server_does_not_report(self):
        svc = make_service({"ai_thinking": "auto"})
        assert await svc._resolve_think(self.client_with_caps(None)) is None

    async def test_forced_on(self):
        svc = make_service({"ai_thinking": "on"})
        assert await svc._resolve_think(self.client_with_caps(None)) is True

    async def test_off_is_false_for_a_model_that_thinks_by_default(self):
        """gemma4 reports thinking {default: true}: leaving the field out was
        not off, it was the model's default."""
        svc = make_service({"ai_thinking": "off"})
        assert await svc._resolve_think(self.client_with_caps(["thinking"])) is False

    async def test_off_omits_the_field_for_a_model_that_does_not_think(self):
        svc = make_service({"ai_thinking": "off"})
        assert await svc._resolve_think(self.client_with_caps(["completion"])) is None

    async def test_off_omits_the_field_for_a_server_too_old_to_say(self):
        svc = make_service({"ai_thinking": "off"})
        assert await svc._resolve_think(self.client_with_caps(None)) is None


class TestVisionSupport:
    async def test_vision_model_override_used(self):
        svc = make_service({"ollama_vision_model": "moondream"})
        client = await svc._vision_client()
        assert client.model == "moondream"

    async def test_empty_override_falls_back_to_primary(self):
        svc = make_service({"ollama_model": "gemma4", "ollama_vision_model": ""})
        client = await svc._vision_client()
        assert client.model == "gemma4"


class TestReceiptGate:
    def gated_service(self, response: str, monkeypatch) -> AIService:
        svc = make_service()
        monkeypatch.setattr(OllamaClient, "generate", AsyncMock(return_value=response))
        model_reports(monkeypatch)
        return svc

    async def test_true_and_false_pass_through(self, monkeypatch):
        svc = self.gated_service('{"is_receipt": true}', monkeypatch)
        assert await svc.is_receipt_image("aW1n") is True
        svc = self.gated_service('{"is_receipt": false}', monkeypatch)
        assert await svc.is_receipt_image("aW1n") is False

    async def test_garbage_is_inconclusive(self, monkeypatch):
        for response in ("not json", '{"is_receipt": "maybe"}', '{"verdict": true}', "[]"):
            svc = self.gated_service(response, monkeypatch)
            assert await svc.is_receipt_image("aW1n") is None

    def capture_gate(self, monkeypatch, caps) -> tuple[AIService, dict]:
        captured: dict = {}

        async def fake_generate(self, prompt, system=None, **kwargs):
            captured.update(kwargs)
            return '{"is_receipt": true}'

        monkeypatch.setattr(OllamaClient, "generate", fake_generate)
        model_reports(monkeypatch, caps=caps)
        return make_service({"ai_thinking": "on"}), captured

    async def test_gate_turns_thinking_off_for_a_model_that_thinks_by_default(self, monkeypatch):
        """With `think` left out gemma4 spent the gate's 64 tokens thinking and
        answered nothing, so the gate was inconclusive on every scan."""
        svc, captured = self.capture_gate(monkeypatch, ["vision", "thinking"])
        assert await svc.is_receipt_image("aW1n") is True
        assert captured["think"] is False
        assert captured["options"]["num_predict"] == 64

    async def test_gate_leaves_think_out_for_a_model_that_does_not_think(self, monkeypatch):
        svc, captured = self.capture_gate(monkeypatch, ["vision"])
        await svc.is_receipt_image("aW1n")
        assert captured["think"] is None


class TestTheReplyHasASchema:
    """`format` carries the schema parse_extraction reads, thinking or not.

    It used to be dropped whenever the model thought ("grammar kills
    thinking"), which left a thinking model free to answer in any shape. On
    Ollama 0.34 gemma4 thinks, then answers to the schema."""

    def capture_service(self, overrides, monkeypatch, caps=None) -> tuple[AIService, dict]:
        captured: dict = {}

        async def fake_generate(self, prompt, system=None, **kwargs):
            captured.update(kwargs)
            return '{"total": 1}'

        monkeypatch.setattr(OllamaClient, "generate", fake_generate)
        model_reports(monkeypatch, caps=caps)
        svc = make_service(overrides)
        monkeypatch.setattr(svc, "_get_categories", AsyncMock(return_value=[]))
        return svc, captured

    async def test_receipt_sends_the_schema_while_thinking(self, monkeypatch):
        svc, captured = self.capture_service({"ai_thinking": "on"}, monkeypatch)
        await svc.extract_receipt(uuid.uuid4(), "aW1n", date(2026, 8, 16))
        assert captured["think"] is True
        assert captured["format"] == RECEIPT_REPLY_SCHEMA

    async def test_receipt_sends_the_schema_with_thinking_off(self, monkeypatch):
        svc, captured = self.capture_service(
            {"ai_thinking": "off"}, monkeypatch, caps=["vision", "thinking"]
        )
        await svc.extract_receipt(uuid.uuid4(), "aW1n", date(2026, 8, 16))
        assert captured["think"] is False
        assert captured["format"] == RECEIPT_REPLY_SCHEMA

    async def test_nl_parse_sends_its_schema(self, monkeypatch):
        svc, captured = self.capture_service({"ai_thinking": "on"}, monkeypatch)
        await svc.parse_nl_transaction(uuid.uuid4(), "coffee 5.50", date(2026, 8, 16))
        assert captured["think"] is True
        assert captured["format"] == NL_REPLY_SCHEMA


class TestTheCallIsRecorded:
    """Every model call lands on the gateway's record, whatever happens to it.

    This used to be two fields on AIService that only the receipt and NL paths
    set, so the three other features recorded nothing at all. The gateway
    records all of them, and `debug_view` is the one shape the job row and the
    call log both render.
    """

    def capture_service(self, monkeypatch, *, generate=None) -> AIService:
        async def default_generate(self, prompt, system=None, **kwargs):
            self.last_meta = {"prompt_eval_count": 11, "eval_count": 7}
            return '{"total": 1}'

        monkeypatch.setattr(OllamaClient, "generate", generate or default_generate)
        model_reports(monkeypatch)
        svc = make_service({"ai_thinking": "on", "ollama_model": "gemma4:test"})
        monkeypatch.setattr(
            svc,
            "_get_categories",
            AsyncMock(return_value=[{"id": 1, "name": "Groceries", "group": "Everyday"}]),
        )
        return svc

    async def test_extract_records_the_call(self, monkeypatch):
        svc = self.capture_service(monkeypatch)
        await svc.extract_receipt(uuid.uuid4(), "aW1n", date(2026, 8, 16))
        result = svc.gateway.last_result
        assert result is not None
        assert result.context.feature == "receipt_extract"
        assert result.model == "gemma4:test"
        assert result.thinking_enabled is True
        assert result.status == "ok"
        assert "Groceries (Everyday)" in result.messages[0]["content"]
        assert "2026-08-16" in result.messages[0]["content"]

    async def test_token_counts_are_kept(self, monkeypatch):
        """Ollama reports these on every call and the client used to drop them."""
        svc = self.capture_service(monkeypatch)
        await svc.extract_receipt(uuid.uuid4(), "aW1n", date(2026, 8, 16))
        result = svc.gateway.last_result
        assert result is not None
        assert result.prompt_tokens == 11
        assert result.completion_tokens == 7

    async def test_recorded_even_when_the_call_fails(self, monkeypatch):
        async def failing_generate(self, prompt, system=None, **kwargs):
            raise ConnectionError("refused")

        svc = self.capture_service(monkeypatch, generate=failing_generate)
        with pytest.raises(ConnectionError):
            await svc.extract_receipt(uuid.uuid4(), "aW1n", date(2026, 8, 16))
        result = svc.gateway.last_result
        assert result is not None
        assert result.status == "error"
        assert "ConnectionError" in (result.error or "")
        assert "Groceries (Everyday)" in result.messages[0]["content"]

    async def test_a_cancelled_call_is_recorded_as_cancelled(self, monkeypatch):
        """Closing the chat panel mid-answer is normal, not an error — and
        "what did it do before I stopped it" is the question the log answers."""

        async def cancelled_generate(self, prompt, system=None, **kwargs):
            raise asyncio.CancelledError()

        svc = self.capture_service(monkeypatch, generate=cancelled_generate)
        with pytest.raises(asyncio.CancelledError):
            await svc.extract_receipt(uuid.uuid4(), "aW1n", date(2026, 8, 16))
        result = svc.gateway.last_result
        assert result is not None
        assert result.status == "cancelled"

    async def test_nl_parse_records_the_call(self, monkeypatch):
        svc = self.capture_service(monkeypatch)
        await svc.parse_nl_transaction(uuid.uuid4(), "coffee 5.50", date(2026, 8, 16))
        result = svc.gateway.last_result
        assert result is not None
        assert result.context.feature == "nl_parse"
        assert "coffee 5.50" in result.messages[0]["content"]

    async def test_features_that_recorded_nothing_now_do(self, monkeypatch):
        """suggest_category swallows its own failures and returned a fallback,
        so a wrong answer left no evidence at all. It does now."""
        svc = self.capture_service(monkeypatch)
        await svc.suggest_category(uuid.uuid4(), "Harborstone Market", -42.0)
        result = svc.gateway.last_result
        assert result is not None
        assert result.context.feature == "suggest_category"
        assert "Harborstone Market" in result.messages[0]["content"]

    async def test_debug_view_is_what_the_job_row_shows(self, monkeypatch):
        svc = self.capture_service(monkeypatch)
        await svc.parse_nl_transaction(uuid.uuid4(), "coffee 5.50", date(2026, 8, 16))
        view = debug_view(svc.gateway.last_result)
        assert view["request"]["model"] == "gemma4:test"
        assert "coffee 5.50" in view["request"]["prompt"]
        assert view["raw_response"] == '{"total": 1}'

    def test_debug_view_of_nothing_is_empty(self):
        assert debug_view(None) == {}

    async def test_a_cut_off_reply_says_so(self, monkeypatch):
        """Without the stop reason a reply the window cut short read exactly
        like a malformed one."""

        async def cut_off(self, prompt, system=None, **kwargs):
            self.last_meta = {"done_reason": "length"}
            return '```json\n{"total": 39.53, "line_items": [{"description": "Soap", "amount": 1}'

        svc = self.capture_service(monkeypatch, generate=cut_off)
        with pytest.raises(ReplyNotJSON, match="cut off"):
            await svc.extract_receipt(uuid.uuid4(), "aW1n", date(2026, 9, 25))
        assert debug_view(svc.gateway.last_result)["done_reason"] == "length"

    async def test_an_answer_left_in_the_thinking_is_read(self, monkeypatch):
        async def thought_it(self, prompt, system=None, **kwargs):
            self.last_meta = {"thinking": 'Total 39.53.\n{"total": 39.53}', "done_reason": "stop"}
            return ""

        svc = self.capture_service(monkeypatch, generate=thought_it)
        assert await svc.extract_receipt(uuid.uuid4(), "aW1n", date(2026, 9, 25)) == {
            "total": 39.53
        }


class TestReceiptModelResolution:
    """The chain the worker uses for receipt scans: vision override ->
    main model -> hardcoded default. The status endpoint reports the result
    so the settings UI can say "receipts are scanned by X" without
    re-implementing this."""

    async def test_override_wins_and_is_flagged(self):
        svc = make_service({"ollama_vision_model": "tiny-ocr"})
        assert await svc._resolve_vision_model() == ("tiny-ocr", True)

    async def test_empty_override_falls_back_to_main_model(self):
        svc = make_service({"ollama_model": "granite4:latest", "ollama_vision_model": ""})
        assert await svc._resolve_vision_model() == ("granite4:latest", False)

    async def test_both_unset_falls_back_to_default(self):
        svc = make_service({"ollama_model": "", "ollama_vision_model": ""})
        assert await svc._resolve_vision_model() == ("llama3.2", False)

    async def test_status_reports_the_resolved_receipt_model(self):
        # ai_enabled defaults to "false", so check_availability takes the
        # early return — no network involved.
        svc = make_service({"ollama_model": "granite4:latest", "ollama_vision_model": ""})
        status = await svc.check_availability()
        assert status["receipt_model"] == "granite4:latest"
        assert status["vision_model"] is None

    async def test_status_receipt_model_prefers_the_override(self):
        svc = make_service({"ollama_model": "granite4:latest", "ollama_vision_model": "tiny-ocr"})
        status = await svc.check_availability()
        assert status["receipt_model"] == "tiny-ocr"
        assert status["vision_model"] == "tiny-ocr"


HOST = "http://ollama.test:11434"

# What /api/show reports, keyed by model — the authoritative answer. Real
# capture: /api/tags lists gemma4:latest WITHOUT "vision" while /api/show for
# the very same tag reports it.
SHOW_CAPS = {
    "gemma4:latest": ["completion", "vision", "tools", "thinking"],
    "phi4-mini:latest": ["completion", "tools"],
}


def show_route(request: httpx.Request) -> httpx.Response:
    model = json.loads(request.content)["model"]
    return httpx.Response(200, json={"capabilities": SHOW_CAPS[model]})


def tags_response(models: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"models": models})


class TestModelCapabilities:
    """/api/tags under-reports capabilities; /api/show decides.

    The settings page believed the tags list and told the user their working
    gemma4 receipt model "does not support vision" — while the worker, which
    gates on /api/show, was scanning receipts with it just fine.
    """

    @respx.mock
    async def test_show_capabilities_win_over_the_tags_list(self):
        respx.get(f"{HOST}/api/tags").mock(
            return_value=tags_response(
                [
                    # exactly what Ollama returns for these tags
                    {
                        "name": "gemma4:latest",
                        "size": 17,
                        "capabilities": ["completion", "tools", "thinking"],
                    },
                    {
                        "name": "phi4-mini:latest",
                        "size": 2,
                        "capabilities": ["completion", "tools"],
                    },
                ]
            )
        )
        respx.post(f"{HOST}/api/show").mock(side_effect=show_route)

        models = await make_service({"ollama_host": HOST}).list_models()

        assert models[0]["name"] == "gemma4:latest"
        assert "vision" in models[0]["capabilities"]
        # A model that genuinely lacks vision still reads as lacking it.
        assert "vision" not in models[1]["capabilities"]
        assert models[0]["size"] == 17

    @respx.mock
    async def test_tags_capabilities_kept_when_show_reports_none(self):
        # Older Ollama omits capabilities from /api/show; blanking the list
        # would throw away the only signal available.
        respx.get(f"{HOST}/api/tags").mock(
            return_value=tags_response(
                [{"name": "gemma4:latest", "size": 17, "capabilities": ["completion", "vision"]}]
            )
        )
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"modelfile": "..."})
        )

        models = await make_service({"ollama_host": HOST}).list_models()
        assert models[0]["capabilities"] == ["completion", "vision"]

    @respx.mock
    async def test_status_reports_vision_from_show(self):
        respx.get(f"{HOST}/").mock(return_value=httpx.Response(200))
        respx.post(f"{HOST}/api/show").mock(side_effect=show_route)

        svc = make_service(
            {
                "ai_enabled": "true",
                "ollama_host": HOST,
                "ollama_model": "gemma4:latest",
                "ollama_vision_model": "",
            }
        )
        status = await svc.check_availability()
        assert status["receipt_model"] == "gemma4:latest"
        assert status["receipt_model_vision"] is True

    @respx.mock
    async def test_status_reports_a_genuine_lack_of_vision(self):
        respx.get(f"{HOST}/").mock(return_value=httpx.Response(200))
        respx.post(f"{HOST}/api/show").mock(side_effect=show_route)

        svc = make_service(
            {
                "ai_enabled": "true",
                "ollama_host": HOST,
                "ollama_model": "phi4-mini:latest",
                "ollama_vision_model": "",
            }
        )
        assert (await svc.check_availability())["receipt_model_vision"] is False

    @respx.mock
    async def test_status_vision_unknown_when_ollama_is_unreachable(self):
        # Down is not misconfigured: the UI must not turn this into
        # "your model does not support vision".
        respx.get(f"{HOST}/").mock(side_effect=httpx.ConnectError("down"))

        svc = make_service(
            {"ai_enabled": "true", "ollama_host": HOST, "ollama_model": "gemma4:latest"}
        )
        status = await svc.check_availability()
        assert status["available"] is False
        assert status["receipt_model_vision"] is None

    async def test_status_vision_unknown_when_ai_is_disabled(self):
        svc = make_service({"ai_enabled": "false", "ollama_model": "gemma4:latest"})
        assert (await svc.check_availability())["receipt_model_vision"] is None


class TestTheAssistantWindow:
    """The chat asks for a context window sized from the model, and the
    status endpoint reports the same numbers the chat route will use."""

    def client_reporting(self, context_length, caps=("completion", "tools")):
        client = OllamaClient("http://x:11434", "m")
        client.capabilities = AsyncMock(return_value=list(caps))  # type: ignore[method-assign]
        client.context_length = AsyncMock(return_value=context_length)  # type: ignore[method-assign]
        return client

    async def test_auto_sizes_from_the_model(self):
        svc = make_service({"ai_chat_num_ctx": "auto"})
        num_ctx, model_max = await svc.context_window(self.client_reporting(131_072))
        assert model_max == 131_072
        assert num_ctx == 32_768

    async def test_an_explicit_window_is_honoured(self):
        svc = make_service({"ai_chat_num_ctx": "65536"})
        num_ctx, _ = await svc.context_window(self.client_reporting(131_072))
        assert num_ctx == 65_536

    async def test_the_chat_model_falls_back_to_the_main_one(self):
        svc = make_service({"ollama_model": "gemma4:31b", "ollama_chat_model": ""})
        assert await svc._resolve_chat_model() == ("gemma4:31b", False)
        svc = make_service({"ollama_model": "gemma4:31b", "ollama_chat_model": "qwen3:8b"})
        assert await svc._resolve_chat_model() == ("qwen3:8b", True)

    async def test_context_length_is_read_from_model_info_by_suffix(self):
        client = OllamaClient("http://x:11434", "gemma4:latest")
        client.show = AsyncMock(  # type: ignore[method-assign]
            return_value={"model_info": {"gemma4.context_length": 131072, "gemma4.x": 1}}
        )
        assert await client.context_length() == 131072
        client.show = AsyncMock(return_value={})  # type: ignore[method-assign]
        assert await client.context_length() is None
