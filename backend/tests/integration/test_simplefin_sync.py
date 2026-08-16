"""SimpleFIN sync dedup, pending→posted, date policy, and the accept-match
flow — all against a real database.

Date policy: a matched transaction keeps the user's ledger date (budget
months follow it); the bank's posted date is preserved as bank_posted_date
metadata. Only rows the sync itself created adopt bank values wholesale
(pending→posted amount/date updates).

Matching ladder: candidates are searched in a ±10 day window, but auto-
matching is confined to ±5 days — strong payee similarity auto-matches there;
exact amount within ±1 day auto-matches regardless of payee when unambiguous;
any remaining exact-amount candidate (including settlement-lagged ones out to
±10 days) forces a review match — never a silent duplicate.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from igab.db.models import Transaction
from igab.domain.exceptions import InvariantViolation
from igab.services.simplefin_service import SimpleFINService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_simplefin_connection,
    create_transaction,
    create_user,
    make_services,
)

SF_ACCT = "sf-acct-1"


class FakeClient:
    def __init__(self, payload: list[dict]):
        self.payload = payload

    async def get_transactions(self, access_url: str, since=None) -> list[dict]:
        return self.payload

    async def get_accounts(self, access_url: str) -> list[dict]:
        return []


def _ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 12, tzinfo=UTC).timestamp())


def bank_txn(
    txn_id: str | None,
    amount: str,
    on: date,
    *,
    posted: bool = True,
    payee: str = "CORNER MARKET",
) -> dict:
    t: dict = {
        "account_id": SF_ACCT,
        "amount": amount,
        "payee": payee,
        "description": f"{payee} POS PURCHASE",
    }
    if txn_id is not None:
        t["id"] = txn_id
    if posted:
        t["posted"] = _ts(on)
    else:
        t["posted"] = 0
        t["transacted_at"] = _ts(on)
    return t


async def _sync_setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(
        db_session, budget, "Checking", simplefin_account_id=SF_ACCT
    )
    conn = await create_simplefin_connection(db_session, user)
    return services, user, budget, account, conn


def _service(services, payload: list[dict]) -> SimpleFINService:
    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = FakeClient(payload)
    return svc


async def _live_rows(db_session, account_id) -> list[Transaction]:
    rows = (
        (
            await db_session.execute(
                select(Transaction).where(
                    Transaction.account_id == account_id,
                    Transaction.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


PATCH_DECRYPT = patch(
    "igab.services.simplefin_service.decrypt", return_value="https://u:p@x.test"
)


async def test_sync_idempotent_same_payload_twice(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [
        bank_txn("t-1", "-12.50", today - timedelta(days=1)),
        bank_txn("t-2", "-40.00", today),
    ]
    svc = _service(services, payload)

    with PATCH_DECRYPT:
        first = await svc.sync(conn.id, budget.id)
        second = await svc.sync(conn.id, budget.id)

    assert first.get("error") is None, first
    assert first["imported"] == 2
    assert second["imported"] == 0
    assert len(await _live_rows(db_session, account.id)) == 2


async def test_pending_to_posted_updates_amount_date_cleared(db_session):
    """The classic tip scenario: -20.00 auth posts as -23.50 a day later."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    auth_day = date.today() - timedelta(days=2)
    post_day = date.today() - timedelta(days=1)

    svc = _service(services, [bank_txn("t-9", "-20.00", auth_day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1
    assert rows[0].cleared == "pending"
    assert await services.account_repo.get_balance(account.id) == Decimal("0")

    svc.client = FakeClient([bank_txn("t-9", "-23.50", post_day, posted=True)])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1, "pending→posted must update in place, not duplicate"
    txn = rows[0]
    assert txn.cleared == "cleared"
    assert txn.amount == Decimal("-23.50")
    assert txn.date == post_day
    assert txn.entered_date == auth_day, "prior date preserved as provenance"
    assert txn.bank_posted_date == post_day
    assert result["cleared"] == 1
    assert await services.account_repo.get_balance(account.id) == Decimal("-23.50")


async def test_fuzzy_automatch_keeps_user_date_and_stamps_bank_posted_date(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    user_day = date.today() - timedelta(days=3)
    bank_day = date.today() - timedelta(days=1)

    payee = await services.payee_repo.find_or_create(budget.id, "Corner Market")
    manual = await create_transaction(
        db_session, budget, account, "-50.00", user_day, payee=payee, cleared="uncleared"
    )

    svc = _service(services, [bank_txn("t-77", "-50.00", bank_day, payee="CORNER MARKET #12")])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 0, "high-confidence match must attach, not import"
    assert result["matched"] == 1
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1
    txn = rows[0]
    assert txn.id == manual.id
    assert txn.sync_id == "t-77"
    assert txn.sync_source == "simplefin"
    assert txn.date == user_day, "the user's ledger date is kept — budget months follow it"
    assert txn.entered_date is None, "no date was rewritten, so no provenance copy"
    assert txn.bank_posted_date == bank_day, "bank posted date preserved as metadata"
    assert txn.cleared == "cleared"


async def test_renamed_payee_same_day_exact_amount_auto_matches(db_session):
    """The Bread Financial regression: the user renamed the payee in YNAB so
    it shares no words with the bank descriptor. Exact amount + same day must
    absorb the bank row instead of silently creating a duplicate — 36 of
    these summed to a -$13k balance error on first real sync."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=4)

    group = await create_category_group(db_session, budget)
    cat = await create_category(db_session, budget, group)
    payee = await create_payee(db_session, budget, "Bread Financial")
    manual = await create_transaction(
        db_session, budget, account, "-320.35", day,
        payee=payee, category=cat, cleared="reconciled",
    )

    svc = _service(
        services, [bank_txn("t-320", "-320.35", day, payee="COMENITY PAY VI WEB PYMT")]
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 0
    assert result["matched"] == 1
    assert result["review_queued"] == 0
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1, "no silent duplicate"
    txn = rows[0]
    assert txn.id == manual.id
    assert txn.sync_id == "t-320"
    assert txn.cleared == "reconciled", "reconciled state untouched"
    assert txn.category_id == cat.id, "categorization untouched"
    assert txn.date == day
    assert txn.bank_posted_date == day


async def test_equal_amount_same_day_pair_matches_one_to_one(db_session):
    """Two -10.00 rows in YNAB, two -10.00 rows in the feed (recurring
    purchase): each feed row must consume a distinct existing row."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=1)
    payee = await create_payee(db_session, budget, "Lidl")
    m1 = await create_transaction(
        db_session, budget, account, "-10.00", day, payee=payee, cleared="cleared"
    )
    m2 = await create_transaction(
        db_session, budget, account, "-10.00", day, payee=payee, cleared="cleared"
    )

    payload = [
        bank_txn("t-a", "-10.00", day, payee="LIDL #123"),
        bank_txn("t-b", "-10.00", day, payee="LIDL #123"),
    ]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["matched"] == 2
    assert result["imported"] == 0
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 2
    assert {r.id for r in rows} == {m1.id, m2.id}
    assert {r.sync_id for r in rows} == {"t-a", "t-b"}, "each row got a distinct bank identity"


async def test_idless_identical_feed_rows_do_not_collapse(db_session):
    """Same-run guard: the row created for the first id-less feed row must not
    absorb the second identical one — the feed says two transactions exist."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today()
    payload = [
        bank_txn(None, "-6.50", day, payee="ALPHA STORE"),
        bank_txn(None, "-6.50", day, payee="ALPHA STORE"),
    ]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 2
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 2, "identical id-less rows must both survive"


async def test_weak_payee_outside_tight_window_creates_with_review_match(db_session):
    """Silent-duplicate regression: an exact-amount candidate 3 days away with
    a dissimilar payee is genuinely uncertain. The bank row imports, but a
    pending review match MUST exist — silence is how duplicates were born."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    user_day = date.today() - timedelta(days=4)
    bank_day = date.today() - timedelta(days=1)

    payee = await create_payee(db_session, budget, "Bread Financial")
    manual = await create_transaction(
        db_session, budget, account, "-320.35", user_day, payee=payee, cleared="cleared"
    )

    svc = _service(
        services,
        [bank_txn("t-rev", "-320.35", bank_day, payee="COMENITY PAY VI WEB PYMT")],
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 1
    assert result["review_queued"] == 1
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 2
    matches = await services.match_repo.get_pending_for_account(account.id)
    assert len(matches) == 1
    assert matches[0].manual_transaction_id == manual.id


async def test_two_distinct_same_day_same_amount_bank_txns_import_as_two(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [
        bank_txn("t-a", "-5.75", today, payee="STARBUCKS #111"),
        bank_txn("t-b", "-5.75", today, payee="STARBUCKS #111"),
    ]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 2
    assert len(await _live_rows(db_session, account.id)) == 2


async def test_missing_bank_id_does_not_false_dedup(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [
        bank_txn(None, "-10.00", today, payee="ALPHA STORE"),
        bank_txn(None, "-99.00", today, payee="BETA STORE"),
    ]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 2, "id-less rows must never dedup against each other"
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 2
    assert all(r.sync_id is None for r in rows)


async def test_ambiguous_pair_creates_review_match_then_accept_no_reimport_loop(db_session):
    """Genuine ambiguity: two payee-less -80.00 rows one day before the bank
    row. Guessing would corrupt one of them, so the bank row imports with a
    review match; accepting merges (keeping the user's date) and re-syncing
    must not re-import the bank transaction."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    user_day = date.today() - timedelta(days=2)
    bank_day = date.today() - timedelta(days=1)

    manual_a = await create_transaction(
        db_session, budget, account, "-80.00", user_day, cleared="uncleared"
    )
    manual_b = await create_transaction(
        db_session, budget, account, "-80.00", user_day, cleared="uncleared"
    )

    payload = [bank_txn("t-55", "-80.00", bank_day, payee="MYSTERY VENDOR")]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 1, "ambiguity imports and asks the user"
    assert result["review_queued"] == 1
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 3

    matches = await services.match_repo.get_pending_for_account(account.id)
    assert len(matches) == 1
    match = matches[0]
    assert match.manual_transaction_id in (manual_a.id, manual_b.id)

    await services.matching.accept_match(match.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 2, "accepting merges the pair down; the other manual row survives"
    keeper = next(r for r in rows if r.id == match.manual_transaction_id)
    assert keeper.sync_id == "t-55", "bank identity must survive the merge"
    assert keeper.has_sync_source is True
    assert keeper.cleared == "cleared"
    assert keeper.date == user_day, "the user's date survives the accept-merge"
    assert keeper.bank_posted_date == bank_day, "bank posted date inherited as metadata"

    with PATCH_DECRYPT:
        again = await svc.sync(conn.id, budget.id)
    assert again["imported"] == 0, "sync_id on the keeper prevents the reimport loop"
    assert len(await _live_rows(db_session, account.id)) == 2


async def test_accept_keeps_reconciled_side(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()

    reconciled = await create_transaction(
        db_session, budget, account, "-30.00", today - timedelta(days=2), cleared="reconciled"
    )
    newer = await create_transaction(
        db_session, budget, account, "-30.00", today, cleared="cleared", sync_id="t-x",
        sync_source="simplefin",
    )
    match = await services.match_repo.create(
        synced_transaction_id=reconciled.id,
        manual_transaction_id=newer.id,
        confidence_score=0.7,
    )

    await services.matching.accept_match(match.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1
    keeper = rows[0]
    assert keeper.id == reconciled.id, "the reconciled row must never be deleted"
    assert keeper.cleared == "reconciled"
    assert keeper.sync_id == "t-x", "bank identity copied onto the reconciled keeper"


async def test_accept_both_reconciled_rejected(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    a = await create_transaction(
        db_session, budget, account, "-30.00", today, cleared="reconciled"
    )
    b = await create_transaction(
        db_session, budget, account, "-30.00", today - timedelta(days=1), cleared="reconciled"
    )
    match = await services.match_repo.create(
        synced_transaction_id=a.id, manual_transaction_id=b.id, confidence_score=0.6
    )

    with pytest.raises(InvariantViolation):
        await services.matching.accept_match(match.id)

    assert len(await _live_rows(db_session, account.id)) == 2


async def test_stale_pending_swept_when_absent_from_feed(db_session):
    """Bank dropped an auth (or re-identified it at posting): the phantom
    pending row must not linger forever."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    auth_day = date.today() - timedelta(days=2)

    svc = _service(services, [bank_txn("t-old", "-15.00", auth_day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    assert len(await _live_rows(db_session, account.id)) == 1

    # Next sync: the auth vanished; a differently-identified posted txn with a
    # different amount appears (classic id-change-at-posting).
    svc.client = FakeClient([bank_txn("t-new", "-17.00", date.today(), posted=True)])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1, "stale pending swept; posted row imported"
    assert rows[0].sync_id == "t-new"
    assert rows[0].amount == Decimal("-17.00")
    assert result.get("removed_pending") == 1


async def test_manual_pending_rows_not_swept(db_session):
    """The sweep only touches sync-created pendings, never user rows."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    manual_pending = await create_transaction(
        db_session, budget, account, "-33.00", date.today(), cleared="pending"
    )
    assert manual_pending.sync_source is None

    svc = _service(services, [bank_txn("t-z", "-1.00", date.today())])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    rows = await _live_rows(db_session, account.id)
    ids = {r.id for r in rows}
    assert manual_pending.id in ids, "manual pending row must survive the sweep"


async def test_duplicate_sync_id_within_one_payload_imports_once(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [
        bank_txn("t-dup", "-8.00", today),
        bank_txn("t-dup", "-8.00", today),
    ]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 1
    assert len(await _live_rows(db_session, account.id)) == 1


async def test_unique_index_blocks_duplicate_live_sync_id(db_session):
    """DB-level backstop: two live rows with the same (account, sync_id) are
    impossible; a soft-deleted duplicate is allowed."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    await create_transaction(
        db_session, budget, account, "-1.00", today, sync_id="dup-1", sync_source="simplefin"
    )
    await create_transaction(
        db_session, budget, account, "-2.00", today, sync_id="dup-1",
        sync_source="simplefin", is_deleted=True,
    )

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await create_transaction(
            db_session, budget, account, "-3.00", today, sync_id="dup-1",
            sync_source="simplefin",
        )


# ─── Candidate query behavior (repo level) ────────────────────────────────────


async def test_candidate_query_window_and_sign_boundaries(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    center = date.today() - timedelta(days=10)

    at_edge = await create_transaction(
        db_session, budget, account, "-25.00", center - timedelta(days=5)
    )
    beyond_edge = await create_transaction(
        db_session, budget, account, "-25.00", center - timedelta(days=6)
    )
    sign_flipped = await create_transaction(db_session, budget, account, "25.00", center)

    found = await services.transaction_repo.find_existing_match_candidates(
        account.id, Decimal("-25.00"), center, date_window_days=5
    )
    ids = {t.id for t, _ in found}
    assert at_edge.id in ids, "±5 days is inside the window"
    assert beyond_edge.id not in ids, "±6 days is outside the window"
    assert sign_flipped.id not in ids, "amount match is sign-sensitive"


async def test_candidate_query_excludes_consumed_ids(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=10)
    a = await create_transaction(db_session, budget, account, "-25.00", day)
    b = await create_transaction(db_session, budget, account, "-25.00", day)

    found = await services.transaction_repo.find_existing_match_candidates(
        account.id, Decimal("-25.00"), day, exclude_ids={a.id}
    )
    ids = {t.id for t, _ in found}
    assert ids == {b.id}


async def test_match_candidates_exclude_bank_sourced_rows(db_session):
    """find_match_candidates feeds try_match's 'manual transaction' search —
    an id-less sync-created row is bank-sourced and must never qualify."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today()
    manual = await create_transaction(db_session, budget, account, "-6.50", day)
    idless_synced = await create_transaction(
        db_session, budget, account, "-6.50", day, sync_source="simplefin"
    )

    found = await services.transaction_repo.find_match_candidates(
        account.id, Decimal("-6.50"), day
    )
    ids = {t.id for t in found}
    assert manual.id in ids
    assert idless_synced.id not in ids


# ─── Split parents and the widened search window ──────────────────────────────


async def _make_split(db_session, budget, account, payee, day, total, leg_amounts, *,
                      cleared="cleared"):
    parent = await create_transaction(
        db_session, budget, account, total, day, payee=payee, cleared=cleared, is_split=True
    )
    for amt in leg_amounts:
        await create_transaction(
            db_session,
            budget,
            account,
            amt,
            day,
            parent_transaction_id=parent.id,
            cleared=cleared,
        )
    return parent


async def test_sync_auto_matches_split_parent_by_total(db_session):
    """The point of split reconstruction: the bank sees ONE -163.94 charge,
    and the register carries it as a split parent with exactly that total."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=3)
    payee = await create_payee(db_session, budget, "Target")
    parent = await _make_split(
        db_session, budget, account, payee, day, "-163.94", ["-74.44", "-65.00", "-24.50"]
    )

    svc = _service(services, [bank_txn("t-split", "-163.94", day, payee="TARGET T- 0423")])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["matched"] == 1
    assert result["imported"] == 0
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 4, "parent + 3 children, no duplicate"
    await db_session.refresh(parent)
    assert parent.sync_id == "t-split"
    assert parent.bank_posted_date == day
    children = [r for r in rows if r.parent_transaction_id == parent.id]
    assert len(children) == 3
    assert all(c.sync_id is None for c in children), "sync stamps the parent only"


async def test_sync_cleared_upgrade_on_split_parent_clears_children(db_session):
    """Auto-matching an uncleared split parent upgrades it to cleared — the
    children must follow, or the next reconcile strands uncleared children
    under a reconciled parent."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=3)
    payee = await create_payee(db_session, budget, "Target")
    parent = await _make_split(
        db_session, budget, account, payee, day, "-163.94",
        ["-74.44", "-65.00", "-24.50"], cleared="uncleared",
    )

    svc = _service(services, [bank_txn("t-split-u", "-163.94", day, payee="TARGET T- 0423")])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["matched"] == 1
    await db_session.refresh(parent)
    assert parent.cleared == "cleared"
    rows = await _live_rows(db_session, account.id)
    children = [r for r in rows if r.parent_transaction_id == parent.id]
    assert len(children) == 3
    assert all(c.cleared == "cleared" for c in children), (
        "children mirror the parent's cleared upgrade"
    )


async def test_sync_never_matches_split_child_amount(db_session):
    """A bank charge equal to one LEG of a split is a different purchase —
    children are invisible to matching, so it imports as its own row."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=3)
    payee = await create_payee(db_session, budget, "Target")
    parent = await _make_split(
        db_session, budget, account, payee, day, "-163.94", ["-74.44", "-65.00", "-24.50"]
    )

    svc = _service(services, [bank_txn("t-leg", "-74.44", day, payee="SOME OTHER STORE")])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 1
    assert result["matched"] == 0
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 5, "new row created; the split is untouched"
    created = next(r for r in rows if r.sync_id == "t-leg")
    assert created.parent_transaction_id is None
    children = [r for r in rows if r.parent_transaction_id == parent.id]
    assert all(c.sync_id is None for c in children)


async def test_settlement_lag_payment_queues_review_not_silent_dupe(db_session):
    """Sapphire regression: the user dates a card payment when initiated (6/15),
    the bank posts it a week later (6/22). Delta 7 was beyond the old ±5
    search window — silent duplicate. Now it must queue for review."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    user_day = date.today() - timedelta(days=9)
    post_day = date.today() - timedelta(days=2)  # 7 days after user_day
    payee = await create_payee(db_session, budget, "Sapphire")
    manual = await create_transaction(
        db_session, budget, account, "-5000.00", user_day, payee=payee, cleared="reconciled"
    )

    svc = _service(
        services, [bank_txn("t-sapphire", "-5000.00", post_day, payee="SAPPHIRE AUTOPAY PAYMENT")]
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["review_queued"] == 1
    assert result["matched"] == 0
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 2, "created visibly, never silently merged or dropped"
    created = next(r for r in rows if r.id != manual.id)
    assert created.approved is False
    matches = await services.match_repo.get_pending_for_account(account.id)
    assert len(matches) == 1
    await db_session.refresh(manual)
    assert manual.sync_id is None, "reconciled row untouched until the user decides"
    assert manual.date == user_day


async def test_identical_payee_week_apart_reviews_not_auto(db_session):
    """Weekly recurring charge hazard: same payee, same amount, 7 days apart
    is usually a DIFFERENT purchase. It must review, never auto-match."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    last_week = date.today() - timedelta(days=9)
    this_week = date.today() - timedelta(days=2)
    payee = await create_payee(db_session, budget, "Spotify")
    manual = await create_transaction(
        db_session, budget, account, "-12.99", last_week, payee=payee, cleared="cleared"
    )

    svc = _service(services, [bank_txn("t-spot", "-12.99", this_week, payee="SPOTIFY")])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["matched"] == 0, "a week of distance is never auto-matched"
    assert result["review_queued"] == 1
    await db_session.refresh(manual)
    assert manual.sync_id is None


async def test_candidate_query_production_window_boundaries(db_session):
    """The production search window: ±10 days in, ±11 out."""
    from igab.services.simplefin_service import DEDUP_DATE_WINDOW_DAYS

    services, user, budget, account, conn = await _sync_setup(db_session)
    center = date.today() - timedelta(days=15)
    at_edge = await create_transaction(
        db_session, budget, account, "-25.00", center - timedelta(days=10)
    )
    beyond_edge = await create_transaction(
        db_session, budget, account, "-25.00", center - timedelta(days=11)
    )

    found = await services.transaction_repo.find_existing_match_candidates(
        account.id, Decimal("-25.00"), center, date_window_days=DEDUP_DATE_WINDOW_DAYS
    )
    ids = {t.id for t, _ in found}
    assert at_edge.id in ids, "±10 days is inside the search window"
    assert beyond_edge.id not in ids, "±11 days is outside the search window"


async def test_nearest_candidate_survives_the_limit(db_session):
    """Six same-amount rows crowd the window on the future side; the
    exact-day row must survive LIMIT 5 (nearest-first, not latest-first)."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    center = date.today() - timedelta(days=12)
    exact = await create_transaction(db_session, budget, account, "-9.99", center)
    for days in (2, 4, 6, 8, 10):
        await create_transaction(
            db_session, budget, account, "-9.99", center + timedelta(days=days)
        )

    found = await services.transaction_repo.find_existing_match_candidates(
        account.id, Decimal("-9.99"), center, date_window_days=10
    )
    assert len(found) == 5
    ids = {t.id for t, _ in found}
    assert exact.id in ids
