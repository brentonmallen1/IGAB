"""How much of a model's context the assistant may use, and what fits in it.

Ollama's default context is small — 4,096 tokens on a stock install, and a
prompt that overflows it is truncated from the *front*, which is where the
system prompt lives. The app never used to say ``num_ctx`` at all, so it
depended on the server having been configured generously. It now asks for
a window explicitly, sized from what the model reports unless the user
picks one.

Pure: takes the model's advertised length and the settings, returns numbers.
"""

#: What "auto" asks for when the model could take more. The KV cache scales
#: with the window, so the whole 128k a gemma4 advertises is not free; a
#: month grid with two hundred envelopes and a few tool rounds fits in a
#: quarter of this.
AUTO_CONTEXT_CAP = 32_768

#: Below this the system prompt plus the tool schema alone would crowd out an
#: answer. Also the fallback when the model reports nothing.
CONTEXT_FLOOR = 4_096

#: Roughly how many characters of JSON a token covers. Figures and
#: punctuation tokenize worse than prose, so this leans low.
CHARS_PER_TOKEN = 3

#: The share of the window a single tool result may take. The rest is the
#: prompt, the history, earlier tool results this turn, and the answer.
RESULT_SHARE = 0.25

#: The cap before any of this existed. Kept as the floor so a small window
#: never gives a tool *less* room than it had.
MIN_RESULT_CHARS = 6_000


def resolve_num_ctx(setting: str | None, model_max: int | None) -> int:
    """The window to request.

    ``setting`` is the ``ai_chat_num_ctx`` value: empty or "auto" sizes from
    the model, a number is used as written (clamped to what the model can
    take, when that is known).
    """
    if setting and setting.strip().lower() != "auto":
        try:
            chosen = int(setting)
        except ValueError:
            chosen = 0
        if chosen > 0:
            return max(CONTEXT_FLOOR, min(chosen, model_max) if model_max else chosen)
    if model_max:
        return max(CONTEXT_FLOOR, min(model_max, AUTO_CONTEXT_CAP))
    return CONTEXT_FLOOR


def result_char_budget(num_ctx: int) -> int:
    """How many characters one tool result may be before it is summarized."""
    return max(MIN_RESULT_CHARS, int(num_ctx * RESULT_SHARE * CHARS_PER_TOKEN))
