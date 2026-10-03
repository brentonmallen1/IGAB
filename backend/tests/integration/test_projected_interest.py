"""Projected interest rows, against a real ledger.

A loan payment posts as a transfer of the whole amount into the loan; the
lender's interest is a separate payee-less outflow on the loan that nothing
used to write, so the register and the loan's balance ran one month of
interest low. The app now writes that row from the terms on file and
retires it when the lender's own row arrives. The rule is
`domain.projected_interest` (unit-tested in test_domain_projected_interest);
this file holds the wiring to it: every write path that can move a payment
or an interest row, the undo stack, and every place the row is served.

Fictional and round throughout: Harborstone Mortgage, 24,000.00 owed at
6%, so a month costs 120.00 and a 500.00 payment leaves 23,620.00.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import Account, ChangeLog, Liability, Transaction
from igab.domain.dates import add_months, month_start
from igab.domain.exceptions import UndoConflict
from igab.domain.payee_names import STARTING_BALANCE_PAYEE
from igab.domain.projected_interest import PROJECTION_MEMO, PROJECTION_ORIGIN
from igab.repositories.liability_repo import LiabilityRepository
from igab.services.liability_service import LiabilityService
from igab.services.transaction_service import TransactionCreate, TransactionUpdate
from igab.services.undo_service import UndoService
from igab.utils.clock import today_utc

from .factories import (
    create_account,
    create_budget,
    create_liability,
    create_payee,
    create_transaction,
    create_user,
    make_services,
    money,
)

TODAY = today_utc()
THIS = month_start(TODAY)
LAST = add_months(THIS, -1)
#: A day in last month that is never the 1st, so a re-date within it moves.
LAST_MID = LAST + timedelta(days=14)


@dataclass
class Mortgage:
    services: object
    user: object
    budget: object
    checking: Account
    loan: Account
    liability: Liability
    opening_payee: object

    @property
    def txns(self):
        return self.services.transactions  # type: ignore[attr-defined]


async def _mortgage(db_session, *, rate: str | None = "6", user=None) -> Mortgage:
    services = make_services(db_session)
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    loan = await create_account(
        db_session, budget, "Harborstone Mortgage", account_type="mortgage", on_budget=False
    )
    opening = await create_payee(db_session, budget, STARTING_BALANCE_PAYEE)
    await create_transaction(
        db_session, budget, loan, Decimal("-24000.00"), add_months(THIS, -6), payee=opening
    )
    liability = await create_liability(
        db_session,
        budget,
        "Harborstone Mortgage",
        linked_account_id=loan.id,
        interest_rate=Decimal(rate) if rate is not None else None,
    )
    return Mortgage(services, user, budget, checking, loan, liability, opening)


async def _pay(m: Mortgage, on, amount: str = "500.00", into: Account | None = None):
    """A payment from checking into the loan; returns the loan's leg."""
    out = await m.txns.create(
        m.budget.id,
        TransactionCreate(
            account_id=m.checking.id,
            date=on,
            amount=Decimal(amount),
            transfer_account_id=(into or m.loan).id,
        ),
    )
    leg = await m.services.transaction_repo.get(out.transfer_id)  # type: ignore[attr-defined]
    assert leg is not None
    return leg


async def _rows(db_session, account_id, *, deleted: bool | None = False) -> list[Transaction]:
    await db_session.flush()
    stmt = select(Transaction).where(Transaction.account_id == account_id)
    if deleted is not None:
        stmt = stmt.where(Transaction.is_deleted == deleted)
    return list((await db_session.execute(stmt.order_by(Transaction.date))).scalars().all())


async def _projections(db_session, account_id) -> list[Transaction]:
    return [
        r for r in await _rows(db_session, account_id) if r.projected_interest_month is not None
    ]


async def _only_projection(db_session, account_id) -> Transaction:
    rows = await _projections(db_session, account_id)
    assert len(rows) == 1, rows
    return rows[0]


async def _balance(m: Mortgage) -> Decimal:
    return money(await m.services.account_repo.get_balance(m.loan.id))  # type: ignore[attr-defined]


async def _cleared_balance(m: Mortgage) -> Decimal:
    return money(
        await m.services.account_repo.get_cleared_balance(m.loan.id)  # type: ignore[attr-defined]
    )


async def _lender_row(m: Mortgage, on, amount: str = "-120.00", **kwargs) -> Transaction:
    return await m.txns.create(
        m.budget.id,
        TransactionCreate(account_id=m.loan.id, date=on, amount=Decimal(amount), **kwargs),
    )


