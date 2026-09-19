"""A gap between the bank's balance and the ledger's, decomposed.

The incident: a Harborstone checking account reconciled clean, and the page
then announced that the bank held more than the ledger and that "something
may not have been pulled in — fetch the last 90 days again". Nothing was
missing. Four purchases the bank's own site already showed as posted were
still `pending` in the feed, so the user ticked them cleared before
reconciling; the ledger was AHEAD of the feed, which is the opposite of the
failure the message named.

Three things follow from that, and this file holds all three to the paths
that actually serve them:

1. the bridge's `balance-date` is stored, so a balance can be known to be
   stale rather than assumed live;
2. a gap made of rows the bank has not posted is not a fault, and the
   account response says which kind of gap it is;
3. a row the user cleared ahead of the bank is still adoptable, so a bank
   that re-identifies it at posting cannot write a duplicate onto a
   reconciled account.

Figures are invented and rescaled — see the personal-data rule in CLAUDE.md.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import select

from igab.db.models import Account, Transaction
from igab.integrations.simplefin.client import SimpleFINFeed
from igab.services.simplefin_service import SimpleFINService
from igab.services.transaction_service import TransactionUpdate

from .factories import (
    create_account,
    create_budget,
    create_simplefin_connection,
    create_user,
    make_services,
)

ACCT = "ACT-harborstone"
PATCH_DECRYPT = patch("igab.services.simplefin_service.decrypt", return_value="https://u:p@x.test")

TODAY = date(2026, 9, 19)
#: The four holds, rescaled. Distinct amounts so every feed row has exactly
#: one candidate and no pairing is ambiguous.
HOLDS = [("-20.00", "WHISTLE EXPRESS"), ("-75.00", "PAYPAL TRANSFER")]
UNPOSTED_TOTAL = Decimal("-95.00")


def _ts(d: date, hour: int = 12) -> int:
    return int(datetime(d.year, d.month, d.day, hour, tzinfo=UTC).timestamp())


def bank_txn(txn_id: str, amount: str, on: date, *, payee: str, posted: bool) -> dict:
    """A feed row. `posted=False` is an auth hold: the protocol's own way of
    saying the bank has not settled it, and what the bridge kept reporting
    for rows the bank's website already showed."""
    return {
        "id": txn_id,
        "account_id": ACCT,
        "amount": amount,
        "payee": payee,
        "description": f"{payee} POS PURCHASE",
        "posted": _ts(on) if posted else 0,
        "transacted_at": _ts(on),
    }


class FakeClient:
    def __init__(self, payload, balances=None, balance_dates=None):
        self.payload = payload
        self.balances = balances or {}
        self.balance_dates = balance_dates or {}

    async def get_feed(self, access_url: str, since=None) -> SimpleFINFeed:
        return SimpleFINFeed(
            transactions=list(self.payload),
            balances=dict(self.balances),
            balance_dates=dict(self.balance_dates),
        )

    async def get_accounts(self, access_url: str) -> list[dict]:
        return []


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(
        db_session, budget, "Harborstone Checking", simplefin_account_id=ACCT
    )
    conn = await create_simplefin_connection(db_session, user)
    await db_session.flush()
    return services, budget, account, conn


def _service(services, payload, balances=None, balance_dates=None) -> SimpleFINService:
    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = FakeClient(payload, balances, balance_dates)
    return svc


def _holds() -> list[dict]:
    return [
        bank_txn(f"hold-{i}", amount, TODAY - timedelta(days=i + 1), payee=payee, posted=False)
        for i, (amount, payee) in enumerate(HOLDS)
    ]


async def _tick_cleared(services, budget, account_id) -> None:
    """What the user does in the register when the bank's site shows a hold
    as posted and the feed has not caught up."""
    result = await services.session.execute(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.cleared == "pending",
            Transaction.is_deleted == False,  # noqa: E712
        )
    )
    for row in result.scalars().all():
        await services.transactions.update(budget.id, row.id, TransactionUpdate(cleared="cleared"))


async def _reconcile(db_session, account: Account, at_balance: Decimal) -> None:
    account.last_reconciled_at = datetime.now(UTC)
    account.last_reconciled_balance = at_balance
    await db_session.flush()


