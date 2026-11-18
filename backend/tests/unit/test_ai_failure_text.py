"""Every way a scan or description fails reads as a sentence for a person:
what happened, and what to do — never an exception name."""

import re

import httpx
import pytest

from igab.ai.failure_text import failure_text
from igab.ai.reply_json import ReplyCutShort, ReplyNotJSON
from igab.domain.exceptions import InvariantViolation
from igab.tasks.ai_worker import NonRetryableJobError

REQUEST = httpx.Request("POST", "http://ollama.test/api/generate")

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
    httpx.HTTPStatusError(
        "Ollama returned 404: model 'gemma4:31b' not found",
        request=REQUEST,
        response=httpx.Response(404, request=REQUEST),
    ),
    httpx.HTTPStatusError(
        "Ollama returned 500: out of memory",
        request=REQUEST,
        response=httpx.Response(500, request=REQUEST),
    ),
    KeyError("response"),
]

#: What the person must never read: the app's own vocabulary.
JARGON = re.compile(
    r"JSON|ReplyCutShort|ReplyNotJSON|InvariantViolation|Timeout\b|Error\b|done_reason"
)


@pytest.mark.parametrize("exc", FAILURES, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("kind", ["receipt", "nl_parse"])
def test_every_failure_is_a_plain_sentence(exc, kind):
    text = failure_text(exc, kind)
    assert text and text[0].isupper() and text.rstrip().endswith((".", ")"))
    if not isinstance(exc, KeyError):  # the catch-all quotes it, as a last resort
        assert not JARGON.search(text), text


def test_a_receipt_says_receipt_and_a_description_says_description():
    exc = ReplyNotJSON("no object")
    assert "this receipt" in failure_text(exc, "receipt")
    assert "this description" in failure_text(exc, "nl_parse")


@pytest.mark.parametrize(
    ("reason", "setting"),
    [("length", "Thinking"), ("deadline", "Receipt scan timeout")],
)
def test_a_cut_short_read_names_the_setting_that_helps(reason, setting):
    text = failure_text(ReplyCutShort("cut off", reason), "receipt")
    assert f"System → AI → Advanced → {setting}" in text


def test_a_loop_says_it_was_stopped():
    assert "stuck repeating" in failure_text(ReplyCutShort("x", "repetition"), "receipt")


def test_a_missing_model_is_named():
    exc = FAILURES[9]
    assert "model 'gemma4:31b' not found" in failure_text(exc, "receipt")


def test_a_message_written_for_people_passes_through():
    msg = "The image doesn't appear to be a receipt — created an empty transaction"
    assert failure_text(NonRetryableJobError(msg), "receipt") == msg


def test_the_catch_all_still_says_what_it_was():
    assert "KeyError" in failure_text(KeyError("response"), "receipt")