async def _cmd_z(db_session, budget_id):
    """⌘Z. Flushed first: the session runs autoflush=False (production
    commits at request end), and undo selects its candidate by query."""
    await db_session.flush()
    return await UndoService(db_session).undo_latest(budget_id)


async def _redo(db_session, budget_id):
    await db_session.flush()
    return await UndoService(db_session).redo_latest(budget_id)


async def _record_of(db_session, entity_id) -> ChangeLog:
    """The create record of a row the test wrote."""
    await db_session.flush()
    return (
        await db_session.execute(
            select(ChangeLog).where(ChangeLog.entity_id == entity_id, ChangeLog.action == "create")
        )
    ).scalar_one()


def _liability_service(db_session) -> LiabilityService:
    services = make_services(db_session)
    return LiabilityService(
        LiabilityRepository(db_session),
        services.account_repo,
        services.category_repo,
        services.transaction_repo,
    )


# ─── Creation ────────────────────────────────────────────────────────────────


async def test_a_payment_writes_the_months_projected_interest(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)

    row = await _only_projection(db_session, m.loan.id)
    assert money(row.amount) == Decimal("-120.00"), "6% of 24,000 over 12"
    assert row.date == THIS, "dated on the month's first payment"
    assert row.projected_interest_month == THIS
    assert row.cleared == "uncleared"
    assert row.payee_id is None and row.category_id is None
    assert row.approved is True
    assert row.created_via == PROJECTION_ORIGIN
    assert row.memo == PROJECTION_MEMO


async def test_the_projection_counts_in_the_balance_and_not_the_cleared_balance(db_session):
    """Uncleared: in the working balance and net worth like any entered row,
    out of everything that means "the bank agrees"."""
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    assert await _balance(m) == Decimal("-23620.00")
    # The opening is cleared; the payment leg is uncleared as the service
    # writes it, and the projection must not be in the cleared figure either.
    assert await _cleared_balance(m) == Decimal("-24000.00")


async def test_the_payment_and_its_projection_share_one_batch_as_system(db_session):
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    row = await _only_projection(db_session, m.loan.id)
    await db_session.flush()
    records = {
        c.entity_id: c
        for c in (
            await db_session.execute(select(ChangeLog).where(ChangeLog.budget_id == m.budget.id))
        ).scalars()
    }
    assert records[row.id].source == "system"
    assert records[row.id].action == "create"
    assert records[row.id].batch_id == records[leg.id].batch_id is not None


async def test_the_estimate_steps_aside_for_the_projection(db_session):
    """No double count: the projection IS this month's charge as far as the
    ledger knows, so the liability page claims no estimate on top of it —
    and the modelled figure and the row are one number."""
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    status = await _liability_service(db_session).get_status(m.liability)
    assert status.current_balance == Decimal("23620.00")
    assert status.estimated_interest_this_month is None
    assert status.balance_with_estimate == Decimal("23620.00")
    assert status.modelled_interest_this_month == Decimal("120.00")
    assert status.projected_interest_this_month == Decimal("120.00")


async def test_no_payment_no_projection(db_session):
    m = await _mortgage(db_session)
    await _lender_row(m, THIS, "-35.00", memo="late fee")
    assert await _projections(db_session, m.loan.id) == []


# ─── Replacement by the lender's own row ─────────────────────────────────────


async def test_a_typed_lender_row_retires_the_projection(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)

    await _lender_row(m, THIS + timedelta(days=1), "-121.37")

    await db_session.refresh(projection)
    assert projection.is_deleted is True
    assert projection.projected_interest_month is None, "a retire is never a tombstone"
    assert await _projections(db_session, m.loan.id) == []
    assert await _balance(m) == Decimal("-24000.00") + Decimal("500.00") - Decimal("121.37")


