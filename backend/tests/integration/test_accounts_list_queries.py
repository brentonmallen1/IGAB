"""The accounts listing must not ask per account.

It did: `list_accounts` called `get_balance`, `get_cleared_balance` and
`get_uncategorized_count` inside a Python loop, so sixteen accounts cost
forty-nine sequential round-trips and the page got slower with every account
added. Locally that is tens of milliseconds; against a database a few
milliseconds away it is hundreds, because the cost is latency, not work.

A count assertion rather than a timing one: timings are flaky and say nothing
about why. If someone reintroduces a per-account query, the count moves and
names itself.
"""

import uuid
from datetime import date

from sqlalchemy import event

from .factories import create_account, create_budget, create_transaction


class _Counter:
    """Counts statements issued on a session's sync connection."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def __call__(self, conn, cursor, statement, params, context, executemany) -> None:
        self.statements.append(statement)

    @property
    def selects(self) -> int:
        return sum(1 for s in self.statements if s.lstrip().upper().startswith("SELECT"))


async def _count_list_selects(api_client, db_session, budget_id: uuid.UUID) -> int:
    counter = _Counter()
    # The API and this fixture share one session, so its bind is where every
    # statement the request issues shows up.
    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", counter)
    try:
        resp = await api_client.get(f"/api/v1/{budget_id}/accounts")
        assert resp.status_code == 200
    finally:
        event.remove(bind, "before_cursor_execute", counter)
    return counter.selects


async def _seed(db_session, budget, n: int, start: int = 0) -> None:
    for i in range(start, start + n):
        account = await create_account(db_session, budget, name=f"Account {i}")
        await create_transaction(db_session, budget, account, "10.00", date(2026, 8, 1))
    await db_session.flush()


class TestAccountsListDoesNotScaleInQueries:
    async def test_query_count_is_flat_as_accounts_are_added(self, api_client, db_session):
        """Three accounts and nine must cost the same number of SELECTs.

        The absolute number is not the contract — auth and budget-access
        lookups are in it, and they may legitimately change. That it does not
        GROW with the account count is the contract.
        """
        budget = await create_budget(db_session, api_client.test_user)
        await _seed(db_session, budget, 3)
        with_three = await _count_list_selects(api_client, db_session, budget.id)

        await _seed(db_session, budget, 6, start=3)
        with_nine = await _count_list_selects(api_client, db_session, budget.id)

        assert with_nine == with_three, (
            f"{with_three} SELECTs for 3 accounts, {with_nine} for 9 — "
            "the listing is asking per account again"
        )

    async def test_the_listing_still_reports_each_accounts_figures(self, api_client, db_session):
        """Batching must not change any answer, only the statement count."""
        budget = await create_budget(db_session, api_client.test_user)
        funded = await create_account(db_session, budget, name="Harborstone")
        await create_transaction(db_session, budget, funded, "100.00", date(2026, 8, 1))
        await create_transaction(db_session, budget, funded, "-30.00", date(2026, 8, 2))
        empty = await create_account(db_session, budget, name="Cascade Point HYSA")
        await db_session.flush()

        rows = {a["name"]: a for a in (await api_client.get(f"/api/v1/{budget.id}/accounts")).json()}

        assert float(rows["Harborstone"]["balance"]) == 70.0
        # An account with no rows contributes no group to the aggregate; it
        # must read as zero, never as a missing key.
        assert float(rows["Cascade Point HYSA"]["balance"]) == 0.0
        assert rows["Cascade Point HYSA"]["uncategorized_count"] == 0
