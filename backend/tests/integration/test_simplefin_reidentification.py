"""Re-linking a bank account at the bridge must not duplicate its history.

The incident this encodes: a SimpleFIN connection was re-linked, the bridge
minted a new `ACT-…` for the account and fresh ids for every transaction in
it, and one sync wrote 330 rows to an account that needed 53 — 277 of them
twins of already-reconciled transactions, complete with their own fresh bank
ids. The dedup ladder could not have caught it: it only offers candidates
that carry no bank link at all, and every one of those rows carried the
retired one.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import select

from igab.db.models import Account, Transaction
from igab.domain.sync_window import SIMPLEFIN_MAX_WINDOW_DAYS
from igab.integrations.simplefin.client import SimpleFINError, SimpleFINFeed
from igab.services.simplefin_service import SimpleFINService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_simplefin_connection,
    create_user,
    make_services,
)

OLD_ACCT = "ACT-old"
NEW_ACCT = "ACT-new"
BANK_NAME = "HARBORSTONE EVERYDAY CHECKING"
#: Close enough to be suggested, not close enough to be acted on. The three
#: tests below are about the path that still needs a person: auto-relink only
#: ever fires on an exact name match.
BANK_NAME_SIMILAR = "HARBORSTONE EVERYDAY CHECKING — Primary"

PATCH_DECRYPT = patch("igab.services.simplefin_service.decrypt", return_value="https://u:p@x.test")


class FakeClient:
    """A bridge that answers from a fixed payload.

    `honour_window` makes it behave like the real one — a row posted before
    `since` is not returned — which is the only way to test that a window
    was wide enough. The `since` of every request is kept for the same
    reason.
    """

    def __init__(self, payload, names=None, errors=None, balances=None, honour_window=False):
        self.payload = payload
        self.names = names or {}
        self.errors = errors or []
        self.balances = balances or {}
        self.honour_window = honour_window
        self.requests: list[datetime | None] = []

    async def get_feed(self, access_url: str, since=None) -> SimpleFINFeed:
        self.requests.append(since)
        rows = self.payload
        if self.honour_window and since is not None:
            rows = [t for t in rows if t["posted"] >= since.timestamp()]
        return SimpleFINFeed(
            transactions=rows,
            balances=dict(self.balances),
            account_names=dict(self.names),
            errors=list(self.errors),
        )

    async def get_accounts(self, access_url: str) -> list[dict]:
        return []


def _ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 12, tzinfo=UTC).timestamp())


def bank_txn(txn_id: str, amount: str, on: date, *, account: str, payee: str) -> dict:
    return {
        "id": txn_id,
        "account_id": account,
        "amount": amount,
        "payee": payee,
        "description": f"{payee} POS PURCHASE",
        "posted": _ts(on),
    }


#: Amounts are distinct so each feed row has exactly one candidate and the
#: pairing is unambiguous.
HISTORY = [
    ("-12.50", "CORNER MARKET"),
    ("-40.00", "HARBORSTONE FUEL"),
    ("-8.75", "CASCADE COFFEE"),
    ("-125.00", "NORTHWIND UTILITIES"),
    ("-64.20", "SAPPHIRE PHARMACY"),
    ("-19.99", "MERIDIAN STREAMING"),
    ("-230.45", "LAKESHORE GROCERS"),
    ("-55.00", "PINEGROVE HARDWARE"),
]


def _feed(account: str, prefix: str, start: date) -> list[dict]:
    return [
        bank_txn(f"{prefix}-{i}", amount, start + timedelta(days=i), account=account, payee=payee)
        for i, (amount, payee) in enumerate(HISTORY)
    ]


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(
        db_session, budget, "Harborstone Checking", simplefin_account_id=OLD_ACCT
    )
    account.simplefin_account_name = BANK_NAME
    conn = await create_simplefin_connection(db_session, user)
    await db_session.flush()
    return services, budget, account, conn


def _service(
    services, payload, names=None, errors=None, balances=None, honour_window=False
) -> SimpleFINService:
    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = FakeClient(payload, names, errors, balances, honour_window)
    return svc


async def _relink(db_session, account: Account, feed_id: str) -> None:
    """What the link endpoint does: repoint the account and forget when it
    last synced, so the next run asks for the full window."""
    account.simplefin_account_id = feed_id
    account.last_simplefin_sync_at = None
    await db_session.flush()


async def _synced_at(db_session, account: Account, when: datetime) -> None:
    account.last_simplefin_sync_at = when
    await db_session.flush()


async def _live_rows(db_session, account_id) -> list[Transaction]:
    result = await db_session.execute(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.is_deleted == False,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def test_relinked_account_adopts_its_history_instead_of_duplicating_it(db_session):
    """The 277-duplicate regression, end to end — in the shape that broke it
    the second time.

    After the first fix, a relinked account caught up through a window a few
    days wide, so its recent rows took the new bank ids while everything
    older kept the retired ones. A wider re-fetch then found the account
    holding both, decided it had *not* been re-identified, and would have
    written every retired-id row again. Adoption is now decided per row: an
    id the bank was asked about and did not report is one it has retired.
    """
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    with PATCH_DECRYPT:
        first = await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    assert first.get("error") is None, first
    assert first["imported"] == len(HISTORY)

    # Give the rows the bookkeeping a person would have done, and reconcile
    # them — what the duplicate sync destroyed the value of.
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group, "Groceries")
    rows = await _live_rows(db_session, account.id)
    for row in rows:
        row.category_id = category.id
        row.cleared = "reconciled"
    await db_session.flush()

    # The bank re-issued every id. The first catch-up only reached the last
    # three rows, so the account now holds five retired ids and three new.
    account.simplefin_account_id = NEW_ACCT
    await _synced_at(db_session, account, datetime.now(UTC))
    recent = _feed(NEW_ACCT, "new", start)[-3:]
    with PATCH_DECRYPT:
        partial = await _service(services, recent, names={NEW_ACCT: BANK_NAME}).sync(
            conn.id, budget.id
        )
    assert partial["adopted"] == 0, "outside the window asked for: not evidence, not adopted"
    assert partial["imported"] == 3, "and so, honestly, imported"
    for row in await _live_rows(db_session, account.id):
        if row.sync_id.startswith("new-"):
            await services.transactions.delete(budget.id, row.id, source="system")
    await db_session.flush()
    rows = await _live_rows(db_session, account.id)
    for row, feed_row in zip(sorted(rows, key=lambda r: r.date)[-3:], recent):
        row.sync_id = feed_row["id"]
    await db_session.flush()

    # Now the full window, with one row the broken link missed.
    await _relink(db_session, account, NEW_ACCT)
    feed = _feed(NEW_ACCT, "new", start) + [
        bank_txn("new-late", "-31.00", date.today(), account=NEW_ACCT, payee="CORNER MARKET")
    ]
    with PATCH_DECRYPT:
        second = await _service(services, feed, names={NEW_ACCT: BANK_NAME}).sync(
            conn.id, budget.id
        )

    assert second.get("error") is None, second
    assert second["adopted"] == len(HISTORY) - 3, second
    assert second["imported"] == 1, second
    assert second["skip_reasons"] == {"already_posted": 3}

    after = await _live_rows(db_session, account.id)
    assert len(after) == len(HISTORY) + 1, "a re-fetch must not double the register"

    # The adopted rows carry the new bank ids, so the *next* sync recognises
    # them — without this the duplication simply recurs on the next run.
    assert {r.sync_id for r in after} == {f"new-{i}" for i in range(len(HISTORY))} | {"new-late"}
    # And they are still the user's rows.
    history = [r for r in after if r.sync_id != "new-late"]
    assert all(r.category_id == category.id for r in history)
    assert all(r.cleared == "reconciled" for r in history)


async def test_adoption_is_stable_on_a_second_sync(db_session):
    """Once adopted, the account is ordinary again: no further adoption, no
    duplicates, nothing but already-posted skips."""
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    await _relink(db_session, account, NEW_ACCT)

    with PATCH_DECRYPT:
        svc = _service(services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME})
        await svc.sync(conn.id, budget.id)
        third = await svc.sync(conn.id, budget.id)

    assert third["adopted"] == 0
    assert third["imported"] == 0
    assert third["skip_reasons"] == {"already_posted": len(HISTORY)}
    assert len(await _live_rows(db_session, account.id)) == len(HISTORY)


async def test_ordinary_sync_never_adopts(db_session):
    """Overlapping ids mean the link still holds. A genuinely new row must
    import, not absorb an existing one."""
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)

    payload = _feed(OLD_ACCT, "old", start) + [
        bank_txn("old-new-row", "-77.10", date.today(), account=OLD_ACCT, payee="CORNER MARKET")
    ]
    with PATCH_DECRYPT:
        second = await _service(services, payload).sync(conn.id, budget.id)

    assert second["adopted"] == 0
    assert second["imported"] == 1
    assert len(await _live_rows(db_session, account.id)) == len(HISTORY) + 1


async def test_a_row_outside_the_window_asked_for_is_never_offered(db_session):
    """The `since` bound that makes row-level adoption safe.

    A row holds a bank id the feed does not mention. That means one of two
    opposite things, and only the window separates them: the bank was asked
    about that day and dropped the id (retired — adopt), or the bank was
    never asked (no evidence — leave it alone). Here the feed carries a
    record on the row's own day, so the date rule admits it either way, and
    the window is the only thing deciding.
    """
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=8)
    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    rows_before = len(await _live_rows(db_session, account.id))

    # The bank re-reports that same first purchase, same day, under a new id.
    reissued = bank_txn("new-first", HISTORY[0][0], start, account=OLD_ACCT, payee=HISTORY[0][1])

    # Asked for the last two days only: the row sits eight days back, outside
    # what was requested, so its missing id proves nothing and the record
    # imports rather than claiming it.
    await _synced_at(db_session, account, datetime.now(UTC) - timedelta(days=2))
    with PATCH_DECRYPT:
        narrow = await _service(services, [reissued]).sync(conn.id, budget.id)
    assert narrow["adopted"] == 0, "the bank was never asked about that day"
    assert narrow["imported"] == 1
    for row in await _live_rows(db_session, account.id):
        if row.sync_id == "new-first":
            await services.transactions.delete(budget.id, row.id, source="system")
    await db_session.flush()

    # Asked for the full window: the same absent id now means the bank was
    # asked and did not report it, so the row adopts the new id in place.
    await _synced_at(db_session, account, datetime.now(UTC) - timedelta(days=30))
    with PATCH_DECRYPT:
        wide = await _service(services, [reissued]).sync(conn.id, budget.id)
    assert wide["adopted"] == 1, wide
    assert wide["imported"] == 0
    assert len(await _live_rows(db_session, account.id)) == rows_before


async def test_an_orphaned_account_does_not_advance_its_window(db_session):
    """The stamp says when the bank last served this account, not when a sync
    last ran. Advancing it on runs that served the account nothing is how a
    relinked account came back asking for the days since the *break* rather
    than the days since it was last served — and 24 posted rows were never
    requested.
    """
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)
    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    await db_session.refresh(account)
    served_at = account.last_simplefin_sync_at
    assert served_at is not None

    # The bank re-issues the id under a name auto-relink will not act on.
    # Two hourly runs go by.
    with PATCH_DECRYPT:
        svc = _service(services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME_SIMILAR})
        await svc.sync(conn.id, budget.id)
        await svc.sync(conn.id, budget.id)

    await db_session.refresh(account)
    assert account.last_simplefin_sync_at == served_at


async def test_an_automatic_relink_asks_for_the_full_window(db_session):
    """A relink in the middle of a run cannot make do with the feed already
    in hand: that feed was fetched for the days since the runs that served
    this account nothing. The run asks again, from the floor, before
    importing — so the days the broken link missed arrive in the same run.
    """
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)
    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    rows_before = len(await _live_rows(db_session, account.id))

    # The account was served an hour ago (as far as its stamp knows), and a
    # row posted twenty days ago is what the broken link missed.
    await _synced_at(db_session, account, datetime.now(UTC) - timedelta(hours=1))
    missed = bank_txn(
        "new-missed",
        "-31.00",
        date.today() - timedelta(days=20),
        account=NEW_ACCT,
        payee="CORNER MARKET",
    )
    svc = _service(
        services,
        _feed(NEW_ACCT, "new", start) + [missed],
        names={NEW_ACCT: BANK_NAME},
        honour_window=True,
    )
    await db_session.refresh(conn)
    quota_before = conn.global_requests_today
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert len(svc.client.requests) == 2, "fetched once narrow, then again from the floor"
    floor = datetime.now(UTC) - timedelta(days=SIMPLEFIN_MAX_WINDOW_DAYS)
    assert abs((svc.client.requests[1] - floor).total_seconds()) < 60
    assert result["adopted"] == rows_before
    assert result["imported"] == 1, "the missed row arrived in the same run"
    await db_session.refresh(conn)
    assert conn.global_requests_today == quota_before + 2, "both requests count against the quota"


async def test_a_reconciled_account_off_from_the_bank_is_a_fault(db_session):
    """The bank's balance was stored every sync and shown on one page. A gap
    on a reconciled account now reaches the run, the connection's error and
    the health check — the sync's own admission that something did not
    arrive."""
    from igab.repositories.sync_run_repo import SyncRunRepository

    services, budget, account, conn = await _setup(db_session)
    account.last_reconciled_at = datetime.now(UTC)
    await db_session.flush()
    start = date.today() - timedelta(days=30)
    ledger = sum(Decimal(amount) for amount, _payee in HISTORY)

    with PATCH_DECRYPT:
        first = await _service(
            services, _feed(OLD_ACCT, "old", start), balances={OLD_ACCT: ledger}
        ).sync(conn.id, budget.id)
    assert first["balance_drift"] == [], "the ledger agrees with the bank"

    with PATCH_DECRYPT:
        result = await _service(
            services,
            _feed(OLD_ACCT, "old", start),
            balances={OLD_ACCT: ledger - Decimal("1240.17")},
        ).sync(conn.id, budget.id)

    [drift] = result["balance_drift"]
    assert drift["account_name"] == "Harborstone Checking"
    assert Decimal(drift["bank_balance"]) == ledger - Decimal("1240.17")
    assert Decimal(drift["ledger_cleared_balance"]) == ledger
    await db_session.refresh(conn)
    assert "off by 1,240.17" in conn.last_sync_error

    repo = SyncRunRepository(db_session)
    runs, _ = await repo.list_runs(budget_id=budget.id)
    run = await repo.get(runs[0].id)
    assert run.status == "degraded"
    assert run.balance_drift[0]["account_name"] == "Harborstone Checking"
    [row] = run.accounts
    assert row.bank_balance == ledger - Decimal("1240.17")
    assert row.ledger_cleared_balance == ledger


async def test_an_unreconciled_account_off_from_the_bank_is_not_a_fault(db_session):
    """A mortgage accrues interest between statements and a 401k moves with
    the market. Flagging those would light the badge permanently."""
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)
    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    with PATCH_DECRYPT:
        result = await _service(
            services, _feed(OLD_ACCT, "old", start), balances={OLD_ACCT: Decimal("999.99")}
        ).sync(conn.id, budget.id)
    assert result["balance_drift"] == []
    await db_session.refresh(conn)
    assert conn.last_sync_error is None


async def test_a_first_sync_anchors_before_it_judges_drift(db_session):
    """The opening-balance anchor closes the gap a 90-day window cannot
    carry; a fresh account must not be flagged for its own pre-history."""
    services, budget, account, conn = await _setup(db_session)
    account.last_reconciled_at = datetime.now(UTC)
    await db_session.flush()
    start = date.today() - timedelta(days=30)
    with PATCH_DECRYPT:
        result = await _service(
            services, _feed(OLD_ACCT, "old", start), balances={OLD_ACCT: Decimal("5000")}
        ).sync(conn.id, budget.id)
    assert result["anchored"] == 1
    assert result["balance_drift"] == []


async def test_orphaned_link_is_reported_and_recorded(db_session):
    """The nine-day outage: the account still syncs, still reports success,
    and imports nothing because its stored id is no longer offered."""
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    # The feed offers only the new account; the budget still points at the old.
    with PATCH_DECRYPT:
        result = await _service(
            services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME_SIMILAR}
        ).sync(conn.id, budget.id)

    assert result["imported"] == 0
    assert result["skip_reasons"] == {"foreign_account": len(HISTORY)}

    orphans = result["orphaned_links"]
    assert [o["account_name"] for o in orphans] == ["Harborstone Checking"]
    assert orphans[0]["stored_simplefin_id"] == OLD_ACCT
    assert orphans[0]["suggested_feed_id"] == NEW_ACCT

    await db_session.refresh(conn)
    assert conn.last_sync_error is not None
    assert "Harborstone Checking" in conn.last_sync_error
    assert conn.last_sync_error_at is not None


async def test_bridge_auth_errors_reach_the_connection(db_session):
    """`con.auth` names an institution whose credentials lapsed. The bridge's
    own guide says always show these; they used to be logged into a root
    logger nothing had configured and shown nowhere."""
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)
    errors = [
        SimpleFINError(code="gen.api", message="Requested date range exceeds limit of 90 days."),
        SimpleFINError(
            code="con.auth",
            message="Connection to Harborstone Financial may need attention. Auth required",
            connection_id="MBR-1",
        ),
    ]

    with PATCH_DECRYPT:
        result = await _service(services, _feed(OLD_ACCT, "old", start), errors=errors).sync(
            conn.id, budget.id
        )

    assert [e["code"] for e in result["bank_errors"]] == ["gen.api", "con.auth"]
    await db_session.refresh(conn)
    # The auth failure is surfaced; the capped-range notice is ours to fix,
    # not the user's, so it does not become their error banner.
    assert "Harborstone Financial" in conn.last_sync_error
    assert "90 days" not in conn.last_sync_error


async def test_clean_sync_leaves_no_error_behind(db_session):
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)
    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    await db_session.refresh(conn)
    assert conn.last_sync_error is None
    assert conn.last_sync_error_at is None


async def test_skip_reasons_always_sum_to_skipped(db_session):
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)
    payload = _feed(OLD_ACCT, "old", start) + _feed("ACT-someone-else", "other", start)
    with PATCH_DECRYPT:
        svc = _service(services, payload)
        first = await svc.sync(conn.id, budget.id)
        second = await svc.sync(conn.id, budget.id)
    for result in (first, second):
        assert sum(result["skip_reasons"].values()) == result["skipped"], result


async def test_every_run_leaves_a_record(db_session):
    """Nothing recorded a sync before this. `last_sync_at` plus an error field
    a successful run cleared meant a sync that imported nothing looked exactly
    like one that worked."""
    from igab.repositories.sync_run_repo import SyncRunRepository

    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)

    runs, total = await SyncRunRepository(db_session).list_runs(budget_id=budget.id)
    assert total == 1
    run = await SyncRunRepository(db_session).get(runs[0].id)
    assert run.status == "ok"
    assert run.imported == len(HISTORY)
    assert run.feed_txn_count == len(HISTORY)
    assert run.window_start is not None
    assert run.duration_ms is not None

    [row] = run.accounts
    assert row.account_name == "Harborstone Checking"
    assert row.feed_txn_count == len(HISTORY)
    assert row.feed_newest_date == start + timedelta(days=len(HISTORY) - 1)
    assert row.orphaned is False


async def test_an_orphaned_account_is_recorded_as_degraded_with_no_feed_rows(db_session):
    """The signature, in one row: the run was told to sync this account and
    the feed offered it nothing at all."""
    from igab.repositories.sync_run_repo import SyncRunRepository

    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    with PATCH_DECRYPT:
        await _service(
            services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME_SIMILAR}
        ).sync(conn.id, budget.id)

    repo = SyncRunRepository(db_session)
    runs, _ = await repo.list_runs(budget_id=budget.id)
    run = await repo.get(runs[0].id)

    assert run.status == "degraded"
    assert run.skip_reasons == {"foreign_account": len(HISTORY)}
    assert run.orphaned_links[0]["suggested_feed_name"] == BANK_NAME_SIMILAR

    [row] = run.accounts
    assert row.orphaned is True
    assert row.feed_txn_count == 0
    assert row.feed_newest_date is None


async def test_a_reidentified_account_is_recorded_as_such(db_session):
    from igab.repositories.sync_run_repo import SyncRunRepository

    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)
    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    await _relink(db_session, account, NEW_ACCT)
    with PATCH_DECRYPT:
        await _service(services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME}).sync(
            conn.id, budget.id
        )

    repo = SyncRunRepository(db_session)
    runs, total = await repo.list_runs(budget_id=budget.id)
    assert total == 2
    latest = await repo.get(runs[0].id)
    assert latest.adopted == len(HISTORY)
    assert latest.accounts[0].reidentified is True


async def test_sync_all_carries_the_fault_to_the_toast(db_session):
    """The sidebar's sync button posts to sync-all, and `formatSyncSummary`
    reads `connections[].orphaned_links`. Totals alone cannot say which bank
    stopped working, so the per-connection list is what the message needs."""
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    svc = _service(services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME_SIMILAR})
    with PATCH_DECRYPT:
        result = await svc.sync_all(conn.user_id, budget.id)

    assert result["imported"] == 0
    assert result["skip_reasons"] == {"foreign_account": len(HISTORY)}

    [outcome] = result["connections"]
    assert outcome["orphaned_links"][0]["account_name"] == "Harborstone Checking"
    assert outcome["orphaned_links"][0]["suggested_feed_name"] == BANK_NAME_SIMILAR


async def test_sync_all_totals_adoptions(db_session):
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)
    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    await _relink(db_session, account, NEW_ACCT)

    svc = _service(services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME})
    with PATCH_DECRYPT:
        result = await svc.sync_all(conn.user_id, budget.id)

    assert result["adopted"] == len(HISTORY)
    assert result["connections"][0]["adopted"] == len(HISTORY)


async def test_an_exact_name_match_relinks_and_catches_up_in_one_sync(db_session):
    """The whole point: the bank reissues an id, and the next sync repoints the
    account, adopts its existing rows, and imports what was missed — without
    anyone noticing anything was wrong."""
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    rows_before = len(await _live_rows(db_session, account.id))

    # The bridge reissues the account id AND every transaction id, and adds a
    # transaction that arrived while the link was broken. The budget account
    # is NOT relinked by hand.
    feed = _feed(NEW_ACCT, "new", start) + [
        bank_txn("new-late", "-31.00", date.today(), account=NEW_ACCT, payee="CORNER MARKET")
    ]
    with PATCH_DECRYPT:
        result = await _service(services, feed, names={NEW_ACCT: BANK_NAME}).sync(
            conn.id, budget.id
        )

    await db_session.refresh(account)
    assert account.simplefin_account_id == NEW_ACCT, "the account repointed itself"
    assert result["adopted"] == rows_before, "existing rows took the new ids"
    assert result["imported"] == 1, "and the missed transaction arrived"
    assert len(await _live_rows(db_session, account.id)) == rows_before + 1


async def test_a_similar_name_is_never_relinked_automatically(db_session):
    """Two of one person's brokerage accounts score 0.95 against each other.
    A wrong relink files one account's transactions into another, so a similar
    name is only ever offered."""
    services, budget, account, conn = await _setup(db_session)
    account.simplefin_account_name = "Cascade Point Brokerage - Retirement"
    await db_session.flush()
    start = date.today() - timedelta(days=30)

    with PATCH_DECRYPT:
        result = await _service(
            services,
            _feed(NEW_ACCT, "new", start),
            names={NEW_ACCT: "Cascade Point Brokerage - Non-retirement"},
        ).sync(conn.id, budget.id)

    await db_session.refresh(account)
    assert account.simplefin_account_id == OLD_ACCT, "left alone for a person to decide"
    orphan = result["orphaned_links"][0]
    assert orphan["suggested_feed_id"] == NEW_ACCT, "but the suggestion is still offered"


async def test_two_candidates_sharing_a_name_relink_neither(db_session):
    """Ambiguity disqualifies: nothing distinguishes them."""
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    feed = _feed(NEW_ACCT, "new", start) + _feed("ACT-twin", "twin", start)
    with PATCH_DECRYPT:
        await _service(services, feed, names={NEW_ACCT: BANK_NAME, "ACT-twin": BANK_NAME}).sync(
            conn.id, budget.id
        )

    await db_session.refresh(account)
    assert account.simplefin_account_id == OLD_ACCT


async def test_auto_relink_can_be_switched_off(db_session):
    services, budget, account, conn = await _setup(db_session)
    from igab.repositories.settings_repo import SettingsRepository
    from igab.services.settings_service import SettingsService

    await SettingsService(SettingsRepository(db_session)).set("simplefin_auto_relink", "false")
    await db_session.flush()
    start = date.today() - timedelta(days=30)

    with PATCH_DECRYPT:
        result = await _service(
            services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME}
        ).sync(conn.id, budget.id)

    await db_session.refresh(account)
    assert account.simplefin_account_id == OLD_ACCT
    assert result["orphaned_links"][0]["account_name"] == "Harborstone Checking"


async def test_an_automatic_relink_is_undoable(db_session):
    """Recorded like a manual one, so Cmd+Z reaches it and the change log says
    it happened rather than implying it was always so."""
    from sqlalchemy import select

    from igab.db.models import ChangeLog

    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)
    with PATCH_DECRYPT:
        await _service(services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME}).sync(
            conn.id, budget.id
        )

    rows = (
        (
            await db_session.execute(
                select(ChangeLog).where(
                    ChangeLog.entity_type == "account", ChangeLog.entity_id == account.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows, "the relink left a change-log entry"
    assert rows[-1].before["simplefin_account_id"] == OLD_ACCT
    assert rows[-1].after["simplefin_account_id"] == NEW_ACCT


async def test_the_link_endpoint_forgets_when_the_account_last_synced(db_session, api_client):
    """A relink by hand resets the window the same way an automatic one does."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, simplefin_account_id=OLD_ACCT)
    account.last_simplefin_sync_at = datetime.now(UTC)
    await db_session.commit()

    r = await api_client.post(
        f"/api/v1/accounts/{account.id}/link-simplefin",
        json={"simplefin_account_id": NEW_ACCT, "simplefin_account_name": BANK_NAME},
    )
    assert r.status_code == 204, r.text
    await db_session.refresh(account)
    assert account.simplefin_account_id == NEW_ACCT
    assert account.last_simplefin_sync_at is None