async def test_a_retire_is_recorded_as_one_system_delete_in_the_lenders_batch(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    lender = await _lender_row(m, THIS, "-120.00")
    await db_session.flush()
    rows = (
        (
            await db_session.execute(
                select(ChangeLog)
                .where(ChangeLog.entity_id == projection.id)
                .order_by(ChangeLog.seq)
            )
        )
        .scalars()
        .all()
    )
    assert [c.action for c in rows] == ["create", "delete"]
    retire = rows[1]
    assert retire.source == "system"
    assert (retire.before or {})["projected_interest_month"] == THIS.isoformat()
    lender_record = await _record_of(db_session, lender.id)
    assert retire.batch_id == lender_record.batch_id is not None, "one undo unit"


async def test_a_lender_row_of_equal_cents_is_never_matched_onto_the_projection(db_session):
    """The match ladder must not absorb the lender's row into the app's
    guess: with equal cents on the same day, every candidate query that
    starts from MATCHABLE_ROW would otherwise offer the projection, and a
    match would leave the projection standing as if it were real."""
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    repo = m.services.transaction_repo  # type: ignore[attr-defined]
    assert await repo.find_existing_match_candidates(m.loan.id, Decimal("-120.00"), THIS) == []
    assert (
        await repo.find_existing_match_candidates(
            m.loan.id, Decimal("-120.00"), THIS, any_bank_state=True
        )
        == []
    )
    assert await repo.find_match_candidates(m.loan.id, Decimal("-120.00"), THIS) == []
    assert await repo.find_similar_transactions(m.loan.id, Decimal("-120.00"), THIS) == []
    await _lender_row(m, THIS, "-120.00")
    assert await repo.find_duplicate_candidate_pairs(m.loan.id) == []


async def test_a_synced_lender_row_of_equal_cents_replaces_the_projection(db_session):
    """End to end through the bank sync: the feed's interest row is written
    as its own row (never matched onto the projection), and the projection
    is retired in the run's batch."""
    from .test_simplefin_sync import PATCH_DECRYPT, SF_ACCT, _service, bank_txn

    m = await _mortgage(db_session)
    m.loan.simplefin_account_id = SF_ACCT
    m.loan.first_sync_complete = True
    await db_session.flush()
    from .factories import create_simplefin_connection

    conn = await create_simplefin_connection(db_session, m.user)  # type: ignore[arg-type]
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)

    svc = _service(m.services, [bank_txn("int-1", "-120.00", THIS, payee="INTEREST")])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, m.budget.id)

    live = await _rows(db_session, m.loan.id)
    synced = [r for r in live if r.sync_id == "int-1"]
    assert len(synced) == 1, ("the lender's row is its own row", result)
    assert synced[0].id != projection.id
    await db_session.refresh(projection)
    assert projection.is_deleted is True and projection.projected_interest_month is None
    assert await _balance(m) == Decimal("-23620.00"), "the interest counted once"


async def test_a_csv_lender_row_replaces_the_projection_in_the_imports_batch(db_session):
    from igab.domain.csv_import import ParsedRow
    from igab.services.csv_import import apply_csv_plan, plan_csv_import

    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)

    rows = [
        ParsedRow(line=1, date=THIS, amount=Decimal("-120.00"), payee="", memo=None, category=None)
    ]
    plans = await plan_csv_import(m.services.transaction_repo, m.budget.id, m.loan.id, rows)  # type: ignore[attr-defined]
    assert [p.outcome for p in plans] == ["new"], "never matched onto the projection"
    counts = await apply_csv_plan(m.txns, m.budget.id, m.loan.id, plans)
    await db_session.flush()

    await db_session.refresh(projection)
    assert projection.is_deleted is True
    assert await _balance(m) == Decimal("-23620.00")

    # Undoing the import takes back the row AND the replacement it caused.
    assert counts.batch_id is not None
    await UndoService(db_session).undo_batch(m.budget.id, counts.batch_id)
    await db_session.refresh(projection)
    assert projection.is_deleted is False
    assert projection.projected_interest_month == THIS
    assert await _balance(m) == Decimal("-23620.00")


async def test_a_pending_lender_row_waits_and_its_posting_retires_the_projection(db_session):
    from igab.domain.bank_posting import FeedRecord

    m = await _mortgage(db_session)
    await _pay(m, THIS)
    pending = await _lender_row(
        m, THIS, "-120.00", cleared="pending", sync_id="p-1", sync_source="simplefin"
    )
    assert len(await _projections(db_session, m.loan.id)) == 1, "a pending row is not money yet"

    await m.txns.apply_bank_posting(
        pending,
        FeedRecord(
            amount=Decimal("-120.00"),
            date=THIS,
            posted=True,
            payee="INTEREST",
            description="INTEREST",
            sync_id="p-1",
        ),
        confirmed=False,
    )
    assert await _projections(db_session, m.loan.id) == []
    assert await _balance(m) == Decimal("-23620.00")


# ─── The payment moves ───────────────────────────────────────────────────────


