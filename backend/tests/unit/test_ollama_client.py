import json

import httpx
import pytest
import respx

from igab.integrations.ollama.client import OllamaClient

HOST = "http://ollama.test:11434"


@pytest.fixture
def client() -> OllamaClient:
    return OllamaClient(HOST, "gemma4")


class TestGeneratePayload:
    @respx.mock
    async def test_minimal_payload_omits_optional_fields(self, client):
        route = respx.post(f"{HOST}/api/generate").mock(
            return_value=httpx.Response(200, json={"response": "ok"})
        )
        result = await client.generate("hello")
        assert result == "ok"
        payload = json.loads(route.calls[0].request.content)
        assert payload == {"model": "gemma4", "prompt": "hello", "stream": False}
        for absent in ("system", "images", "format", "think", "options"):
            assert absent not in payload

    @respx.mock
    async def test_full_payload_shape(self, client):
        route = respx.post(f"{HOST}/api/generate").mock(
            return_value=httpx.Response(200, json={"response": "{}"})
        )
        await client.generate(
            "prompt",
            "system prompt",
            images=["aGVsbG8="],
            format="json",
            think=True,
            options={"temperature": 0, "num_ctx": 8192},
        )
        payload = json.loads(route.calls[0].request.content)
        assert payload["system"] == "system prompt"
        assert payload["images"] == ["aGVsbG8="]
        assert payload["format"] == "json"
        assert payload["think"] is True
        assert payload["options"] == {"temperature": 0, "num_ctx": 8192}

    @respx.mock
    async def test_think_false_is_sent_but_none_is_omitted(self, client):
        route = respx.post(f"{HOST}/api/generate").mock(
            return_value=httpx.Response(200, json={"response": "ok"})
        )
        await client.generate("p", think=False)
        assert json.loads(route.calls[0].request.content)["think"] is False
        await client.generate("p", think=None)
        assert "think" not in json.loads(route.calls[1].request.content)

    @respx.mock
    async def test_http_error_raises(self, client):
        respx.post(f"{HOST}/api/generate").mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await client.generate("p")


class TestShow:
    @respx.mock
    async def test_capabilities_parsed(self, client):
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(
                200, json={"capabilities": ["completion", "vision", "thinking"]}
            )
        )
        assert await client.capabilities() == ["completion", "vision", "thinking"]

    @respx.mock
    async def test_missing_capabilities_returns_none(self, client):
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"modelfile": "..."})
        )
        assert await client.capabilities() is None

    @respx.mock
    async def test_server_error_returns_none(self, client):
        respx.post(f"{HOST}/api/show").mock(return_value=httpx.Response(500))
        assert await client.capabilities() is None

    @respx.mock
    async def test_show_targets_requested_model(self, client):
        route = respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": []})
        )
        await client.show("other-model")
        assert json.loads(route.calls[0].request.content)["model"] == "other-model"


class TestOllamaErrors:
    @respx.mock
    async def test_the_reason_ollama_gave_is_kept(self, client):
        """gemma4:12b at temperature 0 looped until Ollama aborted it. The job
        said "Server error '500 Internal Server Error'" and nothing more."""
        respx.post(f"{HOST}/api/generate").mock(
            return_value=httpx.Response(
                500, json={"error": "prediction aborted, token repeat limit reached"}
            )
        )
        with pytest.raises(httpx.HTTPStatusError, match="token repeat limit reached") as exc:
            await client.generate("p")
        assert exc.value.response.status_code == 500

    @respx.mock
    async def test_a_body_without_a_reason_still_raises(self, client):
        respx.post(f"{HOST}/api/generate").mock(
            return_value=httpx.Response(502, text="bad gateway")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.generate("p")

    @respx.mock
    async def test_chat_keeps_the_reason_too(self, client):
        respx.post(f"{HOST}/api/chat").mock(
            return_value=httpx.Response(400, json={"error": "model does not support tools"})
        )
        with pytest.raises(httpx.HTTPStatusError, match="does not support tools"):
            await client.chat([{"role": "user", "content": "hi"}])
