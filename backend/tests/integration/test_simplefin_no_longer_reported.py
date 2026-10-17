"""Rows the bank stopped reporting: which a sync judges, what it does to each,
and how the person hears about it.

The report: a card whose register still held charges the bank's website no
longer showed. Four ways a row could outlive the bank's copy of it, each
pinned here by name:

(a) a pending hold the sync wrote, dated before the run's window — never
    judged again once an hourly run's few days had moved past it;
(b) a row the person typed, linked to a hold that vanished — unlinked and
    kept, silently;
(c) a posted row missing from the feed — never judged at all;
(d) an account the feed carried no rows for, judged against an empty set
    because a different account's rows made the feed non-empty.

All data is invented: payees, amounts and bank ids.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import SyncRun, Transaction
from igab.domain.bank_absence import HOLD, KEPT, LINKED_TO_HOLD, POSTED, REMOVED, REPORTED_AGAIN
from igab.services.account_hygiene import AccountHygieneService
from igab.services.transaction_service import SplitSpec, TransactionUpdate
from igab.services.undo_service import UndoService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_simplefin_connection,
    create_user,
    make_services,
)
from .fake_bridge import FakeBridge
from .test_simplefin_sync import (
    PATCH_DECRYPT,
    SF_ACCT,
    _link_manual_to_hold,
    _live_rows,
    _service,
    bank_txn,
)

TODAY = date.today()
CARD_SF = "sf-card-2"
#: A posting the feed keeps carrying, older than the row that goes missing —
#: what shows the feed covered the missing row's day.
EARLIER = TODAY - timedelta(days=3)


async def _world(db_session, user=None):
    services = make_services(db_session)
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(
        db_session, budget, "Sapphire Visa", simplefin_account_id=SF_ACCT
    )
    conn = await create_simplefin_connection(db_session, user)
    return services, budget, account, conn


async def _card(db_session, budget):
    return await create_account(db_session, budget, "Cascade Card", simplefin_account_id=CARD_SF)


def _on_card(txn: dict) -> dict:
    return {**txn, "account_id": CARD_SF}


async def _latest_run(db_session, budget) -> SyncRun:
    return (
        (
            await db_session.execute(
                select(SyncRun).where(SyncRun.budget_id == budget.id).order_by(SyncRun.seq.desc())
            )
        )
        .scalars()
        .first()
    )


async def _listed(db_session, budget) -> list:
    report = await AccountHygieneService(db_session).run(budget.id)
    return [i for f in report.findings if f.kind == "no_longer_at_bank" for i in f.items]


async def _get(db_session, txn_id) -> Transaction:
    row = await db_session.get(Transaction, txn_id)
    assert row is not None
    await db_session.refresh(row)
    return row


# ─── (a) a hold older than the window ────────────────────────────────────────


async def test_class_a_a_hold_older_than_the_window_is_judged(db_session):
    services, budget, account, conn = await _world(db_session)
    hold_day = TODAY - timedelta(days=8)
    svc = _service(
        services,
        [
            bank_txn("t-hold", "-120.00", hold_day, posted=False, payee="HARBORSTONE INN"),
            bank_txn("t-a", "-4.00", TODAY - timedelta(days=1)),
        ],
    )
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    await db_session.refresh(account)
    assert account.last_simplefin_sync_at is not None

    # An hourly run: the account synced a moment ago, so on its own the
    # window would start five days back — three days after the hold.
    svc.client = FakeBridge([bank_txn("t-a", "-4.00", TODAY - timedelta(days=1))])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    asked_from = svc.client.requests[-1].since
    assert asked_from is not None
    assert asked_from <= datetime(hold_day.year, hold_day.month, hold_day.day, tzinfo=UTC), (
        "the window reaches back to the open hold"
    )
    assert result["removed_pending"] == 1, result
    assert [r.sync_id for r in await _live_rows(db_session, account.id)] == ["t-a"]
    [entry] = (await _latest_run(db_session, budget)).no_longer_reported
    assert entry["kind"] == HOLD and entry["action"] == REMOVED
    assert entry["sync_id"] == "t-hold" and entry["payee"] == "HARBORSTONE INN"
    assert Decimal(entry["amount"]) == Decimal("-120.00")
    assert entry["date"] == hold_day.isoformat()


async def test_a_hold_still_reported_is_left_alone_however_old(db_session):
    services, budget, account, conn = await _world(db_session)
    hold = bank_txn("t-hold", "-120.00", TODAY - timedelta(days=8), posted=False)
    svc = _service(services, [hold, bank_txn("t-a", "-4.00", TODAY)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
        result = await svc.sync(conn.id, budget.id)
    assert result["removed_pending"] == 0
    assert (await _latest_run(db_session, budget)).no_longer_reported == []


# ─── (b) a person's row linked to a hold that vanished ──────────────────────


async def test_class_b_a_row_linked_to_a_dropped_hold_is_kept_and_listed(db_session):
    services, budget, account, conn = await _world(db_session)
    svc, manual, day = await _link_manual_to_hold(
        db_session, services, budget, account, conn, amount="-60.00"
    )
    svc.client = FakeBridge([bank_txn("t-other", "-3.00", TODAY, payee="CORNER CAFE")])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["kept_unreported"] == 1 and result["removed_pending"] == 0, result
    manual = await _get(db_session, manual.id)
    assert manual.is_deleted is False, "a row the person typed is never removed"
    assert manual.sync_id is None and manual.cleared == "uncleared"
    [entry] = (await _latest_run(db_session, budget)).no_longer_reported
    assert entry["kind"] == LINKED_TO_HOLD and entry["action"] == KEPT
    assert entry["sync_id"] == "t-hold"

    [item] = await _listed(db_session, budget)
    assert item.transaction_id == manual.id and item.action == "delete"
    assert item.account_id == account.id and item.amount == Decimal("-60.00")

    # Deleting it the ordinary way takes it off the list.
    await services.transactions.delete(budget.id, manual.id)
    assert await _listed(db_session, budget) == []


async def test_a_kept_row_a_posting_later_claims_leaves_the_list(db_session):
    services, budget, account, conn = await _world(db_session)
    svc, manual, day = await _link_manual_to_hold(
        db_session, services, budget, account, conn, amount="-60.00"
    )
    svc.client = FakeBridge([bank_txn("t-other", "-3.00", TODAY, payee="CORNER CAFE")])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    assert len(await _listed(db_session, budget)) == 1

    svc.client = FakeBridge(
        [
            bank_txn("t-other", "-3.00", TODAY, payee="CORNER CAFE"),
            bank_txn("t-late", "-60.00", day + timedelta(days=1)),
        ]
    )
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    manual = await _get(db_session, manual.id)
    assert manual.sync_id == "t-late", "the posting matched the kept row"
    assert await _listed(db_session, budget) == []


# ─── (c) a posted row missing from the feed ─────────────────────────────────


async def test_class_c_a_posted_row_missing_from_the_feed_is_kept_and_listed_once(db_session):
    services, budget, account, conn = await _world(db_session)
    day = TODAY - timedelta(days=1)
    svc = _service(services, [bank_txn("t-1", "-25.00", day), bank_txn("t-2", "-9.00", EARLIER)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [posted] = [r for r in await _live_rows(db_session, account.id) if r.sync_id == "t-1"]

    svc.client = FakeBridge([bank_txn("t-2", "-9.00", EARLIER)])
    with PATCH_DECRYPT:
        first = await svc.sync(conn.id, budget.id)
    assert first["kept_unreported"] == 1, first
    [entry] = (await _latest_run(db_session, budget)).no_longer_reported
    assert entry["kind"] == POSTED and entry["action"] == KEPT
    posted = await _get(db_session, posted.id)
    assert posted.is_deleted is False and posted.sync_id == "t-1", "kept, link and all"
    [item] = await _listed(db_session, budget)
    assert item.transaction_id == posted.id and item.action == "delete"

    # Still missing an hour later: news once, not every run.
    with PATCH_DECRYPT:
        second = await svc.sync(conn.id, budget.id)
    assert second["kept_unreported"] == 0
    assert (await _latest_run(db_session, budget)).no_longer_reported == []
    assert len(await _listed(db_session, budget)) == 1

    # The bank reports it again: the omission was momentary.
    svc.client = FakeBridge([bank_txn("t-1", "-25.00", day), bank_txn("t-2", "-9.00", EARLIER)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [back] = (await _latest_run(db_session, budget)).no_longer_reported
    assert back["action"] == REPORTED_AGAIN and back["transaction_id"] == str(posted.id)
    assert await _listed(db_session, budget) == []


async def test_class_c_a_posting_older_than_the_banks_own_history_is_not_judged(db_session):
    """A window widened to reach an old hold asks for more days than some
    banks keep. The rows between the bank's horizon and the hold are not
    missing — the bank simply no longer serves that far back."""
    services, budget, account, conn = await _world(db_session)
    hold = bank_txn("t-hold", "-80.00", TODAY - timedelta(days=25), posted=False)
    recent = bank_txn("t-new", "-5.00", TODAY - timedelta(days=1))
    svc = _service(
        services, [hold, bank_txn("t-old", "-30.00", TODAY - timedelta(days=20)), recent]
    )
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    svc.client = FakeBridge([hold, recent])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)
    assert result["kept_unreported"] == 0 and result["removed_pending"] == 0, result
    assert await _listed(db_session, budget) == []


async def test_a_reconciled_row_the_bank_dropped_is_listed_without_a_delete(db_session):
    services, budget, account, conn = await _world(db_session)
    day = TODAY - timedelta(days=1)
    svc = _service(services, [bank_txn("t-1", "-25.00", day), bank_txn("t-2", "-9.00", EARLIER)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [posted] = [r for r in await _live_rows(db_session, account.id) if r.sync_id == "t-1"]
    posted.cleared = "reconciled"
    await db_session.flush()

    svc.client = FakeBridge([bank_txn("t-2", "-9.00", EARLIER)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [item] = await _listed(db_session, budget)
    assert item.transaction_id == posted.id and item.action is None


# ─── (d) accounts the feed said nothing about ───────────────────────────────


async def test_class_d_an_account_the_feed_carried_no_rows_for_is_not_judged(db_session):
    """One busy account used to license judging a quiet card against no rows
    at all: the gate was the whole feed's, so the card's hold went."""
    services, budget, account, conn = await _world(db_session)
    card = await _card(db_session, budget)
    hold = _on_card(bank_txn("t-card-hold", "-40.00", TODAY, posted=False))
    svc = _service(services, [bank_txn("t-a", "-4.00", TODAY), hold])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    svc.client = FakeBridge(
        [bank_txn("t-a", "-4.00", TODAY), bank_txn("t-b", "-6.00", TODAY)],
        balances={CARD_SF: Decimal("-40.00")},
        names={CARD_SF: "Cascade Card"},
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["removed_pending"] == 0, result
    assert [r.sync_id for r in await _live_rows(db_session, card.id)] == ["t-card-hold"]
    assert (await _latest_run(db_session, budget)).no_longer_reported == []


async def test_class_d_an_empty_feed_records_nothing(db_session):
    services, budget, account, conn = await _world(db_session)
    svc = _service(services, [bank_txn("t-hold", "-40.00", TODAY, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    svc.client = FakeBridge([], balances={SF_ACCT: Decimal("0")}, names={SF_ACCT: "Sapphire"})
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)
    assert result["removed_pending"] == 0 and result["kept_unreported"] == 0
    assert len(await _live_rows(db_session, account.id)) == 1
    assert await _listed(db_session, budget) == []


async def test_class_d_an_orphaned_account_records_nothing(db_session):
    services, budget, account, conn = await _world(db_session)
    svc = _service(services, [bank_txn("t-hold", "-40.00", TODAY, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    # The bank stopped offering this account; another account's rows arrive.
    stranger = {**bank_txn("t-x", "-1.00", TODAY), "account_id": "sf-unlinked"}
    svc.client = FakeBridge([stranger], names={"sf-unlinked": "Northwind Checking"})
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)
    assert result["orphaned_links"], result
    assert result["removed_pending"] == 0
    assert len(await _live_rows(db_session, account.id)) == 1
    assert (await _latest_run(db_session, budget)).no_longer_reported == []


async def test_class_d_an_account_sync_judges_only_the_account_it_asked_for(db_session):
    services, budget, account, conn = await _world(db_session)
    card = await _card(db_session, budget)
    card_hold = _on_card(bank_txn("t-card-hold", "-40.00", TODAY, posted=False))
    svc = _service(
        services,
        [
            bank_txn("t-hold", "-15.00", TODAY, posted=False),
            bank_txn("t-a", "-4.00", TODAY),
            card_hold,
        ],
    )
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    # Both holds dropped; only the checking account is asked for.
    svc.client = FakeBridge(
        [
            bank_txn("t-a", "-4.00", TODAY),
            _on_card(bank_txn("t-c", "-2.00", TODAY)),
        ]
    )
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id, account_simplefin_id=SF_ACCT)
    assert svc.client.filters[-1] == (SF_ACCT,)
    assert result["removed_pending"] == 1
    assert [r.sync_id for r in await _live_rows(db_session, card.id)] == ["t-card-hold"]


# ─── Restore ────────────────────────────────────────────────────────────────


async def _dropped_hold(db_session, services, budget, account, conn):
    """A hold the person filed and annotated, which the bank then dropped."""
    day = TODAY - timedelta(days=2)
    group = await create_category_group(db_session, budget)
    dining = await create_category(db_session, budget, group, "Dining")
    svc = _service(services, [bank_txn("t-hold", "-48.00", day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [hold] = await _live_rows(db_session, account.id)
    await services.transactions.update(
        budget.id, hold.id, TransactionUpdate(category_id=dining.id, memo="team lunch")
    )
    svc.client = FakeBridge([bank_txn("t-z", "-2.00", TODAY, payee="ELSEWHERE")])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)
    assert result["removed_pending"] == 1
    return svc, hold, dining


async def test_a_dropped_hold_is_listed_with_restore(db_session):
    services, budget, account, conn = await _world(db_session)
    _svc, hold, _ = await _dropped_hold(db_session, services, budget, account, conn)
    [item] = await _listed(db_session, budget)
    assert item.transaction_id == hold.id and item.action == "restore"
    assert item.note == "pending hold, removed"


async def test_restore_brings_the_hold_back_with_the_users_edits(db_session, api_client):
    services, budget, account, conn = await _world(db_session, api_client.test_user)
    svc, hold, dining = await _dropped_hold(db_session, services, budget, account, conn)

    r = await api_client.post(
        f"/api/v1/{budget.id}/accounts/hygiene/restore-dropped-hold",
        json={"transaction_id": str(hold.id)},
    )
    assert r.status_code == 200, r.text

    hold = await _get(db_session, hold.id)
    assert hold.is_deleted is False
    assert hold.category_id == dining.id and hold.memo == "team lunch"
    assert hold.cleared == "uncleared" and hold.sync_id is None
    assert await _listed(db_session, budget) == []

    # The next sync does not remove it again, and the run's other work stands.
    with PATCH_DECRYPT:
        again = await svc.sync(conn.id, budget.id)
    assert again["removed_pending"] == 0
    live = {r.id for r in await _live_rows(db_session, account.id)}
    assert hold.id in live and len(live) == 2

    # Listed no more, so a second restore is refused.
    r = await api_client.post(
        f"/api/v1/{budget.id}/accounts/hygiene/restore-dropped-hold",
        json={"transaction_id": str(hold.id)},
    )
    assert r.status_code == 404


async def test_the_sync_log_serves_each_row_a_run_found_missing(db_session, api_client):
    services, budget, account, conn = await _world(db_session, api_client.test_user)
    _svc, hold, _ = await _dropped_hold(db_session, services, budget, account, conn)
    r = await api_client.get(f"/api/v1/{budget.id}/simplefin/sync-runs")
    assert r.status_code == 200, r.text
    [entry] = r.json()["runs"][0]["no_longer_reported"]
    assert entry["transaction_id"] == str(hold.id)
    assert entry["action"] == REMOVED and entry["kind"] == HOLD
    assert Decimal(entry["amount"]) == Decimal("-48.00")


async def test_restore_takes_back_one_row_not_the_whole_run(db_session, api_client):
    """The run is one change-log batch; undoing the hold's delete through
    `undo_change` would have taken back every import beside it."""
    services, budget, account, conn = await _world(db_session, api_client.test_user)
    _svc, hold, _ = await _dropped_hold(db_session, services, budget, account, conn)
    r = await api_client.post(
        f"/api/v1/{budget.id}/accounts/hygiene/restore-dropped-hold",
        json={"transaction_id": str(hold.id)},
    )
    assert r.status_code == 200, r.text
    assert "t-z" in {r.sync_id for r in await _live_rows(db_session, account.id)}


async def test_restore_brings_back_a_split_holds_lines(db_session, api_client):
    services, budget, account, conn = await _world(db_session, api_client.test_user)
    day = TODAY - timedelta(days=2)
    svc = _service(services, [bank_txn("t-hold", "-30.00", day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    [hold] = await _live_rows(db_session, account.id)
    await services.transactions.convert_to_split(
        budget.id,
        hold.id,
        [SplitSpec(amount=Decimal("-20.00")), SplitSpec(amount=Decimal("-10.00"))],
    )
    svc.client = FakeBridge([bank_txn("t-z", "-2.00", TODAY, payee="ELSEWHERE")])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    r = await api_client.post(
        f"/api/v1/{budget.id}/accounts/hygiene/restore-dropped-hold",
        json={"transaction_id": str(hold.id)},
    )
    assert r.status_code == 200, r.text
    lines = await services.transaction_repo.get_splits(hold.id)
    assert sorted(line.amount for line in lines) == [Decimal("-20.00"), Decimal("-10.00")]
    assert all(line.cleared == "uncleared" for line in lines)


async def test_a_hold_the_bank_reports_again_leaves_the_list(db_session):
    services, budget, account, conn = await _world(db_session)
    svc, hold, _ = await _dropped_hold(db_session, services, budget, account, conn)
    day = TODAY - timedelta(days=2)
    svc.client = FakeBridge(
        [bank_txn("t-hold", "-48.00", day, posted=False), bank_txn("t-z", "-2.00", TODAY)]
    )
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    assert await _listed(db_session, budget) == []


async def test_undoing_the_run_takes_its_rows_off_the_list(db_session):
    services, budget, account, conn = await _world(db_session)
    _svc, hold, _ = await _dropped_hold(db_session, services, budget, account, conn)
    run = await _latest_run(db_session, budget)
    await UndoService(db_session).undo_batch_leniently(budget.id, run.change_batch_id)
    run.undone_at = datetime.now(UTC)
    await db_session.flush()
    assert await _listed(db_session, budget) == []