async def test_deleting_the_payment_retires_its_projection(db_session):
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    await m.txns.delete(m.budget.id, leg.id)
    await db_session.refresh(projection)
    assert projection.is_deleted is True and projection.projected_interest_month is None
    assert await _balance(m) == Decimal("-24000.00")


async def test_re_dating_the_payment_within_the_month_re_dates_the_projection(db_session):
    m = await _mortgage(db_session)
    leg = await _pay(m, LAST)
    await m.txns.update(m.budget.id, leg.id, TransactionUpdate(date=LAST_MID))
    row = await _only_projection(db_session, m.loan.id)
    assert row.date == LAST_MID and row.projected_interest_month == LAST


async def test_re_dating_the_payment_into_another_month_moves_the_projection(db_session):
    m = await _mortgage(db_session)
    leg = await _pay(m, LAST_MID)
    first = await _only_projection(db_session, m.loan.id)
    assert first.projected_interest_month == LAST

    await m.txns.update(m.budget.id, leg.id, TransactionUpdate(date=THIS))

    row = await _only_projection(db_session, m.loan.id)
    assert row.projected_interest_month == THIS and row.date == THIS
    await db_session.refresh(first)
    assert first.is_deleted is True and first.projected_interest_month is None
    # This month opens owing 24,000 again (the payment left last month).
    assert money(row.amount) == Decimal("-120.00")


async def test_moving_the_payment_to_another_loan_moves_the_projection(db_session):
    m = await _mortgage(db_session)
    other = await create_account(
        db_session, m.budget, "Northwind Auto Loan", account_type="auto_loan", on_budget=False
    )
    await create_transaction(
        db_session,
        m.budget,
        other,
        Decimal("-12000.00"),
        add_months(THIS, -6),
        payee=m.opening_payee,  # type: ignore[arg-type]
    )
    await create_liability(
        db_session,
        m.budget,
        "Northwind Auto Loan",
        linked_account_id=other.id,
        interest_rate=Decimal("12"),
    )
    leg = await _pay(m, THIS)
    first = await _only_projection(db_session, m.loan.id)

    await m.txns.update(m.budget.id, leg.id, TransactionUpdate(account_id=other.id))

    await db_session.refresh(first)
    assert first.is_deleted is True
    assert await _projections(db_session, m.loan.id) == []
    moved = await _only_projection(db_session, other.id)
    assert moved.projected_interest_month == THIS
    # Sized on the auto loan's own terms: 12% on 12,000 is 120.00.
    assert money(moved.amount) == Decimal("-120.00")


# ─── Month to month ──────────────────────────────────────────────────────────


async def test_each_month_is_sized_on_the_close_before_it_including_its_projection(db_session):
    """Last month: 120.00 on 24,000. This month opens owing
    24,000 - 500 + 120 = 23,620, which costs 118.10."""
    m = await _mortgage(db_session)
    await _pay(m, LAST_MID)
    await _pay(m, THIS)
    by_month = {
        r.projected_interest_month: money(r.amount)
        for r in await _projections(db_session, m.loan.id)
    }
    assert by_month == {LAST: Decimal("-120.00"), THIS: Decimal("-118.10")}
    assert await _balance(m) == Decimal("-24000.00") + Decimal("1000.00") - Decimal("238.10")


async def test_editing_last_months_payment_resizes_this_months_projection(db_session):
    m = await _mortgage(db_session)
    last = await _pay(m, LAST_MID)
    await _pay(m, THIS)
    await m.txns.update(m.budget.id, last.id, TransactionUpdate(amount=Decimal("1500.00")))
    by_month = {
        r.projected_interest_month: money(r.amount)
        for r in await _projections(db_session, m.loan.id)
    }
    # 24,000 - 1,500 + 120 = 22,620 → 113.10.
    assert by_month == {LAST: Decimal("-120.00"), THIS: Decimal("-113.10")}


async def test_no_projection_is_created_before_last_month(db_session):
    m = await _mortgage(db_session)
    await _pay(m, add_months(THIS, -2) + timedelta(days=9))
    assert await _projections(db_session, m.loan.id) == []


