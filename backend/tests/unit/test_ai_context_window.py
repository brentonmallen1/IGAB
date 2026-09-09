"""Sizing the assistant's context window, and what one tool result may take.

Pinned because the first version had neither: a hard 6,000-character cap on
every tool result, and no num_ctx on the request at all. The cap turned a
month grid of 188 envelopes into "too many categories to list" while the
model had 128k of context going spare.
"""

from igab.ai.context_window import (
    AUTO_CONTEXT_CAP,
    CONTEXT_FLOOR,
    MIN_RESULT_CHARS,
    resolve_num_ctx,
    result_char_budget,
)


class TestResolvingTheWindow:
    def test_auto_takes_the_model_max_up_to_the_cap(self):
        assert resolve_num_ctx("auto", 131_072) == AUTO_CONTEXT_CAP
        assert resolve_num_ctx("", 131_072) == AUTO_CONTEXT_CAP
        assert resolve_num_ctx(None, 16_384) == 16_384

    def test_auto_with_an_unknown_model_falls_to_the_floor(self):
        assert resolve_num_ctx("auto", None) == CONTEXT_FLOOR

    def test_a_number_is_used_as_written(self):
        assert resolve_num_ctx("65536", 131_072) == 65_536

    def test_a_number_is_clamped_to_what_the_model_can_take(self):
        assert resolve_num_ctx("131072", 32_768) == 32_768

    def test_a_number_below_the_floor_is_lifted(self):
        assert resolve_num_ctx("512", 131_072) == CONTEXT_FLOOR

    def test_garbage_falls_back_to_auto(self):
        assert resolve_num_ctx("lots", 131_072) == AUTO_CONTEXT_CAP


class TestTheResultBudget:
    def test_grows_with_the_window(self):
        assert result_char_budget(AUTO_CONTEXT_CAP) > result_char_budget(8_192)

    def test_never_below_the_old_cap(self):
        # A small window must not give a tool less room than it always had.
        assert result_char_budget(CONTEXT_FLOOR) == MIN_RESULT_CHARS

    def test_a_default_window_fits_a_large_month_grid(self):
        # 188 envelopes at ~75 characters each, grouped: the case that broke.
        assert result_char_budget(AUTO_CONTEXT_CAP) > 188 * 75