async def test_refetch_asks_for_the_full_window_and_duplicates_nothing(db_session, api_client):
    """The recovery button. Pressed on an account with nothing missing it
    changes nothing; pressed after a gap it imports exactly the gap."""
    from igab.dependencies import get_simplefin_service
    from igab.main import app

    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(
        db_session, budget, "Harborstone Checking", simplefin_account_id=OLD_ACCT
    )
    conn = await create_simplefin_connection(db_session, api_client.test_user)
    await db_session.commit()
    services = make_services(db_session)
    start = date.today() - timedelta(days=30)
    missed = bank_txn(
        "old-missed",
        "-31.00",
        date.today() - timedelta(days=20),
        account=OLD_ACCT,
        payee="CORNER MARKET",
    )
    svc = _service(services, _feed(OLD_ACCT, "old", start) + [missed], honour_window=True)
    app.dependency_overrides[get_simplefin_service] = lambda: svc
    try:
        # The account's stamp says it was served an hour ago; the row twenty
        # days back is what a broken link missed.
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        await db_session.commit()
        await db_session.refresh(account)
        assert account.last_simplefin_sync_at is not None
        rows_before = len(await _live_rows(db_session, account.id))

        with PATCH_DECRYPT:
            r = await api_client.post(
                f"/api/v1/accounts/{account.id}/simplefin-refetch",
                json={"connection_id": str(conn.id)},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 0, "nothing was missing after a full first sync"
        assert body["skip_reasons"] == {"already_posted": len(HISTORY) + 1}
        assert len(await _live_rows(db_session, account.id)) == rows_before
        floor = datetime.now(UTC) - timedelta(days=SIMPLEFIN_MAX_WINDOW_DAYS)
        assert abs((svc.client.requests[-1] - floor).total_seconds()) < 60
    finally:
        app.dependency_overrides.pop(get_simplefin_service, None)


async def test_a_recurring_charge_never_adopts_a_neighbouring_weeks_row(db_session):
    """The duplicate cascade a 90-day refetch produced on a real budget.

    A coffee at the same price every week. One week's row was genuinely
    missing, so its feed record found no twin on its own day — and with the
    wide window used for rows a person typed, it reached back seven days,
    claimed the previous week's reconciled row, queued the pair for review
    and consumed it. The next feed record then found its own twin taken and
    claimed the week before that. Four duplicates of reconciled rows in one
    run, and a review queue full of pairs that were never the same purchase.

    Both sides here are the same bank's posting date for the same coffee, so
    the only honest answer is the same day.
    """
    services, budget, account, conn = await _setup(db_session)
    weeks = [date.today() - timedelta(days=d) for d in (35, 28, 21, 14, 7)]
    coffee = [
        bank_txn(f"old-c{i}", "-8.68", when, account=OLD_ACCT, payee="CASCADE COFFEE")
        for i, when in enumerate(weeks)
    ]

    # Every week but the most recent is already in the register, reconciled.
    with PATCH_DECRYPT:
        await _service(services, coffee[:-1]).sync(conn.id, budget.id)
    for row in await _live_rows(db_session, account.id):
        row.cleared = "reconciled"
    await db_session.flush()
    assert len(await _live_rows(db_session, account.id)) == len(weeks) - 1

    # The bank re-issues every id and the full window is asked for again —
    # including the week that was missing.
    await _relink(db_session, account, OLD_ACCT)
    fresh = [
        bank_txn(f"new-c{i}", "-8.68", when, account=OLD_ACCT, payee="CASCADE COFFEE")
        for i, when in enumerate(weeks)
    ]
    with PATCH_DECRYPT:
        result = await _service(services, fresh).sync(conn.id, budget.id)

    assert result["adopted"] == len(weeks) - 1, "each week took its own new id"
    assert result["imported"] == 1, "only the missing week is new"
    assert result["review_queued"] == 0, "no week is ever offered against another"
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == len(weeks), "a refetch must not duplicate a recurring charge"
    assert {r.sync_id for r in rows} == {f"new-c{i}" for i in range(len(weeks))}


async def test_a_row_the_user_dated_earlier_adopts_on_the_banks_posted_date(db_session):
    """The other half, and the reason the window cannot simply be tightened
    on the row's own date.

    A bill the user entered on the 16th posted at the bank on the 25th; the
    two were merged, so the row carries the user's date and the bank's
    posting date. When the bank re-issued the id, comparing on the user's
    date made the row look nine days from its own posting — past the auto
    threshold — and the payment was written a second time.
    """
    services, budget, account, conn = await _setup(db_session)
    posted_on = date.today() - timedelta(days=20)
    entered_on = posted_on - timedelta(days=9)

    with PATCH_DECRYPT:
        await _service(
            services,
            [
                bank_txn(
                    "old-bill", "-125.00", posted_on, account=OLD_ACCT, payee="NORTHWIND UTILITIES"
                )
            ],
        ).sync(conn.id, budget.id)
    [row] = await _live_rows(db_session, account.id)
    # What a merge leaves behind: the person's date, the bank's posting date.
    row.date = entered_on
    row.cleared = "reconciled"
    await db_session.flush()

    await _relink(db_session, account, OLD_ACCT)
    with PATCH_DECRYPT:
        result = await _service(
            services,
            [
                bank_txn(
                    "new-bill", "-125.00", posted_on, account=OLD_ACCT, payee="NORTHWIND UTILITIES"
                )
            ],
        ).sync(conn.id, budget.id)

    assert result["adopted"] == 1, result
    assert result["imported"] == 0, "the bill must not be written twice"
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1
    assert rows[0].sync_id == "new-bill"
    assert rows[0].date == entered_on, "the person's date is theirs, not the bank's"
