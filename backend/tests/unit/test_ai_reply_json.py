"""parse_json_reply: every reply shape a model has handed the receipt path.

The parser it replaces accepted a bare object or a reply that started with a
fence. Each case below that says "used to fail" failed every scan, and at
temperature 0 failed every retry the same way.
"""

import pytest

from igab.ai.reply_json import ReplyNotJSON, parse_json_reply

OBJ = '{"payee": "Corner Market", "total": 39.53, "card_last4": "4417"}'
PARSED = {"payee": "Corner Market", "total": 39.53, "card_last4": "4417"}


class TestTheAnswerIsFound:
    def test_bare_object(self):
        assert parse_json_reply(OBJ) == PARSED

    def test_fenced(self):
        assert parse_json_reply(f"```json\n{OBJ}\n```") == PARSED

    def test_fenced_without_a_language(self):
        assert parse_json_reply(f"```\n{OBJ}\n```") == PARSED

    def test_fence_tag_in_capitals_used_to_fail(self):
        assert parse_json_reply(f"```JSON\n{OBJ}\n```") == PARSED

    def test_a_sentence_before_the_fence_used_to_fail(self):
        assert parse_json_reply(f"Here is the extracted data:\n```json\n{OBJ}\n```") == PARSED

    def test_a_sentence_before_a_bare_object_used_to_fail(self):
        assert parse_json_reply(f"Here is the JSON:\n{OBJ}") == PARSED

    def test_a_note_after_the_object_used_to_fail(self):
        assert parse_json_reply(f"{OBJ}\nThe total includes tax.") == PARSED

    def test_a_note_after_the_fence(self):
        assert parse_json_reply(f"```json\n{OBJ}\n```\nLet me know if you need more.") == PARSED

    def test_an_array_around_the_object_used_to_fail(self):
        assert parse_json_reply(f"[{OBJ}]") == PARSED

    def test_a_brace_in_the_prose_is_not_the_answer(self):
        assert parse_json_reply(f"Matched against {{categories}}:\n{OBJ}") == PARSED

    def test_nested_objects_stay_inside_their_parent(self):
        reply = '{"total": 5, "line_items": [{"description": "Soap", "amount": 5}]}'
        assert parse_json_reply(reply)["line_items"] == [{"description": "Soap", "amount": 5}]

    def test_the_fenced_object_wins_over_a_stray_one_before_it(self):
        reply = 'I considered {"total": 0} first.\n```json\n' + OBJ + "\n```"
        assert parse_json_reply(reply) == PARSED


class TestReasoningLeftInTheReply:
    """A server that does not split reasoning out passes it through in
    `response`, in one of two spellings."""

    def test_think_block_used_to_fail(self):
        assert parse_json_reply(f"<think>The receipt shows {{a total}}…</think>\n{OBJ}") == PARSED

    def test_gemma_channel_block(self):
        reply = f'<|channel>thought\nTotal is {{"total": 1}}? No, 39.53.<channel|>{OBJ}'
        assert parse_json_reply(reply) == PARSED

    def test_gemma_empty_thought_block_with_thinking_off(self):
        # gemma4 above E4B writes the tags even with thinking disabled.
        assert parse_json_reply(f"<|channel>thought\n<channel|>{OBJ}") == PARSED

    def test_a_block_whose_start_was_already_dropped(self):
        assert parse_json_reply(f'draft {{"total": 1}}</think>\n{OBJ}') == PARSED

    def test_a_reply_cut_off_inside_its_reasoning_has_no_answer(self):
        with pytest.raises(ReplyNotJSON):
            parse_json_reply('<think>maybe {"total": 1} or')


class TestTheAnswerWentIntoThinking:
    def test_an_empty_response_reads_the_thinking_used_to_fail(self):
        assert parse_json_reply("", thinking=f"Reading the receipt.\n{OBJ}") == PARSED

    def test_the_last_object_in_the_thinking_is_the_answer(self):
        thinking = f'First guess {{"total": 36.94}} — that is the subtotal.\nFinal:\n{OBJ}'
        assert parse_json_reply("", thinking=thinking) == PARSED

    def test_a_response_object_wins_over_the_thinking(self):
        assert parse_json_reply(OBJ, thinking='{"total": 1}') == PARSED

    def test_prose_in_response_falls_back_to_the_thinking(self):
        assert parse_json_reply("Done.", thinking=OBJ) == PARSED


class TestACutOffAnswerIsRefused:
    """gemma4 at a 4k window with 180 categories: the thinking took the room
    and the answer stopped four line items in. The first complete object in
    that reply is a line item — returning it filed the bananas as the whole
    receipt."""

    CUT = (
        '```json\n{\n  "payee": "Corner Market",\n  "total": 39.53,\n  "line_items": [\n'
        '    {"description": "ORGANIC BANANAS", "amount": 2.49, "category": "Groceries"},\n'
        '    {"description": "WHOLE MI'
    )

    def test_never_mined_for_a_nested_object(self):
        with pytest.raises(ReplyNotJSON, match="cut off"):
            parse_json_reply(self.CUT, done_reason="length")

    def test_refused_even_when_the_server_did_not_say_so(self):
        with pytest.raises(ReplyNotJSON, match="stops before it is complete"):
            parse_json_reply(self.CUT)

    def test_the_thinking_is_not_read_for_a_cut_off_reply(self):
        with pytest.raises(ReplyNotJSON, match="cut off"):
            parse_json_reply("", thinking=OBJ, done_reason="length")

    def test_the_thinking_is_not_read_once_the_answer_began(self):
        with pytest.raises(ReplyNotJSON):
            parse_json_reply('{"payee": "Corner Market", "tot', thinking=OBJ)


class TestProseBraces:
    def test_an_unclosed_prose_brace_before_the_answer(self):
        assert parse_json_reply(f"Note: {{ see below\n{OBJ}") == PARSED

    def test_a_malformed_object_is_skipped_whole(self):
        reply = '{"total": 1, "items": [{"a": 1}],}\n' + OBJ
        assert parse_json_reply(reply) == PARSED

    def test_braces_inside_strings_do_not_count(self):
        reply = '{"memo": "set {x} aside }", "total": 2}'
        assert parse_json_reply(reply) == {"memo": "set {x} aside }", "total": 2}


class TestTheErrorNamesTheCause:
    def test_cut_off(self):
        with pytest.raises(ReplyNotJSON, match="cut off"):
            parse_json_reply(OBJ[:40], done_reason="length")

    def test_a_complete_object_is_kept_even_when_cut_off(self):
        assert parse_json_reply(OBJ + "\nAnd also", done_reason="length") == PARSED

    def test_empty(self):
        with pytest.raises(ReplyNotJSON, match="empty reply"):
            parse_json_reply("")

    def test_none_is_empty(self):
        with pytest.raises(ReplyNotJSON, match="empty reply"):
            parse_json_reply(None)

    def test_reasoning_but_no_answer(self):
        with pytest.raises(ReplyNotJSON, match="reasoning but no answer"):
            parse_json_reply("", thinking="The total looks like 39.53.")

    def test_prose_is_quoted(self):
        with pytest.raises(ReplyNotJSON, match="the total is"):
            parse_json_reply("the total is $42")

    def test_a_non_object_is_not_an_answer(self):
        with pytest.raises(ReplyNotJSON):
            parse_json_reply("[1, 2]")

    def test_it_is_a_value_error_so_the_worker_retries_it(self):
        assert issubclass(ReplyNotJSON, ValueError)
