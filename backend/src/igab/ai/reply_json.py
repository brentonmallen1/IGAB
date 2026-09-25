"""Reading one JSON object out of a model's reply — pure.

A reply decoded under Ollama's `format` (JSON mode or a schema) is the object
and nothing else. Everything else a model may write around it: the object in a
code fence, after a sentence ("Here is the data:"), before a note, inside a
reasoning block a server did not split out, or not in `response` at all
because the answer went into the thinking.

The first parser here accepted a bare object or a reply that *started* with a
fence, and nothing else. A model that opened with one sentence failed every
scan, and at temperature 0 it failed every retry identically.

A reply that was cut off is refused, never mined for a smaller object. A
thinking model on a 4k window, reading 180 categories, ran out of room four
line items into its answer; picking the first complete object out of that
would have filed the bananas as the whole receipt.

Model-agnostic on purpose: it looks for an object, not for one model's habits.
The reasoning markers it strips are the two spellings in circulation (`<think>`
and gemma's `<|channel>thought … <channel|>`), for a server that passes them
through instead of moving them into `thinking`.
"""

import json
import re

#: A complete reasoning block, in either spelling.
_REASONING_BLOCK = re.compile(r"<think>.*?</think>|<\|channel>thought.*?<channel\|>", re.DOTALL)
#: The end of a reasoning block whose start the server already dropped.
_REASONING_END = re.compile(r"</think>|<channel\|>")
#: The start of a reasoning block that never ended — the reply was cut off in it.
_REASONING_START = re.compile(r"<think>|<\|channel>")
#: A fenced block, any language tag or none, any case. An unclosed fence is
#: not matched: its object is read, or refused as cut off, by the plain scan.
_FENCE = re.compile(r"```[A-Za-z]*[ \t]*\n?(.*?)```", re.DOTALL)
#: A brace that can open a JSON object: a key or the end follows it. Braces in
#: prose ("{categories}", "{ see below") are not candidates.
_OBJECT_START = re.compile(r'\{\s*["}]')

#: How much of an unreadable reply the error quotes.
_QUOTE_CHARS = 120


class ReplyNotJSON(ValueError):
    """The reply held no JSON object. A ValueError, so the AI worker's retry
    rule treats it like the JSONDecodeError it replaces."""


def _closing(text: str, start: int) -> int | None:
    """The index just past the brace that closes the one at `start`, reading
    JSON strings as strings — or None when the text ends first."""
    depth = 0
    in_string = escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def _scan(text: str) -> tuple[list[dict], bool]:
    """(every complete top-level object, whether one was left unfinished).

    Scanning stops at an unfinished object: everything after its start is
    inside it, and a nested object of a truncated answer is not an answer."""
    found: list[dict] = []
    pos = 0
    while match := _OBJECT_START.search(text, pos):
        start = match.start()
        end = _closing(text, start)
        if end is None:
            return found, True
        try:
            value = json.loads(text[start:end])
        except json.JSONDecodeError:
            value = None  # malformed but closed: skip it whole, never mine it
        if isinstance(value, dict):
            found.append(value)
        pos = end
    return found, False


def _answer_text(response: str) -> str:
    """The reply with any reasoning removed."""
    text = _REASONING_BLOCK.sub("", response)
    ends = list(_REASONING_END.finditer(text))
    if ends:
        text = text[ends[-1].end() :]
    started = _REASONING_START.search(text)
    if started:
        text = text[: started.start()]
    return text.strip()


def _answer_object(text: str) -> tuple[dict | None, bool]:
    """(the answer's object, whether the reply was left unfinished). A fenced
    object first — the fence is the model saying "this is the answer" — then
    the first object anywhere."""
    for fenced in _FENCE.findall(text):
        objects, _ = _scan(fenced)
        if objects:
            return objects[0], False
    objects, unfinished = _scan(text)
    return (objects[0] if objects else None), unfinished


def parse_json_reply(
    response: str | None,
    *,
    thinking: str | None = None,
    done_reason: str | None = None,
) -> dict:
    """The JSON object a model answered with.

    Looks in `response` first. When the response never began an object and
    the model finished on its own, the last object in `thinking` is taken: a
    thinking model can write its whole answer there and leave `response`
    empty. Raises ReplyNotJSON saying which of those happened, so the AI
    Activity row names the cause instead of quoting a JSONDecodeError.
    """
    answer = _answer_text(response or "")
    found, unfinished = _answer_object(answer)
    if found is not None:
        return found

    cut_off = done_reason == "length"
    if thinking and not cut_off and not _OBJECT_START.search(answer):
        from_thinking, _ = _scan(thinking)
        if from_thinking:
            return from_thinking[-1]

    if cut_off:
        raise ReplyNotJSON(
            "The model's reply was cut off before its JSON was complete: it ran out of"
            " room (context window or output limit)."
        )
    if unfinished:
        raise ReplyNotJSON("The model's JSON reply stops before it is complete.")
    text = (response or "").strip()
    if not text:
        if thinking:
            raise ReplyNotJSON(
                "The model wrote its reasoning but no answer: the reply was empty and the"
                " thinking held no JSON object."
            )
        raise ReplyNotJSON("The model returned an empty reply.")
    quoted = text[:_QUOTE_CHARS] + ("…" if len(text) > _QUOTE_CHARS else "")
    raise ReplyNotJSON(f"The model's reply held no JSON object: {quoted!r}")
