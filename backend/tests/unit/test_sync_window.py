"""The request window, and the 2,247-day request that provoked it."""

from datetime import UTC, datetime, timedelta

from igab.domain.sync_window import (
    SIMPLEFIN_MAX_WINDOW_DAYS,
    SYNC_OVERLAP_DAYS,
    backfill_windows,
    live_window,
)

NOW = datetime(2026, 9, 16, 1, 0, tzinfo=UTC)


class TestLiveWindow:
    def test_six_years_of_history_does_not_widen_the_window(self):
        """The regression: a YNAB backfill moved the oldest cleared row to
        2020 and every sync then asked for 2,247 days. The window now follows
        the last sync, and history has no say in it at all."""
        window = live_window(now=NOW, last_sync_at=NOW - timedelta(days=1), first_sync=False)
        assert (NOW - window.start).days <= SYNC_OVERLAP_DAYS + 1
        assert window.end is None

    def test_never_exceeds_the_bridge_cap(self):
        for days_since_sync in (0, 1, 30, 89, 90, 365, 2247):
            window = live_window(
                now=NOW,
                last_sync_at=NOW - timedelta(days=days_since_sync),
                first_sync=False,
            )
            assert (NOW - window.start).days <= SIMPLEFIN_MAX_WINDOW_DAYS, days_since_sync

    def test_a_dormant_connection_is_floored_not_widened(self):
        window = live_window(now=NOW, last_sync_at=NOW - timedelta(days=400), first_sync=False)
        assert window.start == NOW - timedelta(days=SIMPLEFIN_MAX_WINDOW_DAYS)

    def test_first_sync_takes_the_full_cap(self):
        window = live_window(now=NOW, last_sync_at=None, first_sync=True)
        assert window.start == NOW - timedelta(days=SIMPLEFIN_MAX_WINDOW_DAYS)

    def test_never_synced_takes_the_full_cap(self):
        """No `last_sync_at` to anchor to, even if the flag says otherwise."""
        window = live_window(now=NOW, last_sync_at=None, first_sync=False)
        assert window.start == NOW - timedelta(days=SIMPLEFIN_MAX_WINDOW_DAYS)

    def test_incremental_window_overlaps_the_previous_run(self):
        """The bridge asks for ~5 days of overlap so a late-posted row dated
        before the last run is not missed."""
        last = NOW - timedelta(days=2)
        window = live_window(now=NOW, last_sync_at=last, first_sync=False)
        assert window.start == last - timedelta(days=SYNC_OVERLAP_DAYS)

    def test_live_window_sends_no_end_date(self):
        """The protocol's upper bound is exclusive, so naming today would drop
        today's transactions."""
        assert live_window(now=NOW, last_sync_at=NOW, first_sync=False).end is None


class TestBackfillWindows:
    def test_tiles_are_contiguous_and_within_the_cap(self):
        windows = backfill_windows(now=NOW, earliest_wanted=NOW - timedelta(days=400))
        assert windows
        for w in windows:
            assert (w.end - w.start).days <= SIMPLEFIN_MAX_WINDOW_DAYS + 1
        # Newest first, each starting where the previous one began.
        for earlier, later in zip(windows, windows[1:]):
            assert later.end == earlier.start + timedelta(days=1)

    def test_tiles_cover_the_whole_span(self):
        earliest = NOW - timedelta(days=400)
        windows = backfill_windows(now=NOW, earliest_wanted=earliest)
        assert min(w.start for w in windows) == earliest
        assert max(w.end for w in windows) == NOW + timedelta(days=1)

    def test_every_tile_names_an_exclusive_end_date(self):
        """Without the extra day the boundary day falls between two tiles."""
        windows = backfill_windows(now=NOW, earliest_wanted=NOW - timedelta(days=100))
        assert all(w.end is not None for w in windows)
        assert windows[0].end == NOW + timedelta(days=1)

    def test_nothing_to_backfill_is_no_requests(self):
        assert backfill_windows(now=NOW, earliest_wanted=NOW) == []
        assert backfill_windows(now=NOW, earliest_wanted=NOW + timedelta(days=5)) == []

    def test_a_short_span_is_one_request(self):
        assert len(backfill_windows(now=NOW, earliest_wanted=NOW - timedelta(days=10))) == 1
