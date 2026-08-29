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

from igab.db.models import ChangeLog, Transaction
from igab.integrations.simplefin.client import SimpleFINFeed
from igab.domain.exceptions import InvariantViolation
from igab.services.simplefin_service import SimpleFINService
from igab.services.transaction_service import SplitSpec, TransactionUpdate
from igab.services.undo_service import UndoService

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
    def __init__(self, payload: list[dict], balances: dict[str, Decimal] | None = None):
        self.payload = payload
        self.balances = balances or {}

    async def get_feed(self, access_url: str, since=None) -> SimpleFINFeed:
        return SimpleFINFeed(transactions=self.payload, balances=dict(self.balances))

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
    account = await create_account(db_session, budget, "Checking", simplefin_account_id=SF_ACCT)
    conn = await create_simplefin_connection(db_session, user)
    return services, user, budget, account, conn


def _service(
    services, payload: list[dict], balances: dict[str, Decimal] | None = None
) -> SimpleFINService:
    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = FakeClient(payload, balances)
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


PATCH_DECRYPT = patch("igab.services.simplefin_service.decrypt", return_value="https://u:p@x.test")


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
        db_session,
        budget,
        account,
        "-320.35",
        day,
        payee=payee,
        category=cat,
        cleared="reconciled",
    )

    svc = _service(services, [bank_txn("t-320", "-320.35", day, payee="COMENITY PAY VI WEB PYMT")])
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
        db_session,
        budget,
        account,
        "-30.00",
        today,
        cleared="cleared",
        sync_id="t-x",
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
    a = await create_transaction(db_session, budget, account, "-30.00", today, cleared="reconciled")
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
        db_session,
        budget,
        account,
        "-2.00",
        today,
        sync_id="dup-1",
        sync_source="simplefin",
        is_deleted=True,
    )

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await create_transaction(
            db_session,
            budget,
            account,
            "-3.00",
            today,
            sync_id="dup-1",
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

    found = await services.transaction_repo.find_match_candidates(account.id, Decimal("-6.50"), day)
    ids = {t.id for t in found}
    assert manual.id in ids
    assert idless_synced.id not in ids


# ─── Split parents and the widened search window ──────────────────────────────


async def _make_split(
    db_session, budget, account, payee, day, total, leg_amounts, *, cleared="cleared"
):
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
        db_session,
        budget,
        account,
        payee,
        day,
        "-163.94",
        ["-74.44", "-65.00", "-24.50"],
        cleared="uncleared",
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


# ─── One posting rule (domain.bank_posting) — pinned by the divergence each
# of the sync's two paths used to have ───────────────────────────────────────


async def _link_manual_to_hold(
    db_session,
    services,
    budget,
    account,
    conn,
    *,
    amount="-50.00",
    user_payee="Corner Market",
    bank_payee="CORNER MARKET",
    sync_id="t-hold",
    via_feed=True,
):
    """A hand-typed uncleared row linked to a bank record that is still an
    auth hold: it carries the hold's id but no posted date.

    `via_feed=True` links it the way the sync does (auto-match on a similar
    payee). `via_feed=False` writes the link directly — the state an earlier
    accepted review leaves behind, which is how a row whose payee shares
    nothing with the bank's string comes to be linked at all.
    """
    day = date.today() - timedelta(days=2)
    payee = await create_payee(db_session, budget, user_payee)
    manual = await create_transaction(
        db_session, budget, account, amount, day, payee=payee, cleared="uncleared"
    )
    svc = _service(services, [bank_txn(sync_id, amount, day, posted=False, payee=bank_payee)])
    if via_feed:
        with PATCH_DECRYPT:
            first = await svc.sync(conn.id, budget.id)
        assert first["matched"] == 1, first
    else:
        manual.sync_id = sync_id
        manual.sync_source = "simplefin"
        manual.has_sync_source = True
        manual.bank_amount = Decimal(amount)
        manual.bank_payee = bank_payee
        await db_session.flush()
    await db_session.refresh(manual)
    assert manual.sync_id == sync_id and manual.cleared == "uncleared"
    assert manual.bank_posted_date is None, "linked to a hold: provisional"
    return svc, manual, day


async def test_identity_path_used_to_skip_an_uncleared_row_forever(db_session):
    """Bug A. The old identity path upgraded only `pending` rows, so a
    hand-typed row linked while the bank record was a hold stayed uncleared
    after it posted under the same id — every sync, forever."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    svc, manual, day = await _link_manual_to_hold(db_session, services, budget, account, conn)
    post_day = day + timedelta(days=1)

    svc.client = FakeClient([bank_txn("t-hold", "-50.00", post_day, posted=True)])
    with PATCH_DECRYPT:
        second = await svc.sync(conn.id, budget.id)

    assert second["cleared"] == 1 and second["imported"] == 0, second
    await db_session.refresh(manual)
    assert manual.cleared == "cleared"
    assert manual.bank_posted_date == post_day
    assert manual.date == day, "the user's ledger date is kept"
    assert manual.amount == Decimal("-50.00")
    assert len(await _live_rows(db_session, account.id)) == 1


async def test_identity_path_used_to_leave_split_children_pending(db_session):
    """A bank-created pending row the user split: when it posts under the
    same id the parent clears and its lines must follow."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=2)
    svc = _service(services, [bank_txn("t-p", "-30.00", day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [parent] = await _live_rows(db_session, account.id)
    await services.transactions.convert_to_split(
        budget.id,
        parent.id,
        [SplitSpec(amount=Decimal("-20.00")), SplitSpec(amount=Decimal("-10.00"))],
    )

    svc.client = FakeClient([bank_txn("t-p", "-30.00", day, posted=True)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    await db_session.refresh(parent)
    assert parent.cleared == "cleared"
    children = await services.transaction_repo.get_splits(parent.id)
    assert len(children) == 2
    assert all(c.cleared == "cleared" for c in children), "lines follow the parent"


async def test_auto_match_path_used_to_blank_import_description(db_session):
    """A feed record without a description used to write NULL over one the
    row already carried."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=1)
    manual = await create_transaction(
        db_session, budget, account, "-50.00", day, cleared="uncleared"
    )
    manual.import_description = "OLD DESC"
    await db_session.flush()

    bare = {"account_id": SF_ACCT, "id": "t-nd", "amount": "-50.00", "posted": _ts(day)}
    svc = _service(services, [bare])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["matched"] == 1
    await db_session.refresh(manual)
    assert manual.import_description == "OLD DESC"
    assert manual.bank_payee is None
    assert manual.cleared == "cleared"


async def test_reidentified_posting_upgrades_the_provisionally_linked_manual_row(db_session):
    """Bug B, same amount. The bank re-identifies the record at posting: the
    row holding the hold's id used to be invisible to the candidate search,
    so a duplicate imported and the user's row stayed uncleared."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    svc, manual, day = await _link_manual_to_hold(db_session, services, budget, account, conn)
    post_day = day + timedelta(days=1)

    svc.client = FakeClient([bank_txn("t-posted", "-50.00", post_day, posted=True)])
    with PATCH_DECRYPT:
        second = await svc.sync(conn.id, budget.id)

    assert second["matched"] == 1 and second["imported"] == 0, second
    assert second["removed_pending"] == 0
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1 and rows[0].id == manual.id
    await db_session.refresh(manual)
    assert manual.sync_id == "t-posted", "the row now carries the posted id"
    assert manual.cleared == "cleared" and manual.bank_posted_date == post_day


async def test_reidentified_posting_keeps_the_users_category_on_a_bank_pending_row(db_session):
    """A same-amount re-id used to sweep the pending row and import a fresh
    one — losing the category, memo and approval the user had put on it."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=2)
    group = await create_category_group(db_session, budget)
    cat = await create_category(db_session, budget, group)
    svc = _service(services, [bank_txn("t-p", "-30.00", day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [pending] = await _live_rows(db_session, account.id)
    await services.transactions.update(
        budget.id, pending.id, TransactionUpdate(category_id=cat.id, memo="lunch", approved=True)
    )

    svc.client = FakeClient([bank_txn("t-q", "-30.00", day, posted=True)])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["removed_pending"] == 0 and result["imported"] == 0
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1 and rows[0].id == pending.id
    await db_session.refresh(pending)
    assert pending.sync_id == "t-q" and pending.cleared == "cleared"
    assert pending.category_id == cat.id and pending.memo == "lunch" and pending.approved


async def test_legacy_cleared_row_without_bank_posted_date_is_not_reidentified(db_session):
    """Rows linked before bank_posted_date existed are cleared with a NULL
    posted date. They must never absorb a foreign same-amount bank id."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=1)
    legacy = await create_transaction(
        db_session,
        budget,
        account,
        "-50.00",
        day,
        cleared="cleared",
        sync_id="old-1",
        sync_source="simplefin",
    )
    svc = _service(services, [bank_txn("t-new", "-50.00", day, posted=True)])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 1 and result["matched"] == 0
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 2
    await db_session.refresh(legacy)
    assert legacy.sync_id == "old-1"


async def test_pending_feed_row_never_claims_a_provisionally_linked_row(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    svc, manual, day = await _link_manual_to_hold(db_session, services, budget, account, conn)

    svc.client = FakeClient(
        [
            bank_txn("t-hold", "-50.00", day, posted=False),
            bank_txn("t-hold2", "-50.00", day, posted=False),
        ]
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 1, "the second hold is its own pending row"
    await db_session.refresh(manual)
    assert manual.sync_id == "t-hold"
    assert len(await _live_rows(db_session, account.id)) == 2


async def _pending_matches(services, account_id):
    return await services.matching.match_repo.get_pending_for_account(account_id)


async def test_manual_row_amount_change_at_posting_queues_review_not_silent_update(db_session):
    """The user typed -50; the bank posts -60 under the same id (a tip). Never
    applied silently: the posted record becomes its own row, queued for
    review against the user's, which goes back to unlinked and uncleared."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    svc, manual, day = await _link_manual_to_hold(db_session, services, budget, account, conn)
    post_day = day + timedelta(days=1)

    svc.client = FakeClient([bank_txn("t-hold", "-60.00", post_day, posted=True)])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["review_queued"] == 1 and result["imported"] == 1 and result["cleared"] == 0
    await db_session.refresh(manual)
    assert manual.amount == Decimal("-50.00") and manual.cleared == "uncleared"
    assert manual.sync_id is None, "the user's row gave the bank id to the posted row"
    rows = await _live_rows(db_session, account.id)
    [bank_row] = [r for r in rows if r.id != manual.id]
    assert bank_row.sync_id == "t-hold" and bank_row.amount == Decimal("-60.00")
    assert bank_row.cleared == "cleared"
    [match] = await _pending_matches(services, account.id)
    assert match.synced_transaction_id == bank_row.id
    assert match.manual_transaction_id == manual.id


async def test_bank_pending_row_amount_change_at_posting_updates_in_place(db_session):
    """The rule the review queue does NOT apply to: a row the sync itself
    created takes the bank's posted amount, remembering the hold's."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=2)
    svc = _service(services, [bank_txn("t-9", "-20.00", day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    svc.client = FakeClient([bank_txn("t-9", "-23.50", day + timedelta(days=1), posted=True)])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["review_queued"] == 0 and result["cleared"] == 1
    [txn] = await _live_rows(db_session, account.id)
    assert txn.amount == Decimal("-23.50")
    assert txn.entered_amount == Decimal("-20.00"), "the hold's amount is kept as provenance"
    assert await _pending_matches(services, account.id) == []


async def test_stale_link_with_changed_amount_queues_review(db_session):
    """New id AND a new amount at posting — the case exact-amount candidates
    cannot cover. The vanished link is released and the posted row this run
    created is offered for review."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    svc, manual, day = await _link_manual_to_hold(
        db_session,
        services,
        budget,
        account,
        conn,
        amount="-20.00",
        user_payee="Starbucks",
        bank_payee="STARBUCKS #1234",
    )
    post_day = day + timedelta(days=1)

    svc.client = FakeClient(
        [bank_txn("t-new", "-23.50", post_day, posted=True, payee="STARBUCKS #1234 SEATTLE")]
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 1 and result["review_queued"] == 1
    assert result["removed_pending"] == 0, "a user row is never swept"
    await db_session.refresh(manual)
    assert manual.sync_id is None and manual.cleared == "uncleared"
    [match] = await _pending_matches(services, account.id)
    assert match.manual_transaction_id == manual.id
    synced = await services.transaction_repo.get(match.synced_transaction_id)
    assert synced is not None and synced.sync_id == "t-new"


async def test_stale_link_review_matches_on_the_retained_bank_payee_when_the_users_payee_differs(
    db_session,
):
    """The user renamed the payee to something the bank string shares nothing
    with. The row still keeps the bank's own pending string, and the posted
    string matches THAT — so the pair is found."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    svc, manual, day = await _link_manual_to_hold(
        db_session,
        services,
        budget,
        account,
        conn,
        amount="-20.00",
        user_payee="Coffee",
        bank_payee="SQ *BLUE BOTTLE 0042",
        via_feed=False,
    )
    await db_session.refresh(manual)
    assert manual.bank_payee == "SQ *BLUE BOTTLE 0042"

    svc.client = FakeClient(
        [bank_txn("t-new", "-23.50", day, posted=True, payee="SQ *BLUE BOTTLE 0042 OAKLAND")]
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["review_queued"] == 1
    [match] = await _pending_matches(services, account.id)
    assert match.manual_transaction_id == manual.id


async def test_same_sync_id_with_changed_amount_never_needs_payee_scoring(db_session):
    """When the bank keeps the id, the identity path queues the amount
    change regardless of how the payee strings compare."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    svc, manual, day = await _link_manual_to_hold(
        db_session,
        services,
        budget,
        account,
        conn,
        user_payee="Coffee",
        bank_payee="X",
        via_feed=False,
    )
    svc.client = FakeClient(
        [bank_txn("t-hold", "-60.00", day, posted=True, payee="ZZZ ENTIRELY DIFFERENT")]
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["review_queued"] == 1
    [match] = await _pending_matches(services, account.id)
    assert match.manual_transaction_id == manual.id


async def _changes_for(db_session, txn_id):
    await db_session.flush()
    rows = (
        (
            await db_session.execute(
                select(ChangeLog).where(ChangeLog.entity_id == txn_id).order_by(ChangeLog.seq)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def test_second_sync_of_a_posted_row_writes_nothing(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=1)
    svc = _service(services, [bank_txn("t-1", "-12.50", day)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [txn] = await _live_rows(db_session, account.id)
    before = len(await _changes_for(db_session, txn.id))
    stamp = txn.updated_at

    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["skipped"] == 1 and result["cleared"] == 0
    await db_session.refresh(txn)
    assert txn.updated_at == stamp
    assert len(await _changes_for(db_session, txn.id)) == before


async def test_sync_posting_is_recorded_as_a_system_change(db_session):
    """Sync used to write rows through the repository with no change-log row
    — an amount or cleared state moved with nothing in Activity to show it."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    day = date.today() - timedelta(days=1)
    manual = await create_transaction(
        db_session, budget, account, "-50.00", day, cleared="uncleared"
    )
    svc = _service(services, [bank_txn("t-1", "-50.00", day)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    changes = await _changes_for(db_session, manual.id)
    assert [c.action for c in changes] == ["update"]
    assert changes[0].source == "system"
    assert changes[0].before["cleared"] == "uncleared" and changes[0].after["cleared"] == "cleared"


async def test_sweep_delete_is_undoable(db_session):
    """The sweep removes a bank-created pending row the feed dropped. It used
    to be an unrecorded soft-delete; the category the user filed it under
    went with it."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    auth_day = date.today() - timedelta(days=2)
    svc = _service(services, [bank_txn("t-old", "-15.00", auth_day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [pending] = await _live_rows(db_session, account.id)
    await services.transactions.update(budget.id, pending.id, TransactionUpdate(memo="filed"))

    svc.client = FakeClient(
        [bank_txn("t-new", "-17.00", date.today(), posted=True, payee="ELSEWHERE")]
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)
    assert result["removed_pending"] == 1

    deletes = [c for c in await _changes_for(db_session, pending.id) if c.action == "delete"]
    assert len(deletes) == 1 and deletes[0].source == "system"
    await UndoService(db_session).undo_change(budget.id, deletes[0].id)
    await db_session.refresh(pending)
    assert pending.is_deleted is False and pending.memo == "filed"


# ─── Opening-balance anchor ──────────────────────────────────────────────────
# The fetch window is 90 days; anything older lives only in the balance the
# bank reports alongside the transactions. The first sync writes one
# uncategorized "Starting Balance" row so the ledger equals that balance —
# without it a carried-balance card showed only the window's activity,
# thousands short of what was owed, and nothing ever noticed.


async def test_first_sync_anchors_the_ledger_to_the_reported_balance(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [bank_txn("t-1", "-100.00", today - timedelta(days=5))]
    svc = _service(services, payload, balances={SF_ACCT: Decimal("2400.00")})

    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result.get("error") is None, result
    assert result["anchored"] == 1
    rows = await _live_rows(db_session, account.id)
    anchor = next(r for r in rows if r.sync_id is None)
    # 2400 reported − (−100 imported) = 2500, dated before the oldest row so
    # history genuinely starts there, reconciled because the bank is the
    # source, uncategorized so the gap lands where unfiled money goes.
    assert anchor.amount == Decimal("2500.00")
    assert anchor.date == today - timedelta(days=6)
    assert anchor.cleared == "reconciled"
    assert anchor.category_id is None
    assert await services.account_repo.get_balance(account.id) == Decimal("2400.00")
    await db_session.refresh(account)
    assert account.simplefin_balance == Decimal("2400.00")


async def test_second_sync_never_re_anchors(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [bank_txn("t-1", "-100.00", today - timedelta(days=5))]
    svc = _service(services, payload, balances={SF_ACCT: Decimal("2400.00")})

    with PATCH_DECRYPT:
        first = await svc.sync(conn.id, budget.id)
        # The bank now reports a different figure (a pending hold cleared, a
        # row outside the window changed) — drift is for Reconcile, not for
        # a second silent adjustment.
        svc.client.balances[SF_ACCT] = Decimal("2350.00")
        second = await svc.sync(conn.id, budget.id)

    assert first["anchored"] == 1
    assert second["anchored"] == 0
    assert len(await _live_rows(db_session, account.id)) == 2
    # The reported balance still updates every sync, so the account page can
    # show the drift.
    await db_session.refresh(account)
    assert account.simplefin_balance == Decimal("2350.00")


async def test_a_ledger_already_matching_gets_no_anchor(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [bank_txn("t-1", "-100.00", today - timedelta(days=5))]
    svc = _service(services, payload, balances={SF_ACCT: Decimal("-100.00")})

    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["anchored"] == 0
    assert len(await _live_rows(db_session, account.id)) == 1


async def test_a_card_anchor_lands_as_uncovered_debt(db_session):
    """The user's own case: a carried-balance card whose first sync brings
    90 days of activity against years of debt. The anchor closes the gap and
    the whole pre-history balance shows as the card's Uncovered — not in any
    envelope, not charged to Ready to Assign."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    card = await create_account(
        db_session, budget, "Visa", account_type="credit_card", simplefin_account_id="sf-visa"
    )
    from igab.services.card_payment import ensure_payment_category

    await ensure_payment_category(db_session, card)
    today = date.today()
    payload = [bank_txn("v-1", "-200.00", today - timedelta(days=5)) | {"account_id": "sf-visa"}]
    svc = _service(services, payload, balances={"sf-visa": Decimal("-2690.00")})

    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result.get("error") is None, result
    assert result["anchored"] == 1
    assert await services.account_repo.get_balance(card.id) == Decimal("-2690.00")
    summary = await services.budgets.get_budget_summary(budget.id, today.replace(day=1))
    row = next(c for c in summary.cards if c.account_id == card.id)
    assert row.balance == Decimal("-2690.00")
    assert row.uncovered == Decimal("2690.00")
    assert row.set_aside == Decimal("0")
    # And Ready to Assign never heard about any of it.
    assert summary.to_be_assigned == Decimal("0")
