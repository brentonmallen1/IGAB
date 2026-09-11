"""What a request asks of the database, for the flat-cost ratchets.

One counter and one rule for what counts as a SELECT. The accounts listing
and the report suites each carried a byte-for-byte copy; had one learned to
count a CTE or skip an auth lookup, two ratchets would have measured
different things under the same name.

Counts, not timings: timings are flaky and say nothing about why. If a cost
that should be flat starts to grow — a query per month, a query per account,
a register fetched whole — the count moves and names itself. The absolute
numbers are not the contract (auth and budget-access lookups are in them and
may legitimately change); that they do not GROW is.
"""

from sqlalchemy import event


class StatementCounter:
    """Statements issued on a session's sync connection, with the rows each
    returned."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, int]] = []

    def __call__(self, conn, cursor, statement, params, context, executemany) -> None:
        # asyncpg reports a SELECT's row count from its status line.
        self.statements.append((statement, max(cursor.rowcount, 0)))

    def _select_rows(self) -> list[int]:
        return [n for s, n in self.statements if s.lstrip().upper().startswith("SELECT")]

    @property
    def selects(self) -> int:
        return len(self._select_rows())

    @property
    def rows_fetched(self) -> int:
        return sum(self._select_rows())


async def count_request(api_client, db_session, path: str, params: dict) -> StatementCounter:
    """GET `path` and count what it asked the database."""
    counter = StatementCounter()
    # The API and this fixture share one session, so its bind is where every
    # statement the request issues shows up.
    bind = db_session.get_bind()
    event.listen(bind, "after_cursor_execute", counter)
    try:
        resp = await api_client.get(path, params=params)
        assert resp.status_code == 200, resp.text
    finally:
        event.remove(bind, "after_cursor_execute", counter)
    # Every request reads at least its user: a counter that saw nothing is
    # broken, and would make every flat-count ratchet pass as 0 == 0.
    assert counter.selects > 0 and counter.rows_fetched > 0, "the counter saw no reads"
    return counter
