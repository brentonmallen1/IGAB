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

The same tally goes out as a `Server-Timing` header (`server_timing`), so the
browser's network panel shows where a slow request spent its time without
anyone reading the server log. Named `span`s inside a request — the snapshot
rebuild, the card walk — ride on the same tally, so the header and the log
line say which of them the request paid for.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


@dataclass
class Span:
    """One named stretch of a request: wall time and the statements it issued."""

    name: str
    seconds: float
    statements: int


@dataclass
class QueryStats:
    statements: int = 0
    db_seconds: float = 0.0
    spans: list[Span] = field(default_factory=list)


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


@contextmanager
def span(name: str) -> Iterator[None]:
    """Time a named stretch of the current request, when one is being measured.

    A no-op outside `measuring()` — which is to say whenever `LOG_QUERY_STATS`
    is off — so it can sit on a hot path. A span that runs more than once in
    a request is recorded each time; the header sums them by name.
    """
    stats = _current.get()
    if stats is None:
        yield
        return
    started, statements = time.perf_counter(), stats.statements
    try:
        yield
    finally:
        done = Span(name, time.perf_counter() - started, stats.statements - statements)
        stats.spans.append(done)
        logger.info("  %s: %d statements, %.1f ms", done.name, done.statements, done.seconds * 1000)


def server_timing(stats: QueryStats, total_seconds: float) -> str:
    """The `Server-Timing` header value for one request's tally.

    `db` and `total` always; each span name once, its durations summed and its
    run count in the description. Durations are milliseconds, as the header
    specifies.
    """
    parts = [
        f'db;dur={stats.db_seconds * 1000:.1f};desc="{stats.statements} statements"',
        f"total;dur={total_seconds * 1000:.1f}",
    ]
    by_name: dict[str, list[Span]] = {}
    for done in stats.spans:
        by_name.setdefault(done.name, []).append(done)
    for name, runs in by_name.items():
        seconds = sum(r.seconds for r in runs)
        statements = sum(r.statements for r in runs)
        parts.append(
            f'{name};dur={seconds * 1000:.1f};desc="{len(runs)}x, {statements} statements"'
        )
    return ", ".join(parts)
