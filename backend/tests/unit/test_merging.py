"""Who survives a merge — domain.merging — pinned by each rung of the
precedence, and each refusal. Two merge paths used to carry their own
version of this and agreed only on the first rung.
"""

import uuid
from datetime import UTC, datetime

from igab.domain.merging import MergeSide, choose_survivor, survivor_violation

ACCOUNT = uuid.uuid4()
T0 = datetime(2026, 7, 1, tzinfo=UTC)
T1 = datetime(2026, 7, 2, tzinfo=UTC)


def side(**over) -> MergeSide:
    base = dict(
        id=uuid.uuid4(),
        cleared="uncleared",
        is_split=False,
        transfer_id=None,
        parent_transaction_id=None,
        account_id=ACCOUNT,
        sync_id=None,
        sync_source=None,
        created_at=T0,
    )
    base.update(over)
    return MergeSide(**base)


def test_reconciled_outranks_everything():
    rec = side(cleared="reconciled", created_at=T1)
    split = side(is_split=True)
    assert choose_survivor(split, rec, requested=split.id)[0] is rec


def test_structured_outranks_the_requested_row():
    split = side(is_split=True, created_at=T1)
    flat = side()
    assert choose_survivor(flat, split, requested=flat.id)[0] is split
    leg = side(transfer_id=uuid.uuid4(), created_at=T1)
    assert choose_survivor(flat, leg, requested=flat.id)[0] is leg


def test_the_requested_row_wins_among_equals():
    a, b = side(), side(created_at=T1)
    assert choose_survivor(a, b, requested=b.id)[0] is b


def test_the_user_entered_row_beats_the_bank_row():
    bank = side(sync_source="simplefin", created_at=T0)
    manual = side(created_at=T1)
    assert choose_survivor(bank, manual, requested=None)[0] is manual
    idless = side(sync_source="simplefin", sync_id=None)
    assert choose_survivor(manual, idless, requested=None)[0] is manual


def test_older_row_survives_a_true_tie():
    older, newer = side(created_at=T0), side(created_at=T1)
    assert choose_survivor(newer, older, requested=None)[0] is older


def test_refusals_by_name():
    rec_a, rec_b = side(cleared="reconciled"), side(cleared="reconciled")
    assert "two reconciled" in survivor_violation(rec_a, rec_b, None)

    line = side(parent_transaction_id=uuid.uuid4())
    assert "split line" in survivor_violation(side(), line, None)

    a, b = side(), side()
    assert "survivor_id" in survivor_violation(a, b, uuid.uuid4())

    rec = side(cleared="reconciled")
    other = side()
    assert "reconciled transaction must be kept" in survivor_violation(rec, other, other.id)

    split = side(is_split=True)
    flat = side()
    assert "must be kept as the survivor" in survivor_violation(split, flat, flat.id)
    assert "merge away a split" in survivor_violation(rec, split, None)
    leg = side(transfer_id=uuid.uuid4())
    assert "merge away a transfer" in survivor_violation(rec, leg, None)

    elsewhere = side(account_id=uuid.uuid4())
    assert "same account" in survivor_violation(side(), elsewhere, None)

    x = side(sync_id="t-a", sync_source="simplefin")
    y = side(sync_id="t-b", sync_source="simplefin")
    assert "different bank" in survivor_violation(x, y, None)

    same = side()
    assert "itself" in survivor_violation(same, same, None)


def test_a_clean_pair_has_no_violation():
    assert survivor_violation(side(), side(sync_id="t-1", sync_source="simplefin"), None) is None
