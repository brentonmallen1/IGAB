"""Pin the day `ReportService` believes it is.

The reports read `date.today()` when they are called, while a test module
reads it when it is imported. A run that straddles midnight on a month's last
day then seeds rows for one calendar and asks a service living in the next:
last month's partial month becomes "complete", a trailing window slides a day,
and an assertion that held all afternoon fails at 00:01. A date-sensitive test
pins the service to the day its fixture was built for.

A `date` subclass rather than a `MagicMock`: the service still constructs
dates and calls `isinstance(x, date)`, which raises when `date` is a mock.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch


@contextmanager
def report_today(today: date) -> Iterator[date]:
    """`date.today()` inside the report service and report_basics returns `today`."""

    class _Pinned(date):
        @classmethod
        def today(cls) -> date:
            return today

    # report_basics too: its free functions (Income by Source, the savings-rate
    # contributors) read the clock the same way the service's methods do.
    with (
        patch("igab.services.report_service.date", _Pinned),
        patch("igab.services.report_basics.date", _Pinned),
    ):
        yield today
