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
    ReplyCutShort("cut off", "repeat_limit"),
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
    [
        ("length", THINKING_SETTING),
        ("deadline", TIMEOUT_SETTING),
        ("repetition", None),
        ("repeat_limit", None),
    ],
)
def test_a_cut_short_read_names_the_setting_that_helps(reason, setting):
    assert explain_failure(ReplyCutShort("x", reason), "receipt").settings == setting


def test_the_technical_line_carries_the_cause_and_the_call():
    failure = explain_failure(ReplyCutShort("x", "repetition"), "receipt", CALL)
    assert failure.technical == (
        "Stopped: one item repeated 8 times in a row\n"
        "gemma4:12b · thinking off · 1,912 tokens · 41 s"
    )


def test_a_loop_ollama_stopped_says_ollama_stopped_it():
    failure = explain_failure(ReplyCutShort("x", "repeat_limit"), "receipt", CALL)
    assert failure.headline == "The model got stuck repeating one line and was stopped."
    assert (failure.technical or "").startswith("Stopped by Ollama: token repeat limit reached")


def test_ollama_problems_point_at_settings_only_when_settings_can_fix_them():
    assert explain_failure(httpx.ConnectError("x"), "receipt").settings == AI_SETTINGS
    assert explain_failure(FAILURES[10], "receipt").settings == AI_SETTINGS
    assert explain_failure(FAILURES[11], "receipt").settings is None
    assert "model 'gemma4:31b' not found" in (
        explain_failure(FAILURES[10], "receipt").technical or ""
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


def test_after_the_thinking_fallback_turning_thinking_off_is_not_the_advice():
    read = {"thinking_setting": "auto", "thinking": False, "thinking_fallback": True}
    call = {**CALL, "thinking_enabled": False}
    failure = explain_failure(ReplyCutShort("x", "length"), "receipt", call, read)
    assert failure.settings is None
    assert "with thinking on and again with it off" in failure.next_step
    assert (failure.technical or "").startswith("Thinking ran out of room; re-read")


def test_a_read_that_never_thought_is_not_told_to_stop_thinking():
    call = {**CALL, "thinking_enabled": False}
    failure = explain_failure(ReplyCutShort("x", "length"), "receipt", call)
    assert failure.settings is None
    assert "thinking" not in failure.next_step


RETRYABLE = [
    ReplyNotJSON("no object"),
    InvariantViolation("zero amount"),
    httpx.ConnectError("refused"),
    httpx.ReadTimeout(""),
    status(500, "out of memory"),
    httpx.RemoteProtocolError("peer closed"),
]


@pytest.mark.parametrize("exc", RETRYABLE, ids=lambda e: type(e).__name__)
def test_a_retry_is_promised_only_when_one_is_coming(exc):
    assert "try again in a moment" in explain_failure(exc, "receipt", will_retry=True).next_step
    final = explain_failure(exc, "receipt", will_retry=False)
    assert "try again in a moment" not in final.next_step
    assert not JARGON.search(final.next_step)


def test_a_4xx_that_is_never_retried_does_not_promise_one():
    assert "in a moment" not in explain_failure(status(400, "bad request"), "receipt").next_step


@pytest.mark.parametrize("reason", ["length", "deadline", "repetition", "repeat_limit"])
def test_a_description_cut_short_never_talks_about_a_receipt(reason):
    failure = explain_failure(
        ReplyCutShort("x", reason), "nl_parse", {**CALL, "thinking_enabled": True}
    )
    assert "receipt" not in failure.headline + failure.next_step
    assert "total" not in failure.headline
