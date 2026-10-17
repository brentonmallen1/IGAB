"""How wide a window to ask the SimpleFIN bridge for.

The bridge documents a hard limit — "The date range of requests to /accounts
(i.e. difference between start-date and end-date) is limited to 90 days at a
time" — and answers an over-wide request with
`gen.api: "Requested date range exceeds limit of 90 days and was capped."`

This app asked for 2,247 days on every sync. The window was anchored to the
*oldest* cleared row on the account, so a YNAB backfill of six years of
history moved the anchor to 2020 and left it there, while `last_sync_at` —
maintained on both the connection and the account — was never read at all.

The bridge also asks that consecutive windows overlap: "Overlap the date
window of transactions you fetch by about 5 days to make sure you don't miss
transactions." A bank can post a transaction dated before the last sync ran.

Pure on purpose: it takes `now` rather than reading the clock, so every
branch is a one-line test.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

#: The bridge's documented cap. Not a tuning knob — requests wider than this
#: are capped server-side, silently as far as the transaction data goes.
SIMPLEFIN_MAX_WINDOW_DAYS = 90

#: The bridge's documented recommendation, so a row posted with a date just
#: before the last run is not missed.
SYNC_OVERLAP_DAYS = 5


@dataclass(frozen=True)
class SyncWindow:
    """What to send as `start-date` / `end-date`.

    `end` is None for the live window, which deliberately sends no
    `end-date` at all: the implied range stays inside the cap, and the
    protocol's upper bound is **exclusive** ("transactions ... before, but
    not on"), so naming today's date would drop today's transactions.
    """

    start: datetime
    end: datetime | None = None


def live_window(
    *,
    now: datetime,
    last_sync_at: datetime | None,
    first_sync: bool,
    oldest_open_hold: date | None,
) -> SyncWindow:
    """The window for an ordinary sync: recent activity, never more than the cap.

    A first sync takes the full 90 days, which is as far back as the bridge
    will answer in one request. Afterwards the window starts a few days
    before the last successful run — and is still floored at 90 days, so a
    connection dormant for a year cannot ask for a year.

    `oldest_open_hold` is the earliest row still linked to a bank record the
    bank has not posted (`txn_filters.linked_to_a_hold`). The window reaches
    back to cover it, because a row outside the window is never judged
    (`judged_from`): a hotel hold authorised eight days ago and dropped today
    sat three days before an hourly sync's window, and stayed pending in the
    register for good — no later window ever reached back to it. Covering the
    hold costs nothing but a longer answer to the same one request. Still
    floored at the cap: a hold older than 90 days cannot be asked about, and
    stays as it is.
    """
    floor = now - timedelta(days=SIMPLEFIN_MAX_WINDOW_DAYS)
    if first_sync or last_sync_at is None:
        return SyncWindow(start=floor)
    start = last_sync_at - timedelta(days=SYNC_OVERLAP_DAYS)
    if oldest_open_hold is not None:
        start = min(start, datetime.combine(oldest_open_hold, time.min, tzinfo=UTC))
    return SyncWindow(start=max(start, floor))


def judged_from(window_start: datetime) -> date:
    """The first day a feed fetched from `window_start` covers whole.

    Only rows dated on or after this day may be judged by their absence from
    the feed. The request names a moment, not a day, and the bridge filters
    by that moment: a row posted at 08:00 on the start day of a window that
    began at 14:00 is not in the answer, and was not dropped by the bank. Feed
    dates are UTC days (`simplefin_service._feed_record`), so this is too.
    Absence outside the window is not evidence of anything — the bank was
    simply not asked.
    """
    start = window_start.astimezone(UTC)
    if start.time() == time.min:
        return start.date()
    return start.date() + timedelta(days=1)


def backfill_windows(*, now: datetime, earliest_wanted: datetime) -> list[SyncWindow]:
    """Tile a long history into requests the bridge will actually answer.

    Contiguous, newest first, each at most the cap wide. Every tile names an
    explicit `end-date` one day past its last day, because the bound is
    exclusive — without that the boundary day's transactions are dropped from
    both the tile that ends there and the one that starts there.

    Each tile costs one request against IGAB's daily request budget
    (`integrations/simplefin/limits.py`: twelve all-accounts and twelve
    per-account, under the bridge's own ask of 24 or fewer a day), so this
    is an explicit action the user asks for, never something a sync does on
    its own.
    """
    if earliest_wanted >= now:
        return []
    windows: list[SyncWindow] = []
    span = timedelta(days=SIMPLEFIN_MAX_WINDOW_DAYS)
    end = now
    while end > earliest_wanted:
        start = max(end - span, earliest_wanted)
        windows.append(SyncWindow(start=start, end=end + timedelta(days=1)))
        end = start
    return windows
