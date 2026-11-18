"""Every way a scan or description fails explains itself in layers: a headline
a person reads first, the next step, and the evidence for whoever diagnoses
it — never an exception name in the first two."""

import re

import httpx
import pytest

from igab.ai.failure_text import (
    AI_SETTINGS,
    THINKING_SETTING,
    TIMEOUT_SETTING,
    explain_failure,
)
from igab.ai.reply_json import ReplyCutShort, ReplyNotJSON
from igab.domain.exceptions import InvariantViolation
from igab.tasks.ai_worker import NonRetryableJobError

REQUEST = httpx.Request("POST", "http://ollama.test/api/generate")


def status(code: int, detail: str) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        f"Ollama returned {code}: {detail}",
        request=REQUEST,
        response=httpx.Response(code, request=REQUEST),
    )


FAILURES = [
    ReplyCutShort("cut off", "length"),
    ReplyCutShort("cut off", "deadline"),
    ReplyCutShort("cut off", "repetition"),
    ReplyNotJSON("The model's reply held no JSON object: 'I see a receipt'"),
    InvariantViolation("AI extraction returned a zero amount"),
    httpx.ConnectError("All connection attempts failed"),
    httpx.ConnectTimeout(""),
    httpx.ReadTimeout(""),
    httpx.RemoteProtocolError("peer closed connection"),
    status(404, "model 'gemma4:31b' not found"),
    status(500, "out of memory"),
    NonRetryableJobError("The image doesn't appear to be a receipt.", next_step="Fill it in."),
    KeyError("response"),
]

#: What a person must never read in the headline or the next step.
JARGON = re.compile(
    r"JSON|ReplyCutShort|ReplyNotJSON|InvariantViolation|Timeout\b|Error\b|done_reason"
)

CALL = {
    "request": {"model": "gemma4:12b"},
    "thinking_enabled": False,
    "completion_tokens": 1912,
    "duration_ms": 41_200,
}


@pytest.mark.parametrize("exc", FAILURES, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("kind", ["receipt", "nl_parse"])
def test_every_failure_has_a_plain_headline_and_next_step(exc, kind):
    failure = explain_failure(exc, kind)
    for text in (failure.headline, failure.next_step):
        assert text and text[0].isupper() and text.rstrip().endswith("."), text
        assert not JARGON.search(text), text
    assert failure.sentence() == f"{failure.headline} {failure.next_step}"


def test_the_headline_is_short():
    """It sits on one line of the Scans row."""
    for exc in FAILURES:
        assert len(explain_failure(exc, "receipt").headline) <= 64


def test_a_description_is_never_told_to_read_the_image():
    for exc in FAILURES:
        assert "image" not in explain_failure(exc, "nl_parse").next_step


@pytest.mark.parametrize(
    ("reason", "setting"),
    [("length", THINKING_SETTING), ("deadline", TIMEOUT_SETTING), ("repetition", None)],
)
def test_a_cut_short_read_names_the_setting_that_helps(reason, setting):
    assert explain_failure(ReplyCutShort("x", reason), "receipt").settings == setting


def test_the_technical_line_carries_the_cause_and_the_call():
    failure = explain_failure(ReplyCutShort("x", "repetition"), "receipt", CALL)
    assert failure.technical == (
        "Stopped: one item repeated 8 times in a row\n"
        "gemma4:12b · thinking off · 1,912 tokens · 41 s"
    )


def test_ollama_problems_point_at_settings_only_when_settings_can_fix_them():
    assert explain_failure(httpx.ConnectError("x"), "receipt").settings == AI_SETTINGS
    assert explain_failure(FAILURES[9], "receipt").settings == AI_SETTINGS
    assert explain_failure(FAILURES[10], "receipt").settings is None
    assert "model 'gemma4:31b' not found" in (
        explain_failure(FAILURES[9], "receipt").technical or ""
    )


def test_a_worker_failure_keeps_its_own_words():
    exc = NonRetryableJobError(
        "Your main model 'x' does not support vision.",
        next_step="Pick a vision-capable model.",
        settings=AI_SETTINGS,
    )
    failure = explain_failure(exc, "receipt")
    assert (failure.headline, failure.next_step, failure.settings) == (
        "Your main model 'x' does not support vision.",
        "Pick a vision-capable model.",
        AI_SETTINGS,
    )


def test_the_catch_all_names_what_it_was_in_the_technical_line():
    failure = explain_failure(KeyError("response"), "receipt")
    assert "KeyError" in (failure.technical or "")
    assert "KeyError" not in failure.headline
