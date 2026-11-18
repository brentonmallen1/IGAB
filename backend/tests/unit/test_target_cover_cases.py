"""Target Amount vs Cover + target — the shared cases.

`shared/target_cover_cases.json` runs here and in
`frontend/src/utils/targetCover.test.ts`. The server serves both figures and
makes the pick it applies (`pick_target_figure`); the client makes the same
pick from the served figures to draw the button total and the optimistic
grid before the round-trip. There is no shared code path between Python and
TypeScript, so a pick changed on one side only is caught by these two suites
or not at all.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from igab.services.assign_service import pick_target_figure
from igab.services.target_service import TargetService

_CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "target_cover_cases.json").read_text()
)["cases"]


def _dec(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _target(spec: dict) -> MagicMock:
    t = MagicMock()
    t.target_type = spec["type"]
    t.target_amount = Decimal(spec["amount"])
    t.target_date = None
    t.weekday = spec.get("weekday")
    t.check_after_day = None
    t.target_limit = _dec(spec.get("limit"))
    return t


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_the_server_serves_both_figures(case):
    svc = TargetService(repo=None)  # type: ignore[arg-type]
    figures = dict(
        assigned=Decimal(case["assigned"]),
        activity=Decimal(case["activity"]),
        available=Decimal(case["available"]),
        month=date.fromisoformat(case["month"]),
    )
    target = _target(case["target"])
    assert svc.target_assigned(target, **figures) == _dec(case["target_assigned"])
    assert svc.cover_and_target_assigned(target, **figures) == _dec(case["cover_target_assigned"])


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_the_server_picks_what_the_client_picks(case):
    plain = Decimal(case["target_assigned"])
    cover = _dec(case["cover_target_assigned"])
    assert pick_target_figure(plain, cover, False) == Decimal(case["as_target"])
    assert pick_target_figure(plain, cover, True) == Decimal(case["as_cover"])
