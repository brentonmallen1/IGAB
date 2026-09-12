"""`previous_window` against the cases the frontend's `previousWindow` also runs."""

import json
from datetime import date
from pathlib import Path

import pytest

from igab.domain.dates import previous_window

_CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "previous_window_cases.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[c["note"] for c in _CASES])
def test_the_shared_cases(case):
    got = previous_window(date.fromisoformat(case["start"]), date.fromisoformat(case["end"]))
    assert got == (date.fromisoformat(case["prev_start"]), date.fromisoformat(case["prev_end"]))
