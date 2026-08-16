"""Offset pagination must partition the register — no row skipped, none
duplicated — even when many transactions share a date AND a created_at.

Bulk imports produce exactly that shape: every row inserted in one
transaction gets the same server-side created_at, so without a unique
ORDER BY tiebreaker Postgres is free to return tied rows in a different
order per query, and adjacent pages silently drop rows. This is the
"transactions randomly missing until I toggle views" bug from the YNAB
parity reconciliation (round 3)."""

from datetime import date

from .factories import (
    create_account,
    create_budget,
    create_transaction,
    create_user,
    make_services,
)

JUL1 = date(2026, 7, 1)


async def _clone_army(db_session, budget, account, n=12):
    """n rows identical in date, amount, cleared — and, because they are
    flushed in one DB transaction, identical in created_at too."""
    return [
        await create_transaction(db_session, budget, account, "-10.00", JUL1)
        for _ in range(n)
    ]


async def test_account_pages_partition_identical_rows(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget)
    created = await _clone_army(db_session, budget, account)

    repo = services.transaction_repo
    seen: list = []
    for offset in range(0, len(created), 5):
        page = await repo.get_for_account(account.id, limit=5, offset=offset)
        seen.extend(t.id for t in page)

    assert len(seen) == len(created)
    assert set(seen) == {t.id for t in created}, "pages skipped or duplicated rows"


async def test_account_page_order_is_deterministic(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget)
    await _clone_army(db_session, budget, account)

    repo = services.transaction_repo
    first = [t.id for t in await repo.get_for_account(account.id, limit=5, offset=0)]
    second = [t.id for t in await repo.get_for_account(account.id, limit=5, offset=0)]
    assert first == second


async def test_budget_register_pages_partition_identical_rows(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget)
    created = await _clone_army(db_session, budget, account)

    repo = services.transaction_repo
    seen: list = []
    for offset in range(0, len(created), 5):
        rows, total, _ = await repo.list_for_budget(
            budget.id, order="register", limit=5, offset=offset
        )
        assert total == len(created)
        seen.extend(r.id for r in rows)

    assert len(seen) == len(created)
    assert set(seen) == {t.id for t in created}, "pages skipped or duplicated rows"


async def test_budget_date_order_pages_partition_identical_rows(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget)
    created = await _clone_army(db_session, budget, account)

    repo = services.transaction_repo
    seen: list = []
    for offset in range(0, len(created), 5):
        rows, _, _ = await repo.list_for_budget(
            budget.id, order="date", limit=5, offset=offset
        )
        seen.extend(r.id for r in rows)

    assert set(seen) == {t.id for t in created}
