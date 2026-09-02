"""UTC-anchored date helpers.

`date.today()` is server-local; a self-hosted box in any timezone would
stamp transaction dates and rate-limit day boundaries inconsistently with
the app's UTC-based reset messaging. Use these instead.
"""

from datetime import UTC, date, datetime


def today_utc() -> date:
    return datetime.now(UTC).date()


def recorded_on(explicit: date | None, client_today: date | None) -> date:
    """The date to stamp on a figure a person has just recorded.

    Three clocks, in falling order of authority:

    1. ``explicit`` — they picked a date, so today is not the question.
    2. ``client_today`` — the browser's local date. **This** is the person's
       today, and the server cannot derive it: it does not know their
       timezone, and asking its own clock answers a different question.
    3. ``today_utc()`` — last resort, for a caller that sent neither.

    Reaching (3) is a small lie every evening west of UTC, where it is
    already tomorrow: a house valued on Tuesday night was dated Wednesday,
    and the asset register said so. It stays as the fallback because an API
    caller outside the browser has no better answer, but every UI path sends
    ``client_today`` so the ledger records the day the person was living in.

    One home for this because four endpoints stamp such a date — two on
    assets, two on liabilities — and `assets.py` already describes its value
    endpoints as "near-copies of the liability balance-snapshot ones".
    """
    return explicit or client_today or today_utc()
