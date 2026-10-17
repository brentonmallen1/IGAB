"""The dismissal key: one per due date and state, parsed back, pruned by age —
and the third state, a bill somebody marked paid."""

import uuid
from datetime import date, timedelta

from igab.domain.payment_due import PAYMENT_WINDOW_DAYS
from igab.services.card_due_dismissals import (
    Dismissal,
    dismissal_key,
    expired_keys,
    parse_dismissal_key,
)

CARD = uuid.UUID("7d3f6c1e-2b4a-4e8f-9a01-5c6d7e8f9a0b")


def test_keys_fit_the_column():
    # guide_state.key is String(60); the longer spelling is the past-due one.
    assert len(dismissal_key(CARD, date(2026, 10, 3), "past_due")) <= 60


def test_due_and_past_due_are_different_keys():
    due = dismissal_key(CARD, date(2026, 10, 3), "due")
    past = dismissal_key(CARD, date(2026, 10, 3), "past_due")
    assert due == f"due:{CARD}:2026-10-03"
    assert past == f"due:{CARD}:2026-10-03:past"


def test_a_paid_bill_is_its_own_key():
    # Not a dismissal of a reminder: the client's rule reads it as a payment.
    key = dismissal_key(CARD, date(2026, 10, 3), "paid")
    assert key == f"paid:{CARD}:2026-10-03"
    assert len(key) <= 60


def test_a_key_parses_back():
    for state in ("due", "past_due", "paid"):
        key = dismissal_key(CARD, date(2026, 10, 3), state)
        assert parse_dismissal_key(key) == Dismissal(CARD, date(2026, 10, 3), state)


def test_other_keys_are_not_dismissals():
    for key in (
        "prefs",
        "step:starter-fund",
        "reports:favorites",
        "notice:tags",
        "due:",
        "due:x:y",
        "paid:",
        f"paid:{CARD}",
        f"paid:{CARD}:2026-13-40",
        "paid:not-a-uuid:2026-10-03",
    ):
        assert parse_dismissal_key(key) is None


def test_expired_keys_are_more_than_60_days_old():
    today = date(2026, 9, 27)
    old = dismissal_key(CARD, date(2026, 7, 28), "due")
    edge = dismissal_key(CARD, date(2026, 7, 29), "past_due")
    fresh = dismissal_key(CARD, date(2026, 10, 3), "due")
    assert expired_keys([old, edge, fresh, "prefs"], today) == [old]


def test_a_paid_bill_is_kept_as_long_as_the_payment_window():
    """The client walks every due date in the served payment window, so an
    acknowledgement lasts as long as its bill can still be in the walk. A
    quarterly bill is older than 60 days while it is still the latest one;
    pruned at 60, it would come back as past due."""
    today = date(2026, 9, 27)
    quarter_old = dismissal_key(CARD, date(2026, 7, 1), "paid")
    edge = dismissal_key(CARD, today - timedelta(days=PAYMENT_WINDOW_DAYS), "paid")
    gone = dismissal_key(CARD, today - timedelta(days=PAYMENT_WINDOW_DAYS + 1), "paid")
    assert expired_keys([quarter_old, edge, gone], today) == [gone]
