"""A duplicate of a transfer leg can be merged, and its transfer goes with it.

The review queue used to refuse these with "Cannot merge away a transfer;
reject the match or delete the transfer instead" — and rejecting left both
rows standing, so the duplicate could not be resolved at all. The shape that
produced it: a $500 card payment typed as a transfer (checking leg A, card
leg B), then a sync that queued the checking-side bank row C as a duplicate
of A and, in the same run, paired C with the card-side bank row D. Two
transfers for one payment, and both rows the review asked to merge were legs.

Amounts are invented: one $500 payment from checking to a Sapphire Visa.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from igab.db.models import ChangeLog, Transaction
from igab.domain.dates import month_start
from igab.domain.exceptions import InvariantViolation
from igab.services.card_payment import ensure_payment_category
from igab.services.simplefin_service import SimpleFINService
from igab.services.transaction_service import TransactionCreate
from igab.services.undo_service import UndoService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_simplefin_connection,
    create_transaction,
    create_user,
    make_services,
)
from .fake_bridge import FakeBridge
from .invariants import assert_financial_invariants, assert_transfer_integrity

TYPED_ON = date.today() - timedelta(days=4)
POSTED_ON = date.today() - timedelta(days=1)
PAYMENT = Decimal("500.00")
SF_CHECKING = "sf-chk"
SF_CARD = "sf-card"


async def _budget(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(
        db_session, budget, "Harborstone Checking", simplefin_account_id=SF_CHECKING
    )
    card = await create_account(
        db_session,
        budget,
        "Sapphire Visa",
        account_type="credit_card",
        simplefin_account_id=SF_CARD,
    )
    await ensure_payment_category(db_session, card)
    # The payment pays for something: $1,000 in, $500 of it assigned to
    # groceries and spent on the card. Without the charge, a payment would
    # pay a card that owes nothing and its envelope would read red.
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income = await create_category(db_session, budget, income_group, "Ready to Assign")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    await create_transaction(db_session, budget, checking, "1000.00", TYPED_ON, category=income)
    await create_budget_assignment(db_session, budget, groceries, month_start(TYPED_ON), PAYMENT)
    await create_transaction(db_session, budget, card, -PAYMENT, TYPED_ON, category=groceries)
    return services, user, budget, checking, card


async def _typed_payment(services, budget, checking, card, amount=PAYMENT):
    """The payment as a person types it: a transfer, both legs uncleared."""
    leg = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TYPED_ON,
            amount=-amount,
            cleared="uncleared",
            transfer_account_id=card.id,
        ),
    )
    partner = await services.transaction_repo.get(leg.transfer_id)
    assert partner is not None
    return leg, partner


async def _bank_row(db_session, budget, account, amount, sync_id, **over):
    kwargs = dict(
        cleared="cleared",
        sync_id=sync_id,
        sync_source="simplefin",
        bank_posted_date=POSTED_ON,
        bank_amount=Decimal(amount),
    )
    kwargs.update(over)
    return await create_transaction(db_session, budget, account, amount, POSTED_ON, **kwargs)


async def _two_transfers_for_one_payment(db_session, services, budget, checking, card):
    """A↔B typed, C↔D the bank's own pair, C queued as A's duplicate and D as
    B's — the state a sync used to build in one run. Built by hand because
    the sync no longer builds it (the last test below); budgets synced
    before that still hold it, and their reviews must be answerable."""
    a, b = await _typed_payment(services, budget, checking, card)
    balances = await _balances(services, checking, card)
    c = await _bank_row(db_session, budget, checking, "-500.00", "t-chk")
    d = await _bank_row(db_session, budget, card, "500.00", "t-card")
    await services.transactions.link_legs(budget.id, c, d)
    match = await services.match_repo.create(
        synced_transaction_id=c.id, manual_transaction_id=a.id, confidence_score=0.7
    )
    card_match = await services.match_repo.create(
        synced_transaction_id=d.id, manual_transaction_id=b.id, confidence_score=0.7
    )
    return a, b, c, d, match, card_match, balances


async def _balances(services, *accounts) -> tuple[Decimal, ...]:
    return tuple([await services.account_repo.get_balance(acct.id) for acct in accounts])


async def _live(db_session, *rows) -> list[Transaction]:
    for row in rows:
        await db_session.refresh(row)
    return [row for row in rows if not row.is_deleted]


async def _live_legs(db_session, budget_id) -> list[Transaction]:
    result = await db_session.execute(
        select(Transaction).where(
            Transaction.budget_id == budget_id,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.transfer_id.isnot(None),
        )
    )
    return list(result.scalars().all())


async def _batch_of(db_session, budget_id, entity_id):
    await db_session.flush()
    rows = (
        (
            await db_session.execute(
                select(ChangeLog)
                .where(ChangeLog.budget_id == budget_id, ChangeLog.entity_id == entity_id)
                .order_by(ChangeLog.seq.desc())
            )
        )
        .scalars()
        .all()
    )
    assert rows, "the merge was recorded"
    return rows[0].batch_id


def _assert_one_pair(legs: list[Transaction], first: Transaction, second: Transaction) -> None:
    assert {leg.id for leg in legs} == {first.id, second.id}, "exactly one transfer remains"
    assert first.transfer_id == second.id and second.transfer_id == first.id


class TestTwoTransfersForOnePayment:
    async def test_a_accepting_the_match_leaves_one_transfer(self, db_session):
        """(a) The typed pair survives on both accounts and takes the bank's
        identity on each; the bank's pair goes. Balances are what they were
        before the duplicate arrived, and the pair still sums to zero."""
        services, _, budget, checking, card = await _budget(db_session)
        a, b, c, d, _, card_match, before = await _two_transfers_for_one_payment(
            db_session, services, budget, checking, card
        )

        survivor = await services.transactions.merge(budget.id, [c.id, a.id])

        assert survivor.id == a.id
        assert await _live(db_session, a, b, c, d) == [a, b]
        _assert_one_pair(await _live_legs(db_session, budget.id), a, b)
        assert (a.sync_id, b.sync_id) == ("t-chk", "t-card"), "both bank identities kept"
        assert a.cleared == "cleared" and b.cleared == "cleared"
        assert a.amount == -b.amount == -PAYMENT
        assert await _balances(services, checking, card) == before
        assert (await services.match_repo.get(card_match.id)).status == "rejected", (
            "the card-side review is moot once its rows are merged"
        )
        await assert_financial_invariants(db_session, budget.id)

    async def test_e_the_review_queue_accept_succeeds(self, db_session):
        """(e) The path the user hit: the duplicate review's accept, not a
        direct merge."""
        services, _, budget, checking, card = await _budget(db_session)
        a, b, c, d, match, _, before = await _two_transfers_for_one_payment(
            db_session, services, budget, checking, card
        )

        await services.matching.accept_match(match.id)

        assert (await services.match_repo.get(match.id)).status == "accepted"
        assert await _live(db_session, a, b, c, d) == [a, b]
        _assert_one_pair(await _live_legs(db_session, budget.id), a, b)
        assert await _balances(services, checking, card) == before
        await assert_financial_invariants(db_session, budget.id)

    async def test_d_undo_restores_all_four_rows_and_both_links(self, db_session):
        """(d) One batch: undo brings back C and D and both transfers."""
        services, _, budget, checking, card = await _budget(db_session)
        a, b, c, d, *_ = await _two_transfers_for_one_payment(
            db_session, services, budget, checking, card
        )
        await services.transactions.merge(budget.id, [c.id, a.id])

        batch_id = await _batch_of(db_session, budget.id, a.id)
        assert batch_id == await _batch_of(db_session, budget.id, b.id), "one undo, both sides"
        await UndoService(db_session).undo_batch(budget.id, batch_id)

        assert await _live(db_session, a, b, c, d) == [a, b, c, d]
        assert (a.transfer_id, b.transfer_id) == (b.id, a.id)
        assert (c.transfer_id, d.transfer_id) == (d.id, c.id)
        assert a.sync_id is None and b.sync_id is None, "the bank identity goes back too"
        assert a.cleared == "uncleared" and b.cleared == "uncleared"
        # Two payments for one charge again — the duplicate, back as it was —
        # so only the transfer rules hold, not the budget's.
        await assert_transfer_integrity(db_session)

    async def test_a_reconciled_card_leg_is_kept_and_relinked(self, db_session):
        """Each account's pair is merged by the precedence: the card's
        reconciled bank leg outranks the typed one, so the checking survivor
        is relinked to it."""
        services, _, budget, checking, card = await _budget(db_session)
        a, b, c, d, *_ = await _two_transfers_for_one_payment(
            db_session, services, budget, checking, card
        )
        d.cleared = "reconciled"
        await db_session.flush()

        await services.transactions.merge(budget.id, [c.id, a.id])

        assert await _live(db_session, a, b, c, d) == [a, d]
        _assert_one_pair(await _live_legs(db_session, budget.id), a, d)
        payee = await services.payee_repo.get(a.payee_id)
        assert payee.transfer_account_id == card.id
        await assert_financial_invariants(db_session, budget.id)

    async def test_c_legs_for_different_amounts_are_refused_by_name(self, db_session):
        """(c) The payment typed as $450; the bank's pair says $500. Merging
        would claim two different movements are one. Nothing changes."""
        services, _, budget, checking, card = await _budget(db_session)
        a, b = await _typed_payment(services, budget, checking, card, amount=Decimal("450.00"))
        c = await _bank_row(db_session, budget, checking, "-500.00", "t-chk")
        d = await _bank_row(db_session, budget, card, "500.00", "t-card")
        await services.transactions.link_legs(budget.id, c, d)

        with pytest.raises(InvariantViolation, match="other account's two legs don't match"):
            await services.transactions.merge(budget.id, [c.id, a.id])

        assert await _live(db_session, a, b, c, d) == [a, b, c, d]
        assert (a.transfer_id, c.transfer_id) == (b.id, d.id)
        await assert_transfer_integrity(db_session)


class TestALegMergedIntoAPlainRow:
    async def test_b_the_reconciled_row_becomes_the_leg(self, db_session):
        """(b) The statement row was reconciled before anyone saw it was the
        typed payment. It survives, takes the transfer over — payee naming
        the card, partner re-pointed — and the category a card payment may
        not carry goes."""
        services, _, budget, checking, card = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Irregular")
        misc = await create_category(db_session, budget, group, "Misc")
        a, b = await _typed_payment(services, budget, checking, card)
        before = await _balances(services, checking, card)
        statement = await _bank_row(
            db_session, budget, checking, "-500.00", "t-chk", cleared="reconciled", category=misc
        )

        survivor = await services.transactions.merge(budget.id, [a.id, statement.id])

        assert survivor.id == statement.id
        assert await _live(db_session, a, b, statement) == [b, statement]
        _assert_one_pair(await _live_legs(db_session, budget.id), statement, b)
        assert statement.cleared == "reconciled" and statement.amount == -PAYMENT
        payee = await services.payee_repo.get(statement.payee_id)
        assert payee.transfer_account_id == card.id
        assert statement.category_id is None, "an on-budget card payment is not spending"
        assert await _balances(services, checking, card) == before, "one payment, counted once"
        await assert_financial_invariants(db_session, budget.id)

    async def test_b_undo_puts_the_plain_row_and_the_link_back(self, db_session):
        services, _, budget, checking, card = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Irregular")
        misc = await create_category(db_session, budget, group, "Misc")
        a, b = await _typed_payment(services, budget, checking, card)
        statement = await _bank_row(
            db_session, budget, checking, "-500.00", "t-chk", cleared="reconciled", category=misc
        )
        payee_before = statement.payee_id
        await services.transactions.merge(budget.id, [a.id, statement.id])

        batch_id = await _batch_of(db_session, budget.id, statement.id)
        await UndoService(db_session).undo_batch(budget.id, batch_id)

        assert await _live(db_session, a, b, statement) == [a, b, statement]
        assert (a.transfer_id, b.transfer_id) == (b.id, a.id)
        assert statement.transfer_id is None and statement.category_id == misc.id
        assert statement.payee_id == payee_before
        await assert_transfer_integrity(db_session)

    async def test_a_reconciled_row_for_a_different_amount_is_refused(self, db_session):
        """A reconciled amount cannot move, so the bank-posting rule drops the
        bank leg's amount instead of refusing — and the reconciled row would
        become a $500 leg of a $450 transfer."""
        services, _, budget, checking, card = await _budget(db_session)
        c = await _bank_row(db_session, budget, checking, "-450.00", "t-chk")
        d = await _bank_row(db_session, budget, card, "450.00", "t-card")
        await services.transactions.link_legs(budget.id, c, d)
        statement = await create_transaction(
            db_session, budget, checking, "-500.00", POSTED_ON, cleared="reconciled"
        )

        with pytest.raises(InvariantViolation, match="The transfer is 450.00"):
            await services.transactions.merge(budget.id, [c.id, statement.id])

        assert await _live(db_session, c, d, statement) == [c, d, statement]
        assert statement.transfer_id is None and c.transfer_id == d.id


# ─── The sync never builds the double-leg state ─────────────────────────────


def _feed_row(account_id: str, txn_id: str, amount: str, payee: str) -> dict:
    posted = datetime(POSTED_ON.year, POSTED_ON.month, POSTED_ON.day, 12, tzinfo=UTC)
    return {
        "account_id": account_id,
        "id": txn_id,
        "amount": amount,
        "payee": payee,
        "description": f"{payee} ONLINE",
        "posted": int(posted.timestamp()),
    }


async def test_a_sync_does_not_pair_bank_rows_queued_against_a_typed_transfer(db_session):
    """The prevention. Both bank rows are queued as duplicates of the typed
    legs, so the pairing pass leaves them alone; accepting each review then
    folds it into the typed transfer, and one transfer remains."""
    services, user, budget, checking, card = await _budget(db_session)
    conn = await create_simplefin_connection(db_session, user)
    a, b = await _typed_payment(services, budget, checking, card)
    before = await _balances(services, checking, card)

    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = FakeBridge(
        [
            _feed_row(SF_CHECKING, "t-chk", "-500.00", "SAPPHIRE VISA AUTOPAY"),
            _feed_row(SF_CARD, "t-card", "500.00", "PAYMENT THANK YOU"),
        ]
    )
    with patch("igab.services.simplefin_service.decrypt", return_value="https://u:p@x.test"):
        result = await svc.sync(conn.id, budget.id)

    assert result["review_queued"] == 2, "each bank row is asked about, not guessed"
    assert result["paired"] == 0, "a row awaiting review as a leg's duplicate is not pairable"
    assert {leg.id for leg in await _live_legs(db_session, budget.id)} == {a.id, b.id}

    for match in await services.match_repo.get_pending_for_budget(budget.id):
        await services.matching.accept_match(match.id)

    await db_session.refresh(a)
    await db_session.refresh(b)
    _assert_one_pair(await _live_legs(db_session, budget.id), a, b)
    assert (a.sync_id, b.sync_id) == ("t-chk", "t-card")
    assert await _balances(services, checking, card) == before
    await assert_financial_invariants(db_session, budget.id)
