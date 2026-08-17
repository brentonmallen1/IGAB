"""AIService.suggest_regex: the model's output is untrusted — anything that
isn't a valid regex must come back as None so the frontend falls back to its
structural heuristic."""

from unittest.mock import AsyncMock, MagicMock

from igab.services.ai_service import AIService


def make_service(response: str | Exception) -> AIService:
    settings = MagicMock()
    settings.get = AsyncMock(return_value=None)  # every setting falls back to its default
    svc = AIService(MagicMock(), settings)
    client = MagicMock()
    if isinstance(response, Exception):
        client.generate = AsyncMock(side_effect=response)
    else:
        client.generate = AsyncMock(return_value=response)
    svc._client = AsyncMock(return_value=client)  # type: ignore[method-assign]
    return svc


class TestSuggestRegex:
    async def test_returns_pattern_from_model_json(self):
        svc = make_service('{"pattern": "^ACH DEPOSIT PAYROLL "}')
        assert await svc.suggest_regex(["ACH DEPOSIT PAYROLL 88", "ACH DEPOSIT PAYROLL 99"]) == (
            "^ACH DEPOSIT PAYROLL "
        )

    async def test_invalid_regex_from_model_returns_none(self):
        svc = make_service('{"pattern": "([bad"}')
        assert await svc.suggest_regex(["A", "B"]) is None

    async def test_non_json_output_returns_none(self):
        svc = make_service("sure! here is a regex: ^A.*")
        assert await svc.suggest_regex(["A", "B"]) is None

    async def test_missing_or_blank_pattern_returns_none(self):
        assert await make_service('{"regex": "^A"}').suggest_regex(["A"]) is None
        assert await make_service('{"pattern": "  "}').suggest_regex(["A"]) is None
        assert await make_service('{"pattern": 42}').suggest_regex(["A"]) is None

    async def test_empty_names_short_circuits_without_calling_model(self):
        svc = make_service('{"pattern": "^A"}')
        assert await svc.suggest_regex([]) is None
        assert await svc.suggest_regex(["", "   "]) is None
        svc._client.assert_not_called()  # type: ignore[union-attr]

    async def test_model_error_returns_none(self):
        svc = make_service(RuntimeError("ollama down"))
        assert await svc.suggest_regex(["A", "B"]) is None
