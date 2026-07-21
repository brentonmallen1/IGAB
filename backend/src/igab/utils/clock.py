"""UTC-anchored date helpers.

`date.today()` is server-local; a self-hosted box in any timezone would
stamp transaction dates and rate-limit day boundaries inconsistently with
the app's UTC-based reset messaging. Use these instead.
"""

from datetime import UTC, date, datetime


def today_utc() -> date:
    return datetime.now(UTC).date()
