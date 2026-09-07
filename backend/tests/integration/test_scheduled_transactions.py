"""A row entered from a schedule links back to it.

`transactions.scheduled_transaction_id` existed but nothing wrote or read
it: `enter_now` never passed it, so a rent row entered from the schedule was
indistinguishable from one typed by hand.
"""

from datetime import timedelta
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

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_user,
    make_services,
)


async def _setup(db_session, *, transfer_to=None, **overrides):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    payee = await create_payee(db_session, budget, "Landlord")
    sched_svc = ScheduledTransactionService(
        ScheduledTransactionRepository(db_session), services.transactions
    )
    fields = dict(
        account_id=checking.id,
        amount=Decimal("-1200.00"),
        frequency="monthly",
        start_date=today_utc(),
        payee_id=payee.id,
        memo="rent",
    )
    fields.update(overrides)
    sched = await sched_svc.create(budget.id, ScheduledTransactionCreate(**fields))
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

    created = await sched_svc.process_due(budget.id, today_utc())
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


# ─── Posting date, missed nights, completion ─────────────────────────────────


async def test_enter_now_posts_on_the_due_date_not_today(db_session):
    """A bill entered from the schedule is dated the occurrence it stands
    for. It used to be dated the day the button was pressed, so entering
    Friday's rent on Monday filed it three days late — and a nightly run that
    slept a night backdated nothing."""
    due = today_utc() - timedelta(days=5)
    services, sched_svc, budget, checking, sched, _ = await _setup(db_session, start_date=due)

    await sched_svc.enter_now(sched.id, budget.id)

    [row] = await _rows_for(services, checking.id)
    assert row.date == due


async def test_last_created_date_is_the_posted_date(db_session):
    due = today_utc() - timedelta(days=5)
    _, sched_svc, budget, _, sched, _ = await _setup(db_session, start_date=due)
    await sched_svc.enter_now(sched.id, budget.id)
    refreshed = await sched_svc.repo.get(sched.id)
    assert refreshed.last_created_date == due


async def test_process_due_posts_each_missed_occurrence_on_its_own_date(db_session):
    """A job that slept two nights owes two rows. Weekly, auto-create, first
    due 15 days ago: three occurrences are due, each dated its own week."""
    first = today_utc() - timedelta(days=15)
    services, sched_svc, budget, checking, sched, _ = await _setup(
        db_session, frequency="weekly", start_date=first, auto_create=True
    )

    created = await sched_svc.process_due(budget.id, today_utc())

    assert created == 3
    rows = sorted(r.date for r in await _rows_for(services, checking.id))
    assert rows == [first, first + timedelta(days=7), first + timedelta(days=14)]
    refreshed = await sched_svc.repo.get(sched.id)
    assert refreshed.next_occurrence_date == first + timedelta(days=21)


async def test_process_due_leaves_a_non_auto_schedule_due(db_session):
    """Behaviour change, on purpose: a schedule the person enters by hand is
    never advanced by the nightly job. It used to roll forward silently, so
    a missed bill moved to next month with no trace it had been missed."""
    due = today_utc() - timedelta(days=3)
    services, sched_svc, budget, checking, sched, _ = await _setup(db_session, start_date=due)

    created = await sched_svc.process_due(budget.id, today_utc())

    assert created == 0
    assert await _rows_for(services, checking.id) == []
    assert (await sched_svc.repo.get(sched.id)).next_occurrence_date == due


async def test_a_due_twice_monthly_auto_schedule_posts_once_per_occurrence_not_nightly(db_session):
    """The drift case. `calculate_next` had no twice-monthly branch and fell
    through to "same date", so the schedule never advanced and every nightly
    run posted the same paycheck again."""
    today = today_utc()
    # Start on the 1st of last month with the 15th as the second day: the
    # occurrences due by today are a fixed, countable set.
    start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    services, sched_svc, budget, checking, sched, _ = await _setup(
        db_session,
        frequency="twice_monthly",
        start_date=start,
        second_day_of_month=15,
        auto_create=True,
        amount=Decimal("2450.00"),
    )
    expected = [d for d in (start, start.replace(day=15)) if d <= today]
    nxt = start.replace(month=start.month % 12 + 1, year=start.year + (start.month == 12))
    for d in (nxt.replace(day=1), nxt.replace(day=15)):
        if d <= today:
            expected.append(d)

    first_run = await sched_svc.process_due(budget.id, today)
    second_run = await sched_svc.process_due(budget.id, today)

    assert first_run == len(expected)
    assert second_run == 0
    rows = sorted(r.date for r in await _rows_for(services, checking.id))
    assert rows == expected


async def test_once_completes_after_enter_now(db_session):
    services, sched_svc, budget, checking, sched, _ = await _setup(db_session, frequency="once")

    await sched_svc.enter_now(sched.id, budget.id)

    assert len(await _rows_for(services, checking.id)) == 1
    assert await sched_svc.repo.get(sched.id) is None


async def test_once_completes_after_skip(db_session):
    _, sched_svc, budget, _, sched, _ = await _setup(db_session, frequency="once")
    assert await sched_svc.skip(sched.id) is None
    assert await sched_svc.repo.get(sched.id) is None


async def test_last_occurrence_before_end_date_completes_the_schedule(db_session):
    """One rule for `once` and for `end_date`: when there is no next
    occurrence, the schedule is done. `process_due` used to have its own
    end-date branch that fired a day late and only on the nightly run."""
    today = today_utc()
    _, sched_svc, budget, _, sched, _ = await _setup(
        db_session, start_date=today, end_date=today + timedelta(days=10)
    )
    await sched_svc.enter_now(sched.id, budget.id)
    assert await sched_svc.repo.get(sched.id) is None


