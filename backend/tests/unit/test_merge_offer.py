"""Whether a merge may be offered at all — the half of the merge rule the
register also has to know.

Every case here is run by the frontend too, from `shared/merge_cases.json`.
A rule changed on one side only fails on the other. The fixture exists
because the client's copy had already drifted past the server's: two bank
rows with different bank ids were offered as mergeable and refused on every
save, with the refusal swallowed by the modal.
"""

import json
import uuid
from pathlib import Path

import pytest

from igab.domain.merging import MergeSide, choose_survivor, may_offer_merge

CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "merge_cases.json").read_text()
)["cases"]

_IDS: dict[str, uuid.UUID] = {}


def _id(key: str | None) -> uuid.UUID | None:
    """Stable uuid per fixture key, so 'a1' is one account on both sides."""
    if key is None:
        return None
    return _IDS.setdefault(key, uuid.uuid4())


def _side(spec: dict, key: str) -> MergeSide:
    return MergeSide(
        id=_id(key),  # type: ignore[arg-type]
        cleared=spec["cleared"],
        is_split=bool(spec.get("is_split")),
        transfer_id=_id(spec.get("transfer_id")),
        parent_transaction_id=_id(spec.get("parent_transaction_id")),
        account_id=_id(spec["account_id"]),  # type: ignore[arg-type]
        sync_id=spec.get("sync_id"),
        sync_source="simplefin" if spec.get("sync_id") else None,
        created_at=None,
    )


@pytest.mark.parametrize("case", CASES, ids=[c["note"] for c in CASES])
def test_shared_merge_cases(case):
    a, b = _side(case["a"], "side-a"), _side(case["b"], "side-b")
    assert may_offer_merge(a, b) is case["server_accepts"], case["note"]
    # Order is not part of the question: the register has no first row.
    assert may_offer_merge(b, a) is case["server_accepts"], case["note"]


@pytest.mark.parametrize("case", CASES, ids=[c["note"] for c in CASES])
def test_the_register_never_offers_what_the_server_refuses(case):
    """The invariant the Hobby Lobby duplicate broke. Where the register
    offers LESS, the fixture names why; where it would offer MORE, this
    fails on both sides."""
    if case["register_offers"]:
        assert case["server_accepts"], case["note"]


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["register_offers"]], ids=lambda c: c["note"]
)
def test_kept_is_the_server_survivor(case):
    """`kept` is who survives whatever the user picks; null means the pick is
    honoured. The merge preview locks its Keep badge from the same field."""
    a, b = _side(case["a"], "side-a"), _side(case["b"], "side-b")
    if case["kept"] is None:
        assert choose_survivor(a, b, a.id)[0] is a and choose_survivor(a, b, b.id)[0] is b
        return
    kept = a if case["kept"] == "a" else b
    for requested in (None, a.id, b.id):
        assert choose_survivor(a, b, requested)[0] is kept, case["note"]
        assert choose_survivor(b, a, requested)[0] is kept, case["note"]
