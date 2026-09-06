"""AIService.suggest_regex: the model proposes, the service decides.

"The AI regex is flaky" is what it looks like when a local model's raw output
is the answer. It is not, any more: every candidate is checked against the
names by the same matcher the importer uses, ranked down if it also swallows
the budget's other payees, and backed by patterns derived from the names
themselves. A model that returns prose, times out, or is not installed costs
the user a *better* suggestion, never their answer.

The ranking itself lives in `rank_match_patterns` (test_payee_names.py). What
is tested here is what the service feeds it and what it promises back.
"""

import re
import uuid
from unittest.mock import AsyncMock, MagicMock

from igab.services.ai_service import AIService

NAMES = ["ACH DEPOSIT PAYROLL 88", "ACH DEPOSIT PAYROLL 99"]
BUDGET = uuid.uuid4()

#: What the derived floor produces for NAMES: the shared stem, then the
#: alternation that matches all of them by construction.
DERIVED_STEM = "^ACH\\ DEPOSIT\\ PAYROLL\\ "
DERIVED_ALL = "^(?:ACH\\ DEPOSIT\\ PAYROLL\\ 88|ACH\\ DEPOSIT\\ PAYROLL\\ 99)"
DERIVED = [DERIVED_STEM, DERIVED_ALL]


def make_service(response: str | Exception, other_payees: list[str] | None = None) -> AIService:
    settings = MagicMock()
    settings.get = AsyncMock(return_value=None)  # every setting falls back to its default
    session = MagicMock()
    session.execute = AsyncMock(return_value=[(name,) for name in (other_payees or [])])
    svc = AIService(session, settings)
    client = MagicMock()
    if isinstance(response, Exception):
        client.generate = AsyncMock(side_effect=response)
    else:
        client.generate = AsyncMock(return_value=response)
    svc._client = AsyncMock(return_value=client)  # type: ignore[method-assign]
    return svc


class TestWhatTheModelSaid:
    async def test_a_good_suggestion_leads(self):
        svc = make_service('{"patterns": ["PAYROLL 88", "^ACH DEPOSIT PAYROLL ", "([bad"]}')
        patterns = await svc.suggest_regex(BUDGET, NAMES)
        # Covers both names; "PAYROLL 88" covers one; "([bad" does not compile.
        assert patterns[0] == "^ACH DEPOSIT PAYROLL "
        assert "([bad" not in patterns

    async def test_an_override_of_the_old_prompt_still_answers(self):
        # A user's saved copy of the single-pattern prompt returns {"pattern"}.
        svc = make_service('{"pattern": "^ACH DEPOSIT PAYROLL "}')
        assert (await svc.suggest_regex(BUDGET, NAMES))[0] == "^ACH DEPOSIT PAYROLL "

    async def test_a_pattern_that_swallows_other_payees_loses_to_one_that_does_not(self):
        """ "Too general" stops being a matter of taste once there is something
        to check it against: `^A` covers both names and half the register."""
        svc = make_service(
            '{"patterns": ["^A", "^ACH DEPOSIT PAYROLL "]}',
            other_payees=["Amazon", "Aldi", "Apple"],
        )
        patterns = await svc.suggest_regex(BUDGET, NAMES)
        assert patterns[0] == "^ACH DEPOSIT PAYROLL "
        # And the property behind the ordering: nothing offered drags in a
        # payee the user did not select.
        assert not any(re.search(p, "Amazon") for p in patterns)

    async def test_the_names_being_merged_are_not_counted_against_a_pattern(self):
        """They are the ones it is SUPPOSED to match."""
        svc = make_service('{"patterns": ["^ACH DEPOSIT PAYROLL "]}', other_payees=NAMES)
        assert (await svc.suggest_regex(BUDGET, NAMES))[0] == "^ACH DEPOSIT PAYROLL "


class TestTheFloorUnderIt:
    """Whatever the model does, something that works comes back."""

    async def test_prose_instead_of_json_still_answers(self):
        svc = make_service("sure! here is a regex: ^A.*")
        assert await svc.suggest_regex(BUDGET, NAMES) == DERIVED

    async def test_a_model_that_is_down_still_answers(self):
        svc = make_service(RuntimeError("ollama down"))
        assert await svc.suggest_regex(BUDGET, NAMES) == DERIVED

    async def test_misshapen_output_still_answers(self):
        assert await make_service('{"regex": "^A"}').suggest_regex(BUDGET, NAMES) == DERIVED
        assert await make_service('{"patterns": "^A"}').suggest_regex(BUDGET, NAMES) == DERIVED

    async def test_every_answer_matches_every_name(self):
        """The whole request is "one pattern for these". The top candidate
        has to actually be that, whatever the model contributed."""
        svc = make_service('{"patterns": ["PAYROLL 88"]}')
        top = (await svc.suggest_regex(BUDGET, NAMES))[0]
        assert all(re.search(top, name) for name in NAMES)

    async def test_names_with_regex_metacharacters_do_not_break_the_fallback(self):
        """`AMZN Mktp US*1A2B3` is a real shape of bank string; an unescaped
        derived pattern would not compile."""
        names = ["AMZN Mktp US*1A2B3", "AMZN Mktp US*9Z8Y7"]
        svc = make_service(RuntimeError("no model"))
        patterns = await svc.suggest_regex(BUDGET, names)
        assert patterns
        for pattern in patterns:
            assert all(re.search(pattern, name) for name in names)


class TestBoundaries:
    async def test_empty_names_short_circuit_without_calling_model(self):
        svc = make_service('{"patterns": ["^A"]}')
        assert await svc.suggest_regex(BUDGET, []) == []
        assert await svc.suggest_regex(BUDGET, ["", "   "]) == []
        svc._client.assert_not_called()  # type: ignore[union-attr]
