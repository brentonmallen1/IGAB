"""Which moves between accounts are refused — domain.account_move.

Every branch reachable from the editor's account picker, stated once and
without a database. The service tests (tests/integration/test_account_move.py)
then only have to prove the wiring reaches this rule and that what moves
alongside the row actually moves.
"""

import uuid

from igab.domain.account_move import MoveRequest, refusal_for_move

TARGET = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
ELSEWHERE = uuid.UUID("00000000-0000-0000-0000-0000000000bb")


def _request(**over) -> MoveRequest:
    base = {
        "target_account_id": TARGET,
        "target_is_closed": False,
        "is_split_child": False,
        "is_bank_synced": False,
    }
    return MoveRequest(**{**base, **over})


def test_an_ordinary_row_may_move():
    assert refusal_for_move(_request()) is None


def test_a_split_line_may_not_move_on_its_own():
    # The lines carry the parent's account; moving one alone would put the
    # account balance and the category activity in two different accounts.
    refusal = refusal_for_move(_request(is_split_child=True))
    assert refusal is not None
    assert "parent" in refusal


def test_a_split_parent_may_move():
    # It takes its lines with it — the service mirrors them.
    assert refusal_for_move(_request(is_split_child=False)) is None


def test_a_bank_fed_row_may_not_move():
    """`find_by_sync_id` is account-scoped, so the feed would not find the row
    it reported and would add it back — the same money in two accounts."""
    refusal = refusal_for_move(_request(is_bank_synced=True))
    assert refusal is not None
    assert "bank feed" in refusal


def test_a_closed_account_is_not_a_destination():
    refusal = refusal_for_move(_request(target_is_closed=True))
    assert refusal is not None
    assert "closed" in refusal


def test_a_transfer_leg_may_move_to_a_third_account():
    assert refusal_for_move(_request(counterpart_account_id=ELSEWHERE)) is None


def test_a_transfer_leg_may_not_move_into_its_own_counterpart():
    # Both sides in one account is not a transfer; it is two rows that cancel.
    refusal = refusal_for_move(_request(counterpart_account_id=TARGET))
    assert refusal is not None
    assert "both sides" in refusal


def test_moving_and_retargeting_a_transfer_at_once_is_refused():
    """Two accounts changing in one request — the row's and the transfer's —
    and no order of application that is obviously the one meant. The editor
    sends them as separate edits, as it already does for breaking a link."""
    refusal = refusal_for_move(_request(retargeting_transfer=True))
    assert refusal is not None
    assert "separate edits" in refusal


def test_the_structural_refusals_come_before_the_transfer_ones():
    """A split line of a bank-fed row states the plainest reason, not the
    last one checked — the order is part of the rule."""
    refusal = refusal_for_move(
        _request(is_split_child=True, is_bank_synced=True, counterpart_account_id=TARGET)
    )
    assert refusal is not None
    assert "parent" in refusal