async def test_an_old_projection_is_still_kept_in_step(db_session):
    """Update and Retire are never limited by the creation window: the app's
    own row two months back is corrected when its payment changes."""
    m = await _mortgage(db_session)
    leg = await _pay(m, add_months(THIS, -2) + timedelta(days=9))
    old = Transaction(
        budget_id=m.budget.id,
        account_id=m.loan.id,
        date=leg.date,
        amount=Decimal("-99.00"),
        cleared="uncleared",
        approved=True,
        created_via=PROJECTION_ORIGIN,
        memo=PROJECTION_MEMO,
        projected_interest_month=month_start(leg.date),
    )
    db_session.add(old)
    await db_session.flush()
    await m.txns.update(m.budget.id, leg.id, TransactionUpdate(memo="statement 7"))
    # A memo edit is still a write to the month: the stale row is resized.
    await db_session.refresh(old)
    assert money(old.amount) == Decimal("-120.00")
    await m.txns.delete(m.budget.id, leg.id)
    await db_session.refresh(old)
    assert old.is_deleted is True


async def test_an_auto_posted_scheduled_payment_projects_interest(db_session):
    from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
    from igab.services.scheduled_transaction_service import ScheduledTransactionService

    from .factories import create_scheduled_transaction

    m = await _mortgage(db_session)
    sched = await create_scheduled_transaction(
        db_session, m.budget, m.checking, "-500.00", "monthly", TODAY
    )
    sched.transfer_account_id = m.loan.id
    await db_session.flush()

    svc = ScheduledTransactionService(ScheduledTransactionRepository(db_session), m.txns)
    created = await svc.process_due(m.budget.id, TODAY)
    assert created, "the schedule posted"
    row = await _only_projection(db_session, m.loan.id)
    assert row.date == TODAY and money(row.amount) == Decimal("-120.00")


# ─── Terms ───────────────────────────────────────────────────────────────────


async def test_no_terms_no_projection(db_session):
    m = await _mortgage(db_session, rate=None)
    await _pay(m, THIS)
    assert await _projections(db_session, m.loan.id) == []


