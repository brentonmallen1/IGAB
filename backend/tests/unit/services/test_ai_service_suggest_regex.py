"""AIService.suggest_regex: the model's output is untrusted. The service owns
the shapes it accepts — the current `patterns` list and the older single
`pattern` — and hands them to `rank_match_patterns` (tested in
test_payee_names.py). Nothing usable comes back as an empty list so the
frontend falls back to its structural heuristic."""

from unittest.mock import AsyncMock, MagicMock

from igab.services.ai_service import AIService

NAMES = ["ACH DEPOSIT PAYROLL 88", "ACH DEPOSIT PAYROLL 99"]


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
    async def test_returns_ranked_candidates(self):
        svc = make_service('{"patterns": ["PAYROLL 88", "^ACH DEPOSIT PAYROLL ", "([bad"]}')
        assert await svc.suggest_regex(NAMES) == ["^ACH DEPOSIT PAYROLL ", "PAYROLL 88"]

    async def test_an_override_of_the_old_prompt_still_answers(self):
        # A user's saved copy of the single-pattern prompt returns {"pattern"}.
        svc = make_service('{"pattern": "^ACH DEPOSIT PAYROLL "}')
        assert await svc.suggest_regex(NAMES) == ["^ACH DEPOSIT PAYROLL "]

    async def test_non_json_output_returns_nothing(self):
        svc = make_service("sure! here is a regex: ^A.*")
        assert await svc.suggest_regex(NAMES) == []

    async def test_missing_or_misshapen_patterns_return_nothing(self):
        assert await make_service('{"regex": "^A"}').suggest_regex(["A"]) == []
        assert await make_service('{"patterns": "^A"}').suggest_regex(["A"]) == []

    async def test_empty_names_short_circuit_without_calling_model(self):
        svc = make_service('{"patterns": ["^A"]}')
        assert await svc.suggest_regex([]) == []
        assert await svc.suggest_regex(["", "   "]) == []
        svc._client.assert_not_called()  # type: ignore[union-attr]

    async def test_model_error_returns_nothing(self):
        svc = make_service(RuntimeError("ollama down"))
        assert await svc.suggest_regex(NAMES) == []