class TestBalanceDateIsStored:
    async def test_the_bridge_s_own_date_is_kept(self, db_session):
        """Without it the balance reads as live, and a bridge a day behind
        turns an hour of ordinary spending into 'rows are missing'."""
        services, budget, account, conn = await _setup(db_session)
        computed_at = datetime(2026, 9, 18, 14, 0, tzinfo=UTC)
        svc = _service(
            services,
            _holds(),
            balances={ACCT: Decimal("1000.00")},
            balance_dates={ACCT: computed_at},
        )
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        await db_session.refresh(account)
        assert account.simplefin_balance_date == computed_at

    async def test_a_bridge_that_says_nothing_leaves_it_null(self, db_session):
        """Every account was this before the column existed. A missing date
        must not read as a stale one."""
        services, budget, account, conn = await _setup(db_session)
        svc = _service(services, _holds(), balances={ACCT: Decimal("1000.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        await db_session.refresh(account)
        assert account.simplefin_balance_date is None


class TestAGapTheFeedHasNotCaughtUpWith:
    async def test_it_is_not_reported_as_a_fault(self, db_session):
        """The regression this whole change exists for. The bank's balance
        excludes the two holds; the ledger includes them because the user
        ticked them cleared. That gap is not missing rows."""
        services, budget, account, conn = await _setup(db_session)
        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)

        await _tick_cleared(services, budget, account.id)
        cleared = await services.account_repo.get_cleared_balance(account.id)
        assert cleared == UNPOSTED_TOTAL
        await _reconcile(db_session, account, cleared)

        # The bank still reports zero: it has posted none of it.
        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            result = await svc.sync(conn.id, budget.id)
        assert result["balance_drift"] == []

    async def test_an_unexplained_remainder_is_still_a_fault(self, db_session):
        """A hand-typed row carries no bank id, so nothing can say the bank
        has not posted it. That part of the gap stays news — and the record
        names it separately from the part that is explained."""
        services, budget, account, conn = await _setup(db_session)
        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        await _tick_cleared(services, budget, account.id)
        await services.transactions.create(
            budget.id,
            _typed_row(account.id),
        )
        cleared = await services.account_repo.get_cleared_balance(account.id)
        await _reconcile(db_session, account, cleared)

        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            result = await svc.sync(conn.id, budget.id)
        [drift] = result["balance_drift"]
        assert Decimal(drift["unposted_cleared"]) == UNPOSTED_TOTAL
        assert Decimal(drift["unexplained_amount"]) == Decimal("25.00")

    async def test_a_stale_balance_is_not_a_fault(self, db_session):
        """The bank computed its figure before the ledger's newest cleared
        row, so the two are not measuring the same moment."""
        services, budget, account, conn = await _setup(db_session)
        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        await services.transactions.create(budget.id, _typed_row(account.id))
        cleared = await services.account_repo.get_cleared_balance(account.id)
        await _reconcile(db_session, account, cleared)

        svc = _service(
            services,
            _holds(),
            balances={ACCT: Decimal("0.00")},
            balance_dates={ACCT: datetime(2020, 1, 1, tzinfo=UTC)},
        )
        with PATCH_DECRYPT:
            result = await svc.sync(conn.id, budget.id)
        assert result["balance_drift"] == []


class TestWhatTheAccountPageIsServed:
    async def test_the_reason_and_both_figures(self, db_session):
        services, budget, account, conn = await _setup(db_session)
        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        await _tick_cleared(services, budget, account.id)
        cleared = await services.account_repo.get_cleared_balance(account.id)
        await _reconcile(db_session, account, cleared)

        unposted = await services.account_repo.get_unposted_cleared(account.id)
        assert unposted == UNPOSTED_TOTAL

    async def test_a_hand_typed_row_is_never_called_unposted(self, db_session):
        """`sync_id IS NOT NULL` is what keeps the figure honest: an old
        cleared row is indistinguishable from one the bank has not posted."""
        services, budget, account, _conn = await _setup(db_session)
        await services.transactions.create(budget.id, _typed_row(account.id))
        assert await services.account_repo.get_unposted_cleared(account.id) == Decimal("0")

    async def test_newest_cleared_on_ignores_pending_rows(self, db_session):
        """Pending money is in no aggregate until it posts, and a pending row
        must not make the bank's balance look stale."""
        services, budget, account, conn = await _setup(db_session)
        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        assert await services.account_repo.get_newest_cleared_on(account.id) is None


class TestARowClearedAheadOfTheBankStaysAdoptable:
    """A row the user cleared ahead of the bank leaves PROVISIONALLY_LINKED,
    which is the sync's own "the bank has not posted this" set. It does not
    thereby lose its adoption path — `orphaned_link` offers any row inside
    the window whose id the feed stopped reporting, with no `cleared` guard
    at all — but that is worth pinning, because the cost of being wrong is a
    duplicate on a reconciled account.
    """

    async def test_a_re_identified_posting_claims_it_instead_of_duplicating(self, db_session):
        """The bank retires the pending id and posts under a new one, which
        is what re-identification looks like in the feed."""
        services, budget, account, conn = await _setup(db_session)
        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        await _tick_cleared(services, budget, account.id)
        assert len(await _live_rows(db_session, account.id)) == len(HOLDS)

        # The first hold comes back posted under a fresh id; the old id is
        # gone from the feed, as a real re-identification leaves it.
        reposted = bank_txn(
            "posted-0", HOLDS[0][0], TODAY - timedelta(days=1), payee=HOLDS[0][1], posted=True
        )
        svc = _service(services, [_holds()[1], reposted], balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)

        after = await _live_rows(db_session, account.id)
        assert len(after) == len(HOLDS), "the posting claimed the row it belonged to"
        claimed = next(r for r in after if r.sync_id == "posted-0")
        assert claimed.bank_posted_date == TODAY - timedelta(days=1)

    async def test_the_ordinary_same_id_posting_still_stamps_the_date(self, db_session):
        """The main road: most banks keep the id from pending to posted, and
        a row the user cleared early must still pick up the posting date —
        otherwise it counts as unposted forever and skews the drift."""
        services, budget, account, conn = await _setup(db_session)
        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        await _tick_cleared(services, budget, account.id)

        posted = [
            bank_txn(f"hold-{i}", amount, TODAY - timedelta(days=i + 1), payee=payee, posted=True)
            for i, (amount, payee) in enumerate(HOLDS)
        ]
        svc = _service(services, posted, balances={ACCT: UNPOSTED_TOTAL})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)

        rows = await _live_rows(db_session, account.id)
        assert all(r.bank_posted_date is not None for r in rows)
        assert await services.account_repo.get_unposted_cleared(account.id) == Decimal("0")

    async def test_a_dropped_hold_the_user_cleared_is_kept_and_stays_visible(self, db_session):
        """The bank drops the auth and never posts it. The sweep that deletes
        stale pending rows deliberately does not touch one the user marked
        cleared — they said it happened. It therefore sits in the ledger for
        good, which is exactly why `unposted_cleared` is served: the figure
        names it on the account page instead of leaving a silent gap.
        """
        services, budget, account, conn = await _setup(db_session)
        svc = _service(services, _holds(), balances={ACCT: Decimal("0.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)
        await _tick_cleared(services, budget, account.id)

        # Both ids vanish from the feed: the bank dropped the holds.
        survivor = bank_txn("unrelated", "-5.00", TODAY, payee="CASCADE COFFEE", posted=True)
        svc = _service(services, [survivor], balances={ACCT: Decimal("-5.00")})
        with PATCH_DECRYPT:
            await svc.sync(conn.id, budget.id)

        rows = await _live_rows(db_session, account.id)
        assert len([r for r in rows if r.sync_id and r.sync_id.startswith("hold-")]) == len(HOLDS)
        assert await services.account_repo.get_unposted_cleared(account.id) == UNPOSTED_TOTAL


def _typed_row(account_id):
    """A row the user entered by hand: an outflow the bank has never seen."""
    from igab.services.transaction_service import TransactionCreate

    return TransactionCreate(
        account_id=account_id,
        date=TODAY,
        amount=Decimal("-25.00"),
        payee_name="Cascade Florist",
        cleared="cleared",
    )


async def _live_rows(db_session, account_id) -> list[Transaction]:
    result = await db_session.execute(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.parent_transaction_id.is_(None),
        )
    )
    return list(result.scalars().all())
