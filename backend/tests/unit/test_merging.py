"""Who survives a merge — domain.merging — pinned by each rung of the
precedence, and each refusal. Two merge paths used to carry their own
version of this and agreed only on the first rung.
"""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from igab.domain.merging import (
    MergePlan,
    MergeSide,
    Refused,
    choose_survivor,
    plan_merge,
    survivor_violation,
)

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
        amount=Decimal("-500.00"),
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
    assert survivor_violation(rec, split, None) is None, "a reconciled plain row takes the split"
    assert "another split" in survivor_violation(
        side(is_split=True, cleared="reconciled"), split, None
    )
    leg = side(transfer_id=uuid.uuid4())
    assert survivor_violation(rec, leg, None) is None, "a leg's transfer is the plan's question"

    elsewhere = side(account_id=uuid.uuid4())
    assert "same account" in survivor_violation(side(), elsewhere, None)

    x = side(sync_id="t-a", sync_source="simplefin")
    y = side(sync_id="t-b", sync_source="simplefin")
    assert "different bank" in survivor_violation(x, y, None)

    same = side()
    assert "itself" in survivor_violation(same, same, None)


def test_a_clean_pair_has_no_violation():
    assert survivor_violation(side(), side(sync_id="t-1", sync_source="simplefin"), None) is None


# ─── What becomes of a transfer leg that loses ──────────────────────────────
#
# The review queue used to refuse every one of these with "Cannot merge away a
# transfer", and nothing else on screen could resolve the duplicate.

CARD = uuid.uuid4()


def pair(**over) -> tuple[MergeSide, MergeSide]:
    """A checking leg and its card leg, linked both ways: a $500 payment.
    `over` is applied to the checking leg."""
    leg_id, partner_id = uuid.uuid4(), uuid.uuid4()
    leg = side(id=leg_id, transfer_id=partner_id, **over)
    partner = side(id=partner_id, transfer_id=leg_id, account_id=CARD, amount=Decimal("500.00"))
    return leg, partner


def changed(s: MergeSide, **over) -> MergeSide:
    return replace(s, **over)


def partners_of(*sides: MergeSide) -> dict[uuid.UUID, MergeSide]:
    return {s.id: s for s in sides}


def test_a_reconciled_plain_row_takes_the_transfer_over():
    """The statement row survives and becomes the leg; the deleted leg's
    partner is the one it links to."""
    typed, card_leg = pair()
    statement = side(cleared="reconciled", sync_id="t-1", sync_source="simplefin")

    plan = plan_merge(typed, statement, None, partners_of(card_leg))

    assert isinstance(plan, MergePlan)
    assert plan.survivor is statement and plan.deleted is typed
    assert plan.adopted_partner is card_leg and plan.partner_merge is None
    assert plan.survivor_partner is card_leg and plan.relinks


def test_a_plain_duplicate_of_a_leg_changes_no_link():
    typed, _ = pair()
    plan = plan_merge(typed, side(sync_id="t-1", sync_source="simplefin"), None, {})
    assert isinstance(plan, MergePlan)
    assert plan.survivor is typed and plan.adopted_partner is None
    assert not plan.relinks, "the leg keeps the partner it had"


def test_two_transfers_for_one_payment_merge_on_both_accounts():
    """The sync shape: the typed payment, and the bank's two rows paired
    into a second transfer. The typed pair survives on both sides, the bank
    pair goes, and no link has to move."""
    typed, typed_card = pair(created_at=T0)
    bank, bank_card = pair(sync_id="t-chk", sync_source="simplefin", created_at=T1)
    bank_card = changed(bank_card, sync_id="t-card", sync_source="simplefin")

    plan = plan_merge(bank, typed, None, partners_of(typed_card, bank_card))

    assert isinstance(plan, MergePlan)
    assert plan.survivor is typed and plan.deleted is bank
    assert plan.partner_merge is not None
    assert plan.partner_merge.survivor is typed_card and plan.partner_merge.deleted is bank_card
    assert not plan.relinks


def test_the_far_pair_follows_its_own_precedence():
    """A reconciled card leg survives on the card even when its checking leg
    loses — so the checking survivor is relinked to it."""
    typed, typed_card = pair(created_at=T0)
    bank, bank_card = pair(created_at=T1)
    bank_card = changed(bank_card, cleared="reconciled")

    plan = plan_merge(bank, typed, None, partners_of(typed_card, bank_card))

    assert isinstance(plan, MergePlan)
    assert plan.survivor is typed
    assert plan.partner_merge is not None and plan.partner_merge.survivor is bank_card
    assert plan.survivor_partner is bank_card and plan.relinks


def test_partners_with_different_amounts_are_refused_by_name():
    typed, typed_card = pair()
    bank, bank_card = pair(created_at=T1)
    bank_card = changed(bank_card, amount=Decimal("450.00"))

    plan = plan_merge(bank, typed, None, partners_of(typed_card, bank_card))

    assert isinstance(plan, Refused)
    assert "other account's two legs don't match" in plan.reason
    assert "500.00" in plan.reason and "450.00" in plan.reason


def test_partners_in_different_accounts_are_refused_by_name():
    typed, typed_card = pair()
    bank, bank_card = pair(created_at=T1)
    bank_card = changed(bank_card, account_id=uuid.uuid4())

    plan = plan_merge(bank, typed, None, partners_of(typed_card, bank_card))

    assert isinstance(plan, Refused)
    assert "other account's two legs don't match" in plan.reason
    assert "different accounts" in plan.reason


def test_partners_the_rules_would_not_merge_are_refused_by_name():
    """Both reconciled, or two different bank records: the far pair is held
    to the same rules a direct merge of it would be."""
    typed, typed_card = pair()
    bank, bank_card = pair(created_at=T1)
    for far_typed, far_bank, why in (
        (
            changed(typed_card, cleared="reconciled"),
            changed(bank_card, cleared="reconciled"),
            "two reconciled",
        ),
        (
            changed(typed_card, sync_id="t-card-1", sync_source="simplefin"),
            changed(bank_card, sync_id="t-card-2", sync_source="simplefin"),
            "different bank",
        ),
    ):
        plan = plan_merge(bank, typed, None, partners_of(far_typed, far_bank))
        assert isinstance(plan, Refused), why
        assert "other account's two legs don't match" in plan.reason
        assert why in plan.reason


def test_a_leg_whose_partner_is_gone_is_refused():
    typed, _ = pair()
    plan = plan_merge(typed, side(cleared="reconciled"), None, {})
    assert isinstance(plan, Refused) and "missing" in plan.reason


def test_a_split_cannot_take_a_transfer_over():
    typed, card_leg = pair()
    reconciled_split = side(cleared="reconciled", is_split=True)
    plan = plan_merge(typed, reconciled_split, None, partners_of(card_leg))
    assert isinstance(plan, Refused) and "split cannot take over a transfer" in plan.reason


def test_the_two_legs_of_one_transfer_are_not_duplicates():
    leg, partner = pair()
    plan = plan_merge(leg, partner, None, partners_of(leg, partner))
    assert isinstance(plan, Refused) and "same account" in plan.reason
