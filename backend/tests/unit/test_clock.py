"""Which clock stamps a date the user just recorded.

Pure, so every branch is a one-line test (CLAUDE.md — split pure from wired).
The wiring — that all four date-stamping endpoints actually ask this — is
`tests/integration/test_client_today.py`.
"""

import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from igab.utils.clock import recorded_on, today_server_local, today_utc


class TestRecordedOn:
    def test_an_explicit_date_wins_over_everything(self):
        """They picked a date, so today is not the question."""
        assert recorded_on(date(2026, 3, 4), date(2026, 9, 1)) == date(2026, 3, 4)

    def test_the_callers_today_beats_the_servers(self):
        """The whole point: the browser knows the timezone and the server does
        not. An asset valued on Tuesday night in Seattle is dated Tuesday even
        though the server's UTC clock already says Wednesday."""
        theirs = today_utc() - timedelta(days=1)
        assert recorded_on(None, theirs) == theirs

    def test_the_server_clock_is_the_last_resort(self):
        """An API caller outside the browser sent neither; it still gets a
        date, just the server's own."""
        assert recorded_on(None, None) == today_utc()

    def test_an_explicit_date_wins_even_with_no_client_today(self):
        assert recorded_on(date(2020, 1, 1), None) == date(2020, 1, 1)


class TestTodayServerLocal:
    """The household's day for the nightly run: `TZ` decides it, not UTC."""

    @pytest.fixture
    def zone(self, monkeypatch):
        def use(name: str) -> None:
            monkeypatch.setenv("TZ", name)
            time.tzset()

        yield use
        monkeypatch.undo()
        time.tzset()

    def test_follows_tz(self, zone):
        for name in ("Pacific/Kiritimati", "Etc/GMT+12", "America/Chicago", "UTC"):
            zone(name)
            assert today_server_local() == datetime.now(ZoneInfo(name)).date(), name

    def test_two_zones_a_day_apart_disagree_where_utc_could_not(self, zone):
        # UTC+14 and UTC-12 are 26 hours apart, so they never share a date.
        zone("Pacific/Kiritimati")
        east = today_server_local()
        zone("Etc/GMT+12")
        west = today_server_local()
        assert east > west
