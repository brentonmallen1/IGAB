"""`items_to_share` against the cases the frontend's Pareto math also runs."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from igab.domain.concentration import items_to_share

_CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "pareto_cases.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[c["note"] for c in _CASES])
def test_the_shared_cases(case):
    assert items_to_share([Decimal(str(t)) for t in case["totals"]]) == case["items_to_80"]
