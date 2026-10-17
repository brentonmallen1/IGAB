"""Per-request statement counts and database time, for finding slow paths.

Off unless `LOG_QUERY_STATS` is set. With it on, every request logs one line:

    POST /api/v1/<budget>/categories/auto-assign -> 204: 14 statements,
    9.8 ms in the database, 31.0 ms total

Counts first, timings second, for the reason `tests/integration/
statement_counts.py` gives: a count that grows with the number of categories
or months names its own cause, where a slow timing only says something is
slow. This is the same question asked of a live server instead of a test.

The engine hooks are `before_cursor_execute`/`after_cursor_execute`, so the
time is wall time around each round trip — what the request waited for, which
is the figure that matters to someone clicking a button.

The current request's tally lives in a context variable. Starlette runs the
endpoint in a task copied from the middleware's context, and SQLAlchemy's
greenlet bridge runs the sync hooks in that same context, so every statement
a request issues lands on its own tally and on no other request's.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class QueryStats:
    statements: int = 0
    db_seconds: float = 0.0


_current: ContextVar[QueryStats | None] = ContextVar("igab_query_stats", default=None)
_STARTED = "igab_query_stats_started"


def _before(conn, cursor, statement, parameters, context, executemany) -> None:
    if _current.get() is not None:
        # One slot per connection: a connection runs one statement at a time,
        # and a statement that raised simply leaves a value the next overwrites.
        conn.info[_STARTED] = time.perf_counter()


def _after(conn, cursor, statement, parameters, context, executemany) -> None:
    stats = _current.get()
    started = conn.info.pop(_STARTED, None)
    if stats is None or started is None:
        return
    stats.statements += 1
    stats.db_seconds += time.perf_counter() - started


def install(engine: Engine) -> None:
    """Hook an engine's statements. Idempotent, so a reload cannot double-count."""
    if not event.contains(engine, "before_cursor_execute", _before):
        event.listen(engine, "before_cursor_execute", _before)
        event.listen(engine, "after_cursor_execute", _after)


@contextmanager
def measuring() -> Iterator[QueryStats]:
    """Tally every statement issued inside the block."""
    stats = QueryStats()
    token = _current.set(stats)
    try:
        yield stats
    finally:
        _current.reset(token)
