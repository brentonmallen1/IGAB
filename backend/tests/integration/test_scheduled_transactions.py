"""A row entered from a schedule links back to it.

`transactions.scheduled_transaction_id` existed but nothing wrote or read
it: `enter_now` never passed it, so a rent row entered from the schedule was
indistinguishable from one typed by hand.
"""

from decimal import Decimal

from sqlalchemy import select

from igab.db.models import ChangeLog
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.services.scheduled_transaction_service import (
    ScheduledTransactionCreate,
    ScheduledTransactionService,
)
from igab.services.undo_service import UndoService
from igab.utils.clock import today_utc

from .factories import create_account, create_budget, create_payee, create_user, make_services


async def _setup(db_session, *, transfer_to=None):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    payee = await create_payee(db_session, budget, "Landlord")
    sched_svc = ScheduledTransactionService(
        ScheduledTransactionRepository(db_session), services.transactions
    )
    sched = await sched_svc.create(
        budget.id,
        ScheduledTransactionCreate(
            account_id=checking.id,
            amount=Decimal("-1200.00"),
            frequency="monthly",
            start_date=today_utc(),
            payee_id=payee.id,
            memo="rent",
        ),
    )
    if transfer_to is not None:
        sched = await sched_svc.update(sched.id, transfer_account_id=transfer_to.id)
    return services, sched_svc, budget, checking, sched, user


async def _rows_for(services, account_id):
    return [r for r in await services.transaction_repo.get_for_account(account_id)]


async def test_enter_now_links_the_row_to_its_schedule_and_stamps_provenance(db_session):
    services, sched_svc, budget, checking, sched, _ = await _setup(db_session)

    await sched_svc.enter_now(sched.id, budget.id)

    [row] = await _rows_for(services, checking.id)
    assert row.scheduled_transaction_id == sched.id
    assert row.created_via == "scheduled"
    assert row.memo == "rent" and row.amount == Decimal("-1200.00")


async def test_enter_now_on_a_scheduled_transfer_links_both_legs(db_session):
    services0 = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")
    sched_svc = ScheduledTransactionService(
        ScheduledTransactionRepository(db_session), services0.transactions
    )
    sched = await sched_svc.create(
        budget.id,
        ScheduledTransactionCreate(
            account_id=checking.id,
            amount=Decimal("-500.00"),
            frequency="monthly",
            start_date=today_utc(),
        ),
    )
    await sched_svc.update(sched.id, transfer_account_id=savings.id)

    await sched_svc.enter_now(sched.id, budget.id)

    [out_leg] = await _rows_for(services0, checking.id)
    [in_leg] = await _rows_for(services0, savings.id)
    assert out_leg.transfer_id == in_leg.id
    assert out_leg.scheduled_transaction_id == sched.id
    assert in_leg.scheduled_transaction_id == sched.id
    assert out_leg.created_via == "scheduled" and in_leg.created_via == "scheduled"


async def test_process_due_auto_create_links_and_logs_as_system(db_session):
    services, sched_svc, budget, checking, sched, _ = await _setup(db_session)
    await sched_svc.update(sched.id, auto_create=True)

    created = await sched_svc.process_due(budget.id)
    assert created == 1

    [row] = await _rows_for(services, checking.id)
    assert row.scheduled_transaction_id == sched.id
    await db_session.flush()
    change = (
        (
            await db_session.execute(
                select(ChangeLog).where(ChangeLog.entity_id == row.id, ChangeLog.action == "create")
            )
        )
        .scalars()
        .first()
    )
    assert change is not None and change.source == "system"
    refreshed = await sched_svc.repo.get(sched.id)
    assert refreshed.next_occurrence_date > today_utc()


async def test_listing_paths_serialize_scheduled_transaction_id(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    services = make_services(db_session)
    sched_svc = ScheduledTransactionService(
        ScheduledTransactionRepository(db_session), services.transactions
    )
    sched = await sched_svc.create(
        budget.id,
        ScheduledTransactionCreate(
            account_id=checking.id,
            amount=Decimal("-9.00"),
            frequency="monthly",
            start_date=today_utc(),
        ),
    )
    await sched_svc.enter_now(sched.id, budget.id)

    rows = (await api_client.get(f"/api/v1/accounts/{checking.id}/transactions")).json()
    assert rows[0]["scheduled_transaction_id"] == str(sched.id)
    one = (
        await api_client.get(
            f"/api/v1/transactions/{rows[0]['id']}", params={"budget_id": str(budget.id)}
        )
    ).json()
    assert one["scheduled_transaction_id"] == str(sched.id)
    assert one["created_via"] == "scheduled"


async def test_undo_of_enter_now_removes_the_row_and_rolls_the_schedule_back(db_session):
    """Enter-now is one batch: undoing the created transaction also takes
    back the schedule's advance. It used to leave last_created_date set — a
    register with no row while the schedule claimed it had run."""
    services, sched_svc, budget, checking, sched, _ = await _setup(db_session)
    before_next = sched.next_occurrence_date
    await sched_svc.enter_now(sched.id, budget.id)
    [row] = await _rows_for(services, checking.id)
    await db_session.flush()
    change = (
        (
            await db_session.execute(
                select(ChangeLog).where(ChangeLog.entity_id == row.id, ChangeLog.action == "create")
            )
        )
        .scalars()
        .first()
    )

    await UndoService(db_session).undo_change(budget.id, change.id)

    assert await _rows_for(services, checking.id) == []
    rolled_back = await sched_svc.repo.get(sched.id)
    assert rolled_back.last_created_date is None
    assert rolled_back.next_occurrence_date == before_next