async def test_process_due_ends_a_schedule_whose_end_date_moved_behind_it(db_session):
    """An end date edited to before the next occurrence means "stop now":
    the nightly run retires the schedule without posting another row."""
    today = today_utc()
    start = today - timedelta(days=40)
    services, sched_svc, budget, checking, sched, _ = await _setup(
        db_session, start_date=start, auto_create=True
    )
    # Skipped once, so the next occurrence sits about ten days back; then the
    # end date is pulled to between the start and that occurrence.
    skipped = await sched_svc.skip(sched.id)
    assert skipped is not None and start < skipped.next_occurrence_date <= today
    await sched_svc.update(sched.id, end_date=start + timedelta(days=5))

    created = await sched_svc.process_due(budget.id, today)

    assert created == 0
    assert await _rows_for(services, checking.id) == []
    assert await sched_svc.repo.get(sched.id) is None


# ─── The API edge: PATCH nulls, the enum, the new fields ──────────────────────


async def _api_setup(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")
    group = await create_category_group(db_session, budget, "Bills")
    category = await create_category(db_session, budget, group, "Internet")
    await db_session.commit()
    return budget, checking, savings, category


async def test_patch_null_clears_end_date_category_and_memo(api_client, db_session):
    """`exclude_none` on the PATCH made these impossible to remove: the only
    way to drop an end date was to delete the schedule."""
    budget, checking, _, category = await _api_setup(api_client, db_session)
    r = await api_client.post(
        f"/api/v1/{budget.id}/scheduled-transactions",
        json={
            "account_id": str(checking.id),
            "amount": "-45",
            "frequency": "monthly",
            "start_date": "2026-10-01",
            "end_date": "2027-10-01",
            "category_id": str(category.id),
            "memo": "Internet bill",
        },
    )
    assert r.status_code == 201, r.text
    sched_id = r.json()["id"]

    r = await api_client.patch(
        f"/api/v1/scheduled-transactions/{sched_id}",
        json={"end_date": None, "category_id": None, "memo": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["end_date"] is None and body["category_id"] is None and body["memo"] is None


async def test_patch_omitted_fields_are_untouched(api_client, db_session):
    budget, checking, _, category = await _api_setup(api_client, db_session)
    r = await api_client.post(
        f"/api/v1/{budget.id}/scheduled-transactions",
        json={
            "account_id": str(checking.id),
            "amount": "-45",
            "frequency": "monthly",
            "start_date": "2026-10-01",
            "category_id": str(category.id),
            "memo": "Internet bill",
        },
    )
    sched_id = r.json()["id"]
    r = await api_client.patch(f"/api/v1/scheduled-transactions/{sched_id}", json={"amount": "-60"})
    body = r.json()
    assert body["amount"] == -60.0
    assert body["category_id"] == str(category.id) and body["memo"] == "Internet bill"


async def test_patch_twice_monthly_without_second_day_is_rejected(api_client, db_session):
    """The shape rule runs on the merged row at the edge, not on the night
    the arithmetic first meets it."""
    budget, checking, _, _ = await _api_setup(api_client, db_session)
    r = await api_client.post(
        f"/api/v1/{budget.id}/scheduled-transactions",
        json={
            "account_id": str(checking.id),
            "amount": "2450",
            "frequency": "monthly",
            "start_date": "2026-10-01",
        },
    )
    sched_id = r.json()["id"]
    r = await api_client.patch(
        f"/api/v1/scheduled-transactions/{sched_id}", json={"frequency": "twice_monthly"}
    )
    assert r.status_code == 400
    assert "second day" in r.json()["detail"]
    r = await api_client.patch(
        f"/api/v1/scheduled-transactions/{sched_id}",
        json={"frequency": "twice_monthly", "second_day_of_month": 15},
    )
    assert r.status_code == 200, r.text


async def test_unknown_frequency_is_refused_at_the_edge(api_client, db_session):
    budget, checking, _, _ = await _api_setup(api_client, db_session)
    r = await api_client.post(
        f"/api/v1/{budget.id}/scheduled-transactions",
        json={
            "account_id": str(checking.id),
            "amount": "-45",
            "frequency": "fortnightly",
            "start_date": "2026-10-01",
        },
    )
    assert r.status_code == 422


async def test_response_carries_transfer_account_id_and_second_day(api_client, db_session):
    """Both columns existed and the frontend type declared one of them, but
    neither crossed the API — a scheduled transfer could not be created or
    read, so the page's "Transfer: Savings" branch was dead."""
    budget, checking, savings, _ = await _api_setup(api_client, db_session)
    r = await api_client.post(
        f"/api/v1/{budget.id}/scheduled-transactions",
        json={
            "account_id": str(checking.id),
            "amount": "-500",
            "frequency": "twice_monthly",
            "start_date": "2026-10-01",
            "second_day_of_month": 15,
            "transfer_account_id": str(savings.id),
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["transfer_account_id"] == str(savings.id)
    assert body["second_day_of_month"] == 15
    listed = (await api_client.get(f"/api/v1/{budget.id}/scheduled-transactions")).json()
    assert listed[0]["transfer_account_id"] == str(savings.id)


async def test_skip_of_a_once_schedule_answers_204(api_client, db_session):
    budget, checking, _, _ = await _api_setup(api_client, db_session)
    r = await api_client.post(
        f"/api/v1/{budget.id}/scheduled-transactions",
        json={
            "account_id": str(checking.id),
            "amount": "-45",
            "frequency": "once",
            "start_date": "2026-10-01",
        },
    )
    sched_id = r.json()["id"]
    r = await api_client.post(f"/api/v1/scheduled-transactions/{sched_id}/skip")
    assert r.status_code == 204
    assert (await api_client.get(f"/api/v1/{budget.id}/scheduled-transactions")).json() == []
