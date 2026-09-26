"""The day a report is read on: the reader's, whenever there is a reader.

The server cannot work that day out. It does not know the reader's timezone,
and the container runs on UTC, so from 8pm Eastern its clock is already in
tomorrow — and on a month's last evening, in next month. Every report that
ends "today" or leaves the running month out read that clock: at 9pm on
31 August, Net Worth drew a September point, Income by Source called August
complete and averaged it in with an evening still to go, and the Overview's
net-worth card (reader-dated) sat beside a chart that was not.

The browser sends its own date as `client_today` (`api/v1/params.ReaderToday`),
and every report service takes it as `today`. A caller with no reader — the
AI tools without one, a scheduled job, a test — falls back to the server's
day, and falls back here, once, so no report grows a clock of its own.

Server-local `date.today()`, the clock the reports have always read: in the
container that is UTC, where it agrees with `utils/clock.today_utc`.
"""

from datetime import date


def reader_today(today: date | None) -> date:
    """`today` when a reader sent one, else the server's day."""
    return today or date.today()
