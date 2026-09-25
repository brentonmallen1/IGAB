"""The reply schemas, held to the prompts that describe them in prose and to
the parser that reads them.

The model reads the prompt; Ollama's grammar reads the schema. That is two
descriptions of one reply, irreducibly, so this is what keeps them one:

- a field the prompt asks for but the schema lacks is a field the grammar
  forbids — the model is told to write it and cannot;
- a key parse_extraction reads that the schema does not require is a key a
  model may leave out, which is how `{"merchant": …, "amount": …}` became
  "AI extraction returned no amount".
"""

import datetime
import re

import pytest

from igab.services.ai_draft_service import (
    NL_REPLY_SCHEMA,
    RECEIPT_REPLY_SCHEMA,
    parse_extraction,
)
from igab.services.ai_prompts import DEFAULT_PROMPTS

CASES = [
    ("receipt", "ai_prompt_receipt_extract", RECEIPT_REPLY_SCHEMA, {"total": 1}),
    ("nl_parse", "ai_prompt_nl_parse", NL_REPLY_SCHEMA, {"amount": 1}),
]


def prompt_fields(key: str) -> set[str]:
    """Every "name": the default prompt's JSON example spells out."""
    example = DEFAULT_PROMPTS[key].split("Return ONLY a JSON object", 1)[1]
    return set(re.findall(r'"(\w+)":', example))


def schema_fields(schema: dict) -> set[str]:
    """Every property name at any depth."""
    names: set[str] = set()
    for name, sub in schema.get("properties", {}).items():
        names.add(name)
        names |= schema_fields(sub)
    if isinstance(schema.get("items"), dict):
        names |= schema_fields(schema["items"])
    return names


class Recording(dict):
    """A reply that remembers which keys the parser asked it for."""

    def __init__(self, *args):
        super().__init__(*args)
        self.read: set[str] = set()

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)


@pytest.mark.parametrize(("kind", "prompt_key", "schema", "minimal"), CASES)
def test_the_prompt_and_the_schema_name_the_same_fields(kind, prompt_key, schema, minimal):
    assert prompt_fields(prompt_key) == schema_fields(schema)


@pytest.mark.parametrize(("kind", "prompt_key", "schema", "minimal"), CASES)
def test_every_key_the_parser_reads_is_required(kind, prompt_key, schema, minimal):
    reply = Recording(minimal)
    parse_extraction(reply, kind=kind, client_today=datetime.date(2026, 9, 25))
    assert reply.read, "the recording saw nothing — parse_extraction stopped reading .get"
    assert reply.read <= set(schema["required"])


@pytest.mark.parametrize(("kind", "prompt_key", "schema", "minimal"), CASES)
def test_every_property_is_required(kind, prompt_key, schema, minimal):
    """A saved prompt override from before a field existed never asks for
    it; a required key is written anyway (null when the receipt has none)."""
    assert set(schema["required"]) == set(schema["properties"])


def test_a_reply_to_the_schema_parses():
    """The shape gemma4 returned under this schema on Ollama 0.34."""
    reply = {
        "payee": "Corner Market",
        "total": 39.53,
        "date": "2026-09-20",
        "category": "Groceries",
        "reason": "Mostly food.",
        "confidence": 0.9,
        "memo": "Groceries + seedlings",
        "line_items": [{"description": "ORGANIC BANANAS", "amount": 2.49, "category": None}],
        "suggested_split": [],
        "card_last4": "4417",
    }
    draft = parse_extraction(
        reply,
        kind="receipt",
        client_today=datetime.date(2026, 9, 25),
        category_names=[("Groceries", "Everyday")],
    )
    assert str(draft.amount) == "-39.53"
    assert draft.card_last4 == "4417"
    assert draft.category_name is not None
