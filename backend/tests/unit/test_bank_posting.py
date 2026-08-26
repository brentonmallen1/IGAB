"""The one bank-posting rule — domain.bank_posting — one case per cell of its
table, plus the drop-unchanged and never-blank guarantees.

The two sync paths that used to each spell this rule are pinned by name in
test_simplefin_sync.py; this file pins the rule itself.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from igab.domain.bank_posting import Apply, FeedRecord, Review, RowState, posting_updates

D = Decimal
JUL_10 = date(2026, 7, 10)
JUL_12 = date(2026, 7, 12)


def row(**over) -> RowState:
    base = dict(
        cleared="uncleared",
        amount=D("-50.00"),
        date=JUL_10,
        entered_date=None,
        entered_amount=None,
        bank_posted_date=None,
        bank_amount=None,
        bank_payee=None,
        import_description=None,
        sync_id=None,
        sync_source=None,
        has_sync_source=False,
        is_split=False,
        is_transfer_leg=False,
    )
    base.update(over)
    return RowState(**base)


def feed(**over) -> FeedRecord:
    base = dict(
        amount=D("-50.00"),
        date=JUL_12,
        posted=True,
        payee="CORNER MARKET",
        description="CORNER MARKET POS",
        sync_id="t-1",
    )
    base.update(over)
    return FeedRecord(**base)


def apply(r: RowState, f: FeedRecord, *, confirmed: bool = False) -> dict:
    out = posting_updates(r, f, confirmed=confirmed)
    assert isinstance(out, Apply), out
    return out.updates


PROVENANCE = {
    "sync_source": "simplefin",
    "has_sync_source": True,
    "bank_amount": D("-50.00"),
    "sync_id": "t-1",
    "bank_payee": "CORNER MARKET",
    "import_description": "CORNER MARKET POS",
}


# ── a pending feed record changes nothing but provenance ────────────────────


def test_pending_feed_changes_no_money_or_cleared():
    for cleared in ("pending", "uncleared", "cleared", "reconciled"):
        updates = apply(row(cleared=cleared), feed(posted=False))
        assert set(updates) <= set(PROVENANCE), cleared
        assert "bank_posted_date" not in updates


# ── a bank-created pending row takes the bank's posted values ───────────────


def test_pending_row_posts_with_bank_values_and_records_entered_date_once():
    updates = apply(row(cleared="pending", amount=D("-20.00")), feed(amount=D("-23.50")))
    assert updates["cleared"] == "cleared"
    assert updates["amount"] == D("-23.50")
    assert updates["entered_amount"] == D("-20.00")
    assert updates["date"] == JUL_12
    assert updates["entered_date"] == JUL_10
    assert updates["bank_posted_date"] == JUL_12


def test_pending_row_keeps_the_first_entered_values():
    updates = apply(
        row(
            cleared="pending",
            amount=D("-20.00"),
            entered_date=date(2026, 7, 1),
            entered_amount=D("-1"),
        ),
        feed(amount=D("-23.50")),
    )
    assert "entered_date" not in updates and "entered_amount" not in updates


def test_pending_row_same_amount_just_clears():
    updates = apply(row(cleared="pending", date=JUL_12), feed())
    assert updates["cleared"] == "cleared"
    assert "amount" not in updates and "date" not in updates


# ── a user-entered row keeps its date; a changed amount is a question ───────


def test_uncleared_row_clears_on_same_amount_and_keeps_user_date():
    updates = apply(row(cleared="uncleared"), feed())
    assert updates["cleared"] == "cleared"
    assert "date" not in updates and "amount" not in updates
    assert updates["bank_posted_date"] == JUL_12


def test_uncleared_row_with_changed_amount_is_a_review_not_an_update():
    out = posting_updates(row(cleared="uncleared"), feed(amount=D("-60.00")), confirmed=False)
    assert isinstance(out, Review)
    assert "-60.00" in out.reason and "-50.00" in out.reason


def test_confirmed_review_applies_bank_amount_and_records_entered_amount():
    updates = apply(row(cleared="uncleared"), feed(amount=D("-60.00")), confirmed=True)
    assert updates["amount"] == D("-60.00")
    assert updates["entered_amount"] == D("-50.00")
    assert updates["cleared"] == "cleared"
    assert "date" not in updates, "the user's ledger date is never touched"


def test_cleared_row_gets_provenance_only_on_same_amount():
    updates = apply(row(cleared="cleared"), feed())
    assert "cleared" not in updates and "amount" not in updates
    assert updates["bank_posted_date"] == JUL_12


def test_cleared_row_with_changed_amount_is_a_review_too():
    out = posting_updates(row(cleared="cleared"), feed(amount=D("-60.00")), confirmed=False)
    assert isinstance(out, Review)
    updates = apply(row(cleared="cleared"), feed(amount=D("-60.00")), confirmed=True)
    assert updates["amount"] == D("-60.00") and "cleared" not in updates


# ── structured rows never take an amount, even confirmed ────────────────────


def test_uncleared_split_parent_keeps_amount_and_says_so():
    out = posting_updates(row(is_split=True), feed(amount=D("-60.00")), confirmed=True)
    assert isinstance(out, Review) and "lines" in out.reason


def test_transfer_leg_keeps_amount():
    out = posting_updates(row(is_transfer_leg=True), feed(amount=D("-60.00")), confirmed=True)
    assert isinstance(out, Review) and "transfer" in out.reason


def test_split_parent_same_amount_still_clears():
    assert apply(row(is_split=True), feed())["cleared"] == "cleared"


# ── reconciled rows: provenance only, whatever the feed says ────────────────


def test_reconciled_row_strips_locked_fields():
    updates = apply(row(cleared="reconciled"), feed(amount=D("-60.00")), confirmed=True)
    assert not ({"amount", "date", "cleared", "account_id"} & updates.keys())
    assert updates["bank_amount"] == D("-60.00")
    assert updates["bank_posted_date"] == JUL_12


# ── never blank, never rewrite what is already there ────────────────────────


def test_feed_without_description_or_payee_blanks_nothing():
    updates = apply(
        row(bank_payee="OLD PAYEE", import_description="OLD DESC"),
        feed(payee=None, description=None),
    )
    assert "bank_payee" not in updates and "import_description" not in updates


def test_unchanged_values_are_dropped():
    already = row(
        cleared="cleared",
        bank_posted_date=JUL_12,
        bank_amount=D("-50.00"),
        bank_payee="CORNER MARKET",
        import_description="CORNER MARKET POS",
        sync_id="t-1",
        sync_source="simplefin",
        has_sync_source=True,
    )
    assert apply(already, feed()) == {}


def test_feed_record_from_a_bank_row_prefers_its_bank_values():
    loser = SimpleNamespace(
        bank_amount=D("-60.00"),
        amount=D("-59.00"),
        bank_posted_date=JUL_12,
        date=JUL_10,
        cleared="cleared",
        bank_payee="BANK PAYEE",
        import_description="DESC",
        sync_id="t-9",
        sync_source="simplefin",
    )
    f = FeedRecord.from_transaction(loser)
    assert f.amount == D("-60.00") and f.date == JUL_12 and f.posted and f.sync_id == "t-9"
    bare = SimpleNamespace(
        bank_amount=None,
        amount=D("-1"),
        bank_posted_date=None,
        date=JUL_10,
        cleared="pending",
        bank_payee=None,
        import_description=None,
        sync_id=None,
        sync_source=None,
    )
    g = FeedRecord.from_transaction(bare)
    assert g.amount == D("-1") and g.date == JUL_10 and not g.posted and g.source == "simplefin"
