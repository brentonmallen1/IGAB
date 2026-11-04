"""`igab.db.query_stats`: spans and the `Server-Timing` header.

The header is what the browser's network panel shows for a slow request, so
its shape is the contract: `db` and `total` always, each span name once with
its runs summed, durations in milliseconds.
"""

from igab.db import query_stats
from igab.db.query_stats import QueryStats, Span, server_timing, span


def test_a_span_outside_a_measured_request_records_nothing():
    """`LOG_QUERY_STATS` off means no `measuring()` block, and a span on a
    hot path must then cost nothing and leave nothing behind."""
    with span("card-walk"):
        pass
    assert query_stats._current.get() is None


def test_a_span_inside_a_measured_request_lands_on_its_tally():
    with query_stats.measuring() as stats:
        with span("card-walk"):
            stats.statements += 3  # what the engine hooks would add
        with span("snapshot-rebuild"):
            pass
    assert [(s.name, s.statements) for s in stats.spans] == [
        ("card-walk", 3),
        ("snapshot-rebuild", 0),
    ]
    assert all(s.seconds >= 0 for s in stats.spans)


def test_the_header_carries_db_total_and_each_span_once():
    stats = QueryStats(
        statements=30,
        db_seconds=0.0934,
        spans=[
            Span("card-walk", 0.020, 8),
            Span("snapshot-rebuild", 0.054, 6),
            Span("card-walk", 0.010, 1),
        ],
    )
    assert server_timing(stats, 0.1393) == (
        'db;dur=93.4;desc="30 statements", '
        "total;dur=139.3, "
        'card-walk;dur=30.0;desc="2x, 9 statements", '
        'snapshot-rebuild;dur=54.0;desc="1x, 6 statements"'
    )


def test_a_request_with_no_spans_still_says_db_and_total():
    assert server_timing(QueryStats(), 0.0012) == ('db;dur=0.0;desc="0 statements", total;dur=1.2')
