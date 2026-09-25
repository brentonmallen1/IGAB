"""The label format the model's category travels in, pinned on both sides.

`canonical_label` writes it into `result.draft.category` and each suggested
split line; the client reads it back to tell which category a label means
(`labelNamesCategory` in frontend/src/components/ai/draftNotes.ts). The
`shared/category_label_cases.json` block runs the same cases there, so a
format changed on one side only fails on the other.
"""

import json
from pathlib import Path

import pytest

from igab.services.category_matching import canonical_label

_CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "category_label_cases.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[c["note"] for c in _CASES])
def test_the_writer_produces_the_shared_label(case):
    candidates = [(name, group) for name, group in case["candidates"]]
    assert canonical_label(case["index"], candidates) == case["label"]
