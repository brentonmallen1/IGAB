"""Capability-driven behavior: options merge precedence and think gating.

These are the model-agnostic mechanisms that replace per-model code paths —
any model's quirks flow through settings, not through the codebase.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import igab.services.ai_service as ai_service_module
from igab.integrations.ollama.client import OllamaClient
from igab.services.ai_service import AIService, _json_from_response
from igab.services.settings_service import DEFAULTS


@pytest.fixture(autouse=True)
def clear_caps_cache():
    ai_service_module._caps_cache.clear()
    yield
    ai_service_module._caps_cache.clear()


def make_service(overrides: dict[str, str] | None = None) -> AIService:
    values = dict(DEFAULTS)
    values.update(overrides or {})
    settings = MagicMock()
    settings.get = AsyncMock(side_effect=lambda key: values.get(key))
    return AIService(session=MagicMock(), settings=settings)


class TestOptionsMerge:
    async def test_task_defaults_alone(self):
        svc = make_service()
        opts = await svc._merged_options(vision=False, task_defaults={"temperature": 0})
        assert opts == {"temperature": 0}

    async def test_global_options_override_task_defaults(self):
        svc = make_service({"ollama_options": '{"temperature": 0.4, "num_ctx": 8192}'})
        opts = await svc._merged_options(vision=False, task_defaults={"temperature": 0})
        assert opts == {"temperature": 0.4, "num_ctx": 8192}

    async def test_vision_options_win_for_vision_tasks_only(self):
        svc = make_service(
            {
                "ollama_options": '{"num_ctx": 8192}',
                "ollama_vision_options": '{"num_ctx": 4096, "image_tokens": 512}',
            }
        )
        vision = await svc._merged_options(vision=True, task_defaults={})
        assert vision == {"num_ctx": 4096, "image_tokens": 512}
        text = await svc._merged_options(vision=False, task_defaults={})
        assert text == {"num_ctx": 8192}

    async def test_invalid_json_never_breaks_a_call(self):
        svc = make_service({"ollama_options": "{not json"})
        opts = await svc._merged_options(vision=False, task_defaults={"temperature": 0})
        assert opts == {"temperature": 0}

    async def test_non_object_json_ignored(self):
        svc = make_service({"ollama_options": '["a", "b"]'})
        opts = await svc._merged_options(vision=False, task_defaults={})
        assert opts == {}


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

    async def test_forced_off_omits_field(self):
        svc = make_service({"ai_thinking": "off"})
        assert await svc._resolve_think(self.client_with_caps(["thinking"])) is None


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

    async def test_gate_never_requests_thinking(self, monkeypatch):
        captured: dict = {}

        async def fake_generate(self, prompt, system=None, **kwargs):
            captured.update(kwargs)
            return '{"is_receipt": true}'

        monkeypatch.setattr(OllamaClient, "generate", fake_generate)
        svc = make_service({"ai_thinking": "on"})
        await svc.is_receipt_image("aW1n")
        assert "think" not in captured or captured.get("think") is None
        assert captured["options"]["num_predict"] == 64


class TestJsonFromResponse:
    def test_plain_json(self):
        assert _json_from_response('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert _json_from_response('```json\n{"a": 1}\n```') == {"a": 1}

    def test_fenced_without_language(self):
        assert _json_from_response('```\n{"a": 1}\n```') == {"a": 1}

    def test_non_object_raises(self):
        with pytest.raises(ValueError):
            _json_from_response("[1, 2]")

    def test_junk_raises(self):
        import json

        with pytest.raises(json.JSONDecodeError):
            _json_from_response("the total is $42")
