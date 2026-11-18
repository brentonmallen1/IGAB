"""Which failed AI jobs run again, and what a failure says."""

import httpx

from igab.ai.context import error_text
from igab.ai.reply_json import ReplyCutShort, ReplyNotJSON
from igab.tasks.ai_worker import _is_retryable


class TestRetry:
    def test_a_reply_cut_short_is_not_run_again(self):
        """Same call, same stop: retrying it is how one long receipt held the
        model for 15 minutes."""
        assert not _is_retryable(ReplyCutShort("cut off", "repetition"))

    def test_malformed_json_still_gets_another_try(self):
        assert _is_retryable(ReplyNotJSON("no object"))

    def test_ollama_going_silent_still_gets_another_try(self):
        assert _is_retryable(httpx.ReadTimeout(""))
        assert _is_retryable(httpx.ConnectError("refused"))


class TestErrorText:
    def test_an_empty_timeout_says_what_happened(self):
        text = error_text(httpx.ReadTimeout(""))
        assert text.startswith("ReadTimeout: Ollama stopped sending anything")

    def test_a_message_is_kept(self):
        assert error_text(ValueError("bad total")) == "ValueError: bad total"

    def test_anything_else_empty_is_never_blank(self):
        assert error_text(RuntimeError()) == "RuntimeError: no detail given"
