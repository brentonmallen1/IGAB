"""Category balance snapshot cache: correctness and invalidation.

The snapshot-served budget summary must be indistinguishable from the live
simulation (the pre-snapshot code path, kept as the oracle), and every
mutation channel must invalidate the cache:

- ORM object changes (session.add / attribute assignment / session.delete)
- core update() statements via session.execute (BaseRepository.update,
  soft_delete, update_cleared)
- core insert() statements (bulk imports)

This is trust-surface code (CLAUDE.md): edge cases covered include zero
balances, negative amounts, overspending floors, future-dated data, rounding
cents, and stale-row pruning.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import BudgetSnapshotMeta, CategoryMonthSnapshot
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.snapshot_repo import SnapshotRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.budget_service import BudgetService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
)

D = Decimal
DEC25 = date(2025, 12, 1)
JAN = date(2026, 1, 1)
FEB = date(2026, 2, 1)
MAR = date(2026, 3, 1)
APR = date(2026, 4, 1)
DEC26 = date(2026, 12, 1)
ALL_MONTHS = [DEC25, JAN, FEB, MAR, APR, DEC26]


def _services(db_session) -> tuple[BudgetService, BudgetService]:
    """(snapshot-backed service, live-path oracle) over the same session."""
    kwargs = dict(
        account_repo=AccountRepository(db_session),
        category_repo=CategoryRepository(db_session),
        category_group_repo=CategoryGroupRepository(db_session),
        assignment_repo=BudgetAssignmentRepository(db_session),
        transaction_repo=TransactionRepository(db_session),
    )
    snap = BudgetService(**kwargs, snapshot_repo=SnapshotRepository(db_session))
    live = BudgetService(**kwargs)
    return snap, live


def _norm(summary):
    return (
        summary.to_be_assigned,
        summary.total_assigned,
        summary.total_activity,
        summary.total_overspent,
        summary.assigned_in_future,
        sorted(
            (
                (b.category_id, b.month, b.assigned, b.activity, b.available)
                for b in summary.category_balances
            ),
            key=lambda t: str(t[0]),
        ),
    )


async def _assert_parity(snap, live, budget_id, months=ALL_MONTHS):
    for month in months:
        got = await snap.get_budget_summary(budget_id, month)
        expected = await live.get_budget_summary(budget_id, month)
        assert _norm(got) == _norm(expected), f"snapshot/live mismatch for {month}"


async def _meta_exists(db_session, budget_id) -> bool:
    row = await db_session.scalar(
        select(BudgetSnapshotMeta.budget_id).where(BudgetSnapshotMeta.budget_id == budget_id)
    )
    return row is not None


class World:
    """A budget exercising every balance edge the simulation has:
    carryover, overspend + floor, unfunded spending, future data, income."""

    budget = None
    checking = None
    groceries = None
    dining = None
    rent = None
    income_cat = None
    grocery_jan_spend = None
    grocery_jan_assignment = None


@pytest.fixture
async def world(db_session) -> World:
    w = World()
    user = await create_user(db_session)
    w.budget = await create_budget(db_session, user)
    w.checking = await create_account(db_session, w.budget, "Checking")

    everyday = await create_category_group(db_session, w.budget, "Everyday")
    income_group = await create_category_group(db_session, w.budget, "Income", is_system=True)
    w.groceries = await create_category(db_session, w.budget, everyday, "Groceries")
    w.dining = await create_category(db_session, w.budget, everyday, "Dining")
    w.rent = await create_category(db_session, w.budget, everyday, "Rent")
    w.income_cat = await create_category(db_session, w.budget, income_group, "Ready to Assign")

    # Income and an uncategorized outflow: hit TBA via the account balance only
    await create_transaction(
        db_session, w.budget, w.checking, "3000.00", JAN, category=w.income_cat
    )
    await create_transaction(db_session, w.budget, w.checking, "-25.00", JAN)

    # Groceries: JAN leftover carries, FEB overspends (-30), MAR floors to 0
    w.grocery_jan_assignment = await create_budget_assignment(
        db_session, w.budget, w.groceries, JAN, "200.00"
    )
    w.grocery_jan_spend = await create_transaction(
        db_session, w.budget, w.checking, "-150.00", JAN, category=w.groceries
    )
    await create_budget_assignment(db_session, w.budget, w.groceries, FEB, "100.00")
    await create_transaction(db_session, w.budget, w.checking, "-180.00", FEB, category=w.groceries)

    # Dining: funded once, untouched — pure carryover; future-dated APR spend
    await create_budget_assignment(db_session, w.budget, w.dining, JAN, "50.00")
    await create_transaction(db_session, w.budget, w.checking, "-20.00", APR, category=w.dining)

    # Rent: completely unfunded FEB spending — overspent with no assignment
    await create_transaction(db_session, w.budget, w.checking, "-500.00", FEB, category=w.rent)

    # Future assignment: deducted from every earlier month's TBA
    await create_budget_assignment(db_session, w.budget, w.groceries, APR, "75.00")
    return w


async def test_parity_across_months(db_session, world):
    snap, live = _services(db_session)
    await _assert_parity(snap, live, world.budget.id)


async def test_explicit_carryover_and_overspend_floor(db_session, world):
    snap, _ = _services(db_session)

    def bal(summary, category):
        return next(b for b in summary.category_balances if b.category_id == category.id)

    jan = await snap.get_budget_summary(world.budget.id, JAN)
    assert bal(jan, world.groceries).available == D("50.00")
    assert bal(jan, world.dining).available == D("50.00")
    assert bal(jan, world.rent).available == D("0")

    feb = await snap.get_budget_summary(world.budget.id, FEB)
    # 50 carryover + 100 assigned - 180 spent: the overspent month shows red
    assert bal(feb, world.groceries).available == D("-30.00")
    assert bal(feb, world.rent).available == D("-500.00")
    assert bal(feb, world.dining).available == D("50.00")
    assert feb.total_overspent == D("530.00")

    mar = await snap.get_budget_summary(world.budget.id, MAR)
    # Overspending was absorbed by TBA — both categories restart at zero
    assert bal(mar, world.groceries).available == D("0")
    assert bal(mar, world.rent).available == D("0")
    assert mar.total_overspent == D("0")

    apr = await snap.get_budget_summary(world.budget.id, APR)
    assert bal(apr, world.groceries).available == D("75.00")
    assert bal(apr, world.dining).available == D("30.00")


async def test_summary_is_idempotent_and_marks_valid(db_session, world):
    snap, _ = _services(db_session)
    first = await snap.get_budget_summary(world.budget.id, FEB)
    assert await _meta_exists(db_session, world.budget.id)

    rows_before = {
        (r.category_id, r.month, r.assigned, r.activity, r.available)
        for r in (
            await db_session.execute(
                select(CategoryMonthSnapshot).where(
                    CategoryMonthSnapshot.budget_id == world.budget.id
                )
            )
        ).scalars()
    }
    second = await snap.get_budget_summary(world.budget.id, FEB)
    rows_after = {
        (r.category_id, r.month, r.assigned, r.activity, r.available)
        for r in (
            await db_session.execute(
                select(CategoryMonthSnapshot).where(
                    CategoryMonthSnapshot.budget_id == world.budget.id
                )
            )
        ).scalars()
    }
    assert _norm(first) == _norm(second)
    assert rows_before == rows_after
    assert await _meta_exists(db_session, world.budget.id)


async def test_unrelated_writes_do_not_invalidate(db_session, world):
    snap, _ = _services(db_session)
    await snap.get_budget_summary(world.budget.id, JAN)
    assert await _meta_exists(db_session, world.budget.id)

    await create_payee(db_session, world.budget, "Corner Store")
    account_repo = AccountRepository(db_session)
    await account_repo.update(world.checking.id, name="Main Checking")
    assert await _meta_exists(db_session, world.budget.id)


# ─── Invalidation matrix: every mutation channel must clear the meta row ──────


async def _prime(db_session, world):
    snap, live = _services(db_session)
    await snap.get_budget_summary(world.budget.id, FEB)
    assert await _meta_exists(db_session, world.budget.id)
    return snap, live


async def test_invalidates_on_orm_create(db_session, world):
    snap, live = await _prime(db_session, world)
    await create_transaction(
        db_session, world.budget, world.checking, "-10.00", FEB, category=world.dining
    )
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_core_update(db_session, world):
    snap, live = await _prime(db_session, world)
    repo = TransactionRepository(db_session)
    await repo.update(world.grocery_jan_spend.id, amount=D("-199.99"))
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_core_soft_delete(db_session, world):
    snap, live = await _prime(db_session, world)
    repo = TransactionRepository(db_session)
    await repo.soft_delete(world.grocery_jan_spend.id)
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_update_cleared(db_session, world):
    # cleared='pending' excludes the row from activity, so this core-update
    # path changes balances — exactly the statement flush events cannot see.
    snap, live = await _prime(db_session, world)
    repo = TransactionRepository(db_session)
    await repo.update_cleared(world.grocery_jan_spend.id, "pending")
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_orm_attribute_recategorize(db_session, world):
    snap, live = await _prime(db_session, world)
    world.grocery_jan_spend.category_id = world.dining.id
    await db_session.flush()
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_date_move_across_months(db_session, world):
    snap, live = await _prime(db_session, world)
    repo = TransactionRepository(db_session)
    await repo.update(world.grocery_jan_spend.id, date=date(2026, 3, 14))
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_bulk_create(db_session, world):
    snap, live = await _prime(db_session, world)
    repo = TransactionRepository(db_session)
    await repo.bulk_create(
        [
            {
                "budget_id": world.budget.id,
                "account_id": world.checking.id,
                "date": date(2026, 2, 20),
                "amount": D("-33.33"),
                "category_id": world.rent.id,
                "cleared": "cleared",
                "approved": True,
            },
            {
                "budget_id": world.budget.id,
                "account_id": world.checking.id,
                "date": date(2026, 2, 21),
                "amount": D("-33.34"),
                "category_id": world.rent.id,
                "cleared": "cleared",
                "approved": True,
            },
        ]
    )
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_set_assignment(db_session, world):
    snap, live = await _prime(db_session, world)
    await snap.set_assignment(world.budget.id, world.rent.id, FEB, D("450.00"))
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_move_money(db_session, world):
    snap, live = await _prime(db_session, world)
    await snap.move_money(world.budget.id, world.dining.id, world.groceries.id, D("25.00"), JAN)
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_assignment_attribute_change(db_session, world):
    snap, live = await _prime(db_session, world)
    world.grocery_jan_assignment.assigned = D("300.00")
    await db_session.flush()
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_assignment_hard_delete(db_session, world):
    snap, live = await _prime(db_session, world)
    await db_session.delete(world.grocery_jan_assignment)
    await db_session.flush()
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_category_soft_delete(db_session, world):
    # Deleting a category releases its money to TBA; both paths must agree.
    snap, live = await _prime(db_session, world)
    await CategoryRepository(db_session).soft_delete(world.dining.id)
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_invalidates_on_category_hide(db_session, world):
    snap, live = await _prime(db_session, world)
    await CategoryRepository(db_session).update(world.dining.id, is_archived=True)
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id)


async def test_repeated_mutate_read_cycles_stay_consistent(db_session, world):
    """Mutate → summary → mutate → summary within one transaction: the second
    mutation must invalidate the rebuild the first summary just persisted."""
    snap, live = _services(db_session)
    await snap.set_assignment(world.budget.id, world.rent.id, FEB, D("100.00"))
    await _assert_parity(snap, live, world.budget.id, [FEB, MAR])
    await snap.set_assignment(world.budget.id, world.rent.id, FEB, D("400.00"))
    assert not await _meta_exists(db_session, world.budget.id)
    await _assert_parity(snap, live, world.budget.id, [FEB, MAR])
    await create_transaction(
        db_session, world.budget, world.checking, "-0.01", MAR, category=world.rent
    )
    await _assert_parity(snap, live, world.budget.id)


async def test_stale_rows_pruned_on_rebuild(db_session, world):
    snap, _ = _services(db_session)
    only_may_txn = await create_transaction(
        db_session, world.budget, world.checking, "-40.00", date(2026, 5, 5), category=world.rent
    )
    await snap.get_budget_summary(world.budget.id, FEB)

    async def may_rows():
        return (
            await db_session.execute(
                select(CategoryMonthSnapshot).where(
                    CategoryMonthSnapshot.budget_id == world.budget.id,
                    CategoryMonthSnapshot.month == date(2026, 5, 1),
                )
            )
        ).scalars().all()

    assert len(await may_rows()) == 1

    await TransactionRepository(db_session).soft_delete(only_may_txn.id)
    await snap.get_budget_summary(world.budget.id, FEB)
    assert await may_rows() == []


async def test_zero_amounts_and_empty_budget(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    snap, live = _services(db_session)
    await _assert_parity(snap, live, budget.id)

    account = await create_account(db_session, budget, "Empty Checking")
    group = await create_category_group(db_session, budget, "Stuff")
    cat = await create_category(db_session, budget, group, "Zero")
    await create_budget_assignment(db_session, budget, cat, JAN, "0.00")
    await create_transaction(db_session, budget, account, "0.00", JAN, category=cat)
    await _assert_parity(snap, live, budget.id, [DEC25, JAN, FEB])

    summary = await snap.get_budget_summary(budget.id, JAN)
    bal = next(b for b in summary.category_balances if b.category_id == cat.id)
    assert (bal.assigned, bal.activity, bal.available) == (D("0"), D("0"), D("0"))


async def test_month_endpoint_serves_snapshots(api_client, db_session):
    """End-to-end through the real DI wiring: the months endpoint builds the
    cache, a mutation invalidates it, and responses match the live oracle."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    await create_budget_assignment(db_session, budget, cat, JAN, "80.00")
    await create_transaction(db_session, budget, account, "-95.50", JAN, category=cat)

    async def month_response(month):
        resp = await api_client.get(f"/api/v1/{budget.id}/months/{month.isoformat()}")
        assert resp.status_code == 200, resp.text
        return resp.json()

    body = await month_response(JAN)
    assert await _meta_exists(db_session, budget.id)
    assert D(str(body["category_balances"][0]["available"])) == D("-15.50")
    feb_body = await month_response(FEB)
    assert D(str(feb_body["category_balances"][0]["available"])) == D("0")

    await create_transaction(db_session, budget, account, "-1.00", FEB, category=cat)
    assert not await _meta_exists(db_session, budget.id)

    _, live = _services(db_session)
    expected = await live.get_budget_summary(budget.id, FEB)
    feb_body = await month_response(FEB)
    assert D(str(feb_body["to_be_assigned"])) == expected.to_be_assigned
    assert D(str(feb_body["category_balances"][0]["available"])) == D("-1.00")


async def test_snapshots_scoped_per_budget(db_session):
    """A rebuild for one budget must not fabricate validity for another."""
    user = await create_user(db_session)
    budget_a = await create_budget(db_session, user)
    budget_b = await create_budget(db_session, user)
    for budget in (budget_a, budget_b):
        account = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        cat = await create_category(db_session, budget, group, "Groceries")
        await create_budget_assignment(db_session, budget, cat, JAN, "10.00")
        await create_transaction(db_session, budget, account, "-4.00", JAN, category=cat)

    snap, live = _services(db_session)
    await snap.get_budget_summary(budget_a.id, JAN)
    assert await _meta_exists(db_session, budget_a.id)
    assert not await _meta_exists(db_session, budget_b.id)
    await _assert_parity(snap, live, budget_b.id, [JAN])
    # Both valid now; a write invalidates both (coarse by design)
    await snap.get_budget_summary(budget_a.id, JAN)
    b_cat_rows = await db_session.execute(
        select(CategoryMonthSnapshot).where(CategoryMonthSnapshot.budget_id == budget_b.id)
    )
    assert len(list(b_cat_rows.scalars())) > 0
