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
from unittest.mock import patch

from sqlalchemy import select

from igab.db.models import Transaction
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
    def __init__(self, payload, names=None, errors=None):
        self.payload = payload
        self.names = names or {}
        self.errors = errors or []

    async def get_feed(self, access_url: str, since=None) -> SimpleFINFeed:
        return SimpleFINFeed(
            transactions=self.payload,
            balances={},
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


#: Eight is above MIN_IDS_FOR_REIDENTIFICATION, so the wholesale swap below is
#: evidence rather than coincidence. Amounts are distinct so each feed row has
#: exactly one candidate and the pairing is unambiguous.
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


def _service(services, payload, names=None, errors=None) -> SimpleFINService:
    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = FakeClient(payload, names, errors)
    return svc


async def _live_rows(db_session, account_id) -> list[Transaction]:
    result = await db_session.execute(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.is_deleted == False,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def test_relinked_account_adopts_its_history_instead_of_duplicating_it(db_session):
    """The 277-duplicate regression, end to end."""
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

    # The user relinks at the bridge: new account id, and every transaction
    # arrives with an id the register has never seen.
    account.simplefin_account_id = NEW_ACCT
    await db_session.flush()

    with PATCH_DECRYPT:
        second = await _service(
            services, _feed(NEW_ACCT, "new", start), names={NEW_ACCT: BANK_NAME}
        ).sync(conn.id, budget.id)

    assert second.get("error") is None, second
    assert second["adopted"] == len(HISTORY), second
    assert second["imported"] == 0, second

    after = await _live_rows(db_session, account.id)
    assert len(after) == len(HISTORY), "a re-link must not double the register"

    # The adopted rows carry the new bank ids, so the *next* sync recognises
    # them — without this the duplication simply recurs on the next run.
    assert {r.sync_id for r in after} == {f"new-{i}" for i in range(len(HISTORY))}
    # And they are still the user's rows.
    assert all(r.category_id == category.id for r in after)
    assert all(r.cleared == "reconciled" for r in after)


async def test_adoption_is_stable_on_a_second_sync(db_session):
    """Once adopted, the account is ordinary again: no further adoption, no
    duplicates, nothing but already-posted skips."""
    services, budget, account, conn = await _setup(db_session)
    start = date.today() - timedelta(days=30)

    with PATCH_DECRYPT:
        await _service(services, _feed(OLD_ACCT, "old", start)).sync(conn.id, budget.id)
    account.simplefin_account_id = NEW_ACCT
    await db_session.flush()

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
    account.simplefin_account_id = NEW_ACCT
    await db_session.flush()
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
    account.simplefin_account_id = NEW_ACCT
    await db_session.flush()

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