async def test_filling_in_the_terms_projects_and_clearing_them_retires(api_client, db_session):
    m = await _mortgage(db_session, rate=None, user=api_client.test_user)
    await _pay(m, THIS)
    assert await _projections(db_session, m.loan.id) == []

    url = f"/api/v1/{m.budget.id}/liabilities/{m.liability.id}"
    resp = await api_client.patch(url, json={"interest_rate": "6"})
    assert resp.status_code == 200, resp.text
    assert money(resp.json()["projected_interest_this_month"]) == Decimal("120.00")
    assert resp.json()["estimated_interest_this_month"] is None, "no double count"
    projection = await _only_projection(db_session, m.loan.id)

    resp = await api_client.patch(url, json={"interest_rate": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["projected_interest_this_month"] is None
    await db_session.refresh(projection)
    assert projection.is_deleted is True and projection.projected_interest_month is None


async def test_undoing_the_terms_change_takes_its_projection_back(api_client, db_session):
    m = await _mortgage(db_session, rate=None, user=api_client.test_user)
    await _pay(m, THIS)
    resp = await api_client.patch(
        f"/api/v1/{m.budget.id}/liabilities/{m.liability.id}", json={"interest_rate": "6"}
    )
    assert resp.status_code == 200
    projection = await _only_projection(db_session, m.loan.id)

    await _cmd_z(db_session, m.budget.id)
    await db_session.refresh(projection)
    assert projection.is_deleted is True
    assert projection.projected_interest_month is None, "not left as a declined month"


async def test_a_promo_month_projects_nothing(db_session):
    m = await _mortgage(db_session)
    m.liability.promo_end_date = add_months(THIS, 3)
    await db_session.flush()
    await _pay(m, THIS)
    assert await _projections(db_session, m.loan.id) == []


async def test_no_projection_on_an_on_budget_card(db_session):
    """Cards are budgeted by the card model; their interest is the issuer's
    statement charge, never a loan's accrual."""
    m = await _mortgage(db_session)
    card = await create_account(db_session, m.budget, "Sapphire Visa", account_type="credit_card")
    await create_transaction(db_session, m.budget, card, Decimal("-2690.00"), add_months(THIS, -3))
    await create_liability(
        db_session,
        m.budget,
        "Sapphire Visa",
        linked_account_id=card.id,
        interest_rate=Decimal("24"),
    )
    await _pay(m, THIS, into=card)
    assert await _projections(db_session, card.id) == []


# ─── Declining and adopting ──────────────────────────────────────────────────


async def test_deleting_a_projection_declines_the_month_for_good(db_session):
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)

    await m.txns.delete(m.budget.id, projection.id)
    await db_session.refresh(projection)
    assert projection.is_deleted is True
    assert projection.projected_interest_month == THIS, "a tombstone keeps its month"

    # Another write to the month does not bring it back.
    await m.txns.update(m.budget.id, leg.id, TransactionUpdate(memo="statement 7"))
    await _pay(m, THIS, "250.00")
    assert await _projections(db_session, m.loan.id) == []
    assert await _balance(m) == Decimal("-24000.00") + Decimal("750.00")


async def test_undoing_a_decline_restores_the_projection(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    await m.txns.delete(m.budget.id, projection.id)

    await _cmd_z(db_session, m.budget.id)
    await db_session.refresh(projection)
    assert projection.is_deleted is False
    assert projection.projected_interest_month == THIS
    assert await _balance(m) == Decimal("-23620.00")


async def test_clearing_a_projection_adopts_it(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)

    await m.txns.update(m.budget.id, projection.id, TransactionUpdate(cleared="cleared"))

    await db_session.refresh(projection)
    assert projection.is_deleted is False
    assert projection.projected_interest_month is None, "the person's row now"
    assert await _projections(db_session, m.loan.id) == [], "and nothing re-projected beside it"
    assert await _balance(m) == Decimal("-23620.00")


async def test_editing_a_projections_amount_adopts_it(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    await m.txns.update(m.budget.id, projection.id, TransactionUpdate(amount=Decimal("-121.37")))
    await db_session.refresh(projection)
    assert projection.projected_interest_month is None
    assert money(projection.amount) == Decimal("-121.37"), "never re-sized out from under them"
    assert await _projections(db_session, m.loan.id) == []


async def test_a_memo_edit_leaves_it_a_projection(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    await m.txns.update(
        m.budget.id,
        projection.id,
        # The editor sends every field it shows; unchanged ones adopt nothing.
        TransactionUpdate(
            memo="statement 7",
            amount=projection.amount,
            date=projection.date,
            cleared="uncleared",
            account_id=m.loan.id,
        ),
    )
    await db_session.refresh(projection)
    assert projection.projected_interest_month == THIS


async def test_reconciling_the_loan_never_touches_the_projection(db_session):
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    await m.txns.update(m.budget.id, leg.id, TransactionUpdate(cleared="cleared"))
    projection = await _only_projection(db_session, m.loan.id)
    status = await m.services.reconciliation.get_status(m.loan.id)  # type: ignore[attr-defined]
    await m.services.reconciliation.finish(m.loan.id, status["cleared_balance"])  # type: ignore[attr-defined]

    await db_session.refresh(projection)
    assert projection.cleared == "uncleared"
    assert projection.projected_interest_month == THIS
    assert projection.is_deleted is False


# ─── Undo ────────────────────────────────────────────────────────────────────


async def test_cmd_z_of_the_payment_takes_its_projection_too(db_session):
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)

    await _cmd_z(db_session, m.budget.id)

    await db_session.refresh(leg)
    await db_session.refresh(projection)
    assert leg.is_deleted is True
    assert projection.is_deleted is True
    assert projection.projected_interest_month is None, "undo is not a decline"
    assert await _balance(m) == Decimal("-24000.00")

    # So the next payment in the month is projected again.
    await _pay(m, THIS)
    assert len(await _projections(db_session, m.loan.id)) == 1


async def test_cmd_z_after_replacement_unwinds_in_order(db_session):
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    lender = await _lender_row(m, THIS, "-121.37")
    await _cmd_z(db_session, m.budget.id)  # the lender row, and its retire
    await db_session.refresh(projection)
    await db_session.refresh(lender)
    assert lender.is_deleted is True
    assert projection.is_deleted is False and projection.projected_interest_month == THIS
    assert await _balance(m) == Decimal("-23620.00")

    await _cmd_z(db_session, m.budget.id)  # the payment, and its projection
    await db_session.refresh(leg)
    await db_session.refresh(projection)
    assert leg.is_deleted is True and projection.is_deleted is True
    assert await _balance(m) == Decimal("-24000.00")


async def test_undoing_the_payment_after_replacement_never_jams(db_session):
    """The Activity page can reach the payment's batch while the lender's
    row still stands. Its projection is already gone — retired by the
    replacement — so taking back its create is a no-op, not a refusal."""
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    await _lender_row(m, THIS, "-121.37")
    record = await _record_of(db_session, leg.id)

    await UndoService(db_session).undo_change(m.budget.id, record.id)

    await db_session.refresh(leg)
    assert leg.is_deleted is True
    assert await _balance(m) == Decimal("-24000.00") - Decimal("121.37")


async def test_undoing_the_payment_after_a_resize_never_jams(db_session):
    """A later settle re-sized the projection (last month's payment changed).
    That is the app's bookkeeping, not the person's edit: undoing the payment
    that created it still takes it back."""
    m = await _mortgage(db_session)
    last = await _pay(m, LAST_MID)
    this_leg = await _pay(m, THIS)
    this_record = await _record_of(db_session, this_leg.id)
    # Resize this month's projection out from under its create record.
    await m.txns.update(m.budget.id, last.id, TransactionUpdate(amount=Decimal("1500.00")))

    await UndoService(db_session).undo_change(m.budget.id, this_record.id)
    projections = await _projections(db_session, m.loan.id)
    assert [p.projected_interest_month for p in projections] == [LAST]


async def test_an_adopted_projection_is_not_taken_by_undoing_the_payment(db_session):
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    await m.txns.update(m.budget.id, projection.id, TransactionUpdate(amount=Decimal("-121.37")))
    record = await _record_of(db_session, leg.id)
    with pytest.raises(UndoConflict):
        await UndoService(db_session).undo_change(m.budget.id, record.id)


async def test_redo_puts_the_payment_and_its_projection_back(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    await _cmd_z(db_session, m.budget.id)
    await _redo(db_session, m.budget.id)
    await db_session.refresh(projection)
    assert projection.is_deleted is False
    assert projection.projected_interest_month == THIS, "back as a projection"
    assert await _balance(m) == Decimal("-23620.00")


async def test_redo_of_a_replacement_replays_a_retire_not_a_decline(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    await _lender_row(m, THIS, "-121.37")
    await _cmd_z(db_session, m.budget.id)
    await _redo(db_session, m.budget.id)
    await db_session.refresh(projection)
    assert projection.is_deleted is True
    assert projection.projected_interest_month is None, "a replayed retire is not a tombstone"


async def test_known_gap_out_of_order_undo_leaves_a_projection_without_its_payment(
    db_session,
):
    """KNOWN GAP, pinned. Undo replays the log; it never re-plans.

    The Activity page can undo the payment's batch while its replacement
    stands (its projection is already gone, so that half is a no-op), and
    then the replacement — which puts the retired projection back, beside a
    payment that no longer exists. The month then carries 120.00 of interest
    with no payment until the next write to the account settles it. Bounded
    to that one projection, and healed by any write — shown last. ⌘Z alone
    (strict LIFO) can never reach this order.
    """
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    await _lender_row(m, THIS, "-120.00")
    payment_record = await _record_of(db_session, leg.id)
    undo = UndoService(db_session)

    await undo.undo_change(m.budget.id, payment_record.id)
    await _cmd_z(db_session, m.budget.id)  # the lender row, and its retire
    assert len(await _projections(db_session, m.loan.id)) == 1
    assert await _balance(m) == Decimal("-24120.00"), "the gap: interest with no payment"

    # The next write to the account heals it.
    await _lender_row(m, THIS, "-5.00", memo="late fee")
    assert await _projections(db_session, m.loan.id) == []
    assert await _balance(m) == Decimal("-24005.00")


async def test_redo_never_replays_a_payment_past_its_replacement(db_session):
    """Why the out-of-order gap above stops at undo: redo refuses a batch
    while anything newer is live, so the payment cannot be redone — and its
    projection resurrected — over the lender's row that replaced it."""
    m = await _mortgage(db_session)
    leg = await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    await _lender_row(m, THIS, "-120.00")
    payment_record = await _record_of(db_session, leg.id)
    undo = UndoService(db_session)
    await undo.undo_change(m.budget.id, payment_record.id)

    with pytest.raises(UndoConflict, match="changed since"):
        await _redo(db_session, m.budget.id)
    await db_session.refresh(projection)
    assert projection.is_deleted is True
    # The lender's row stands, the payment does not: nothing counted twice.
    assert await _balance(m) == Decimal("-24120.00")


async def test_a_sync_runs_undo_takes_back_the_replacement_it_caused(db_session):
    """The sync log's undo (lenient, per row) reverses the run: the lender's
    row goes, and the projection it retired comes back."""
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    with m.txns.changes.batch() as run_batch:
        await _lender_row(m, THIS, "-120.00", sync_id="int-9", sync_source="simplefin")
    await db_session.refresh(projection)
    assert projection.is_deleted is True

    await db_session.flush()
    result = await UndoService(db_session).undo_batch_leniently(m.budget.id, run_batch)
    assert result.skipped == []
    await db_session.refresh(projection)
    assert projection.is_deleted is False and projection.projected_interest_month == THIS
    assert await _balance(m) == Decimal("-23620.00")


# ─── Known limit ─────────────────────────────────────────────────────────────


async def test_known_limit_a_lender_posting_on_the_first_of_next_month(db_session):
    """KNOWN LIMIT, pinned (`domain.projected_interest`). Interest for last
    month posted on the 1st of this month lands in this month's model: last
    month keeps its projection, and this month — now holding a lender row —
    gets none. Last month's interest is then in the balance twice until the
    person deletes the projection, which declines that month."""
    m = await _mortgage(db_session)
    await _pay(m, LAST_MID)
    await _lender_row(m, THIS, "-120.00")
    await _pay(m, THIS)
    months = [p.projected_interest_month for p in await _projections(db_session, m.loan.id)]
    assert months == [LAST]
    assert await _balance(m) == Decimal("-24000.00") + Decimal("1000.00") - Decimal("240.00")


# ─── Serving ─────────────────────────────────────────────────────────────────


async def test_every_listing_serializes_the_month(api_client, db_session):
    m = await _mortgage(db_session, user=api_client.test_user)
    resp = await api_client.post(
        f"/api/v1/{m.budget.id}/transactions",
        json={
            "account_id": str(m.checking.id),
            "date": THIS.isoformat(),
            "amount": "500.00",
            "transfer_account_id": str(m.loan.id),
        },
    )
    assert resp.status_code == 201, resp.text
    assert "projected_interest_month" in resp.json()
    assert resp.json()["projected_interest_month"] is None, "the payment is no projection"
    projection = await _only_projection(db_session, m.loan.id)
    pid = str(projection.id)

    register = (await api_client.get(f"/api/v1/accounts/{m.loan.id}/transactions")).json()
    assert {r["id"]: r["projected_interest_month"] for r in register}[pid] == THIS.isoformat()

    budget_wide = (await api_client.get(f"/api/v1/{m.budget.id}/transactions")).json()
    listed = {r["id"]: r for r in budget_wide["transactions"]}
    assert listed[pid]["projected_interest_month"] == THIS.isoformat()
    assert all("projected_interest_month" in r for r in budget_wide["transactions"])

    one = (await api_client.get(f"/api/v1/transactions/{pid}")).json()
    assert one["projected_interest_month"] == THIS.isoformat()

    scope = {"budget_id": str(m.budget.id)}
    patched = await api_client.patch(
        f"/api/v1/transactions/{pid}", params=scope, json={"memo": "noted"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["projected_interest_month"] == THIS.isoformat()

    adopted = await api_client.patch(
        f"/api/v1/transactions/{pid}", params=scope, json={"cleared": "cleared"}
    )
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["projected_interest_month"] is None


async def test_the_liability_listing_serves_the_projection(api_client, db_session):
    m = await _mortgage(db_session, user=api_client.test_user)
    await _pay(m, THIS)
    listed = (await api_client.get(f"/api/v1/{m.budget.id}/liabilities")).json()
    row = next(item for item in listed if item["id"] == str(m.liability.id))
    assert money(row["projected_interest_this_month"]) == Decimal("120.00")
    assert row["estimated_interest_this_month"] is None
    assert money(row["current_balance"]) == Decimal("23620.00")
    assert money(row["monthly_interest_now"]) == Decimal("120.00")


async def test_a_loan_with_no_projection_serves_null(api_client, db_session):
    m = await _mortgage(db_session, user=api_client.test_user)
    listed = (await api_client.get(f"/api/v1/{m.budget.id}/liabilities")).json()
    row = next(item for item in listed if item["id"] == str(m.liability.id))
    assert "projected_interest_this_month" in row
    assert row["projected_interest_this_month"] is None
    assert money(row["estimated_interest_this_month"]) == Decimal("120.00")


async def test_anchor_ledger_never_counts_a_projection(db_session):
    m = await _mortgage(db_session)
    await _pay(m, THIS)
    projection = await _only_projection(db_session, m.loan.id)
    before = await m.services.account_repo.get_anchor_ledger(m.loan.id, TODAY)  # type: ignore[attr-defined]
    # Even a projection somehow marked cleared (the invariant says clearing
    # adopts it) stays out of what a bank's balance is measured against.
    projection.cleared = "cleared"
    await db_session.flush()
    after = await m.services.account_repo.get_anchor_ledger(m.loan.id, TODAY)  # type: ignore[attr-defined]
    assert after == before
