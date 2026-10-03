"""A household that migrates from YNAB first and connects its bank second.

The order matters, and it is the order most people arrive in: the budget
comes over from YNAB with months of history, cleaned payees and its own
cleared states, and only then does the bank join — a SimpleFIN link on the
checking account, a downloaded CSV for the card. Each half had its own
defect when met in that order: the CSV import matched nothing (a cleaned
payee never collides with a raw descriptor's import id), and the first sync
wrote a Starting Balance over history the account already held, sized
against a ledger that counted every queued review twice.

So, end to end, on Harborstone Checking (synced) and Sapphire Visa (CSV):

- only the genuinely new bank rows are added;
- no Starting Balance row exists on either account;
- the review queue holds exactly the pairs built here to be ambiguous — a
  descriptor that shares nothing with the payee, three days late;
- once those are accepted each account's cleared balance is the bank's;
- and a later CSV of the synced account adds nothing, because its rows are
  now bank-linked and the file's ladder still sees them (`any_bank_state`).

Every figure is invented and round enough to add up on paper. Dates are day
offsets back from the UTC date the sync itself reads, never months.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Account, Budget, SimpleFINConnection, Transaction
from igab.integrations.ynab.models import YNABBudget, YNABTransaction
from igab.repositories.txn_filters import STARTING_BALANCE_ROW
from igab.utils.clock import today_utc

from .factories import Services, create_budget, create_simplefin_connection, make_services
from .test_simplefin_sync import PATCH_DECRYPT, SF_ACCT, _service, bank_txn
from .test_ynab_import import _importer

CHECKING = "Harborstone Checking"
CARD = "Sapphire Visa"
HEADER = "Posted Date,Description,Debit,Credit\n"


@dataclass(frozen=True)
class Row:
    """One YNAB row, and — when it falls inside the bank's 90 days — how the
    bank reports it: `lag` days later, under its own descriptor."""

    days_ago: int
    amount: str
    payee: str
    cleared: str
    category: tuple[str, str] | None = None
    bank: str | None = None
    lag: int = 0


INCOME = ("Inflow", "Ready to Assign")
RENT = ("Bills", "Rent")
GROCERIES = ("Everyday", "Groceries")
FUEL = ("Everyday", "Fuel")
POWER = ("Bills", "Electric")
YARD = ("Home", "Yard")
SHOPPING = ("Everyday", "Clothing")
STREAMING = ("Bills", "Streaming")
DINING = ("Everyday", "Dining Out")

TJ = "TRADER JOE'S #552 SEATTLE WA"
PAY = "NORTHWIND PAYSERV DIR DEP"

#: Harborstone Checking as YNAB had it. The rows from 91+ days back are
#: history the bank's 90-day feed cannot carry; the rest each have a twin in
#: the feed. Sum: 3,090 before the window + 5,205 inside it = 8,295.
CHECKING_HISTORY = [
    Row(119, "3000.00", "Northwind Payserv", "reconciled", INCOME),
    Row(112, "-1200.00", "Jane Doe", "reconciled", RENT),
    Row(105, "-150.00", "Trader Joe's", "reconciled", GROCERIES),
    Row(98, "-60.00", "Shell", "reconciled", FUEL),
    Row(95, "-500.00", f"Transfer : {CARD}", "reconciled"),
    Row(91, "2000.00", "Northwind Payserv", "reconciled", INCOME),
    # ── inside the feed's window ──
    Row(84, "-1200.00", "Jane Doe", "reconciled", RENT, "JANE DOE RENT ACH", 1),
    Row(77, "2000.00", "Northwind Payserv", "reconciled", INCOME, PAY, 2),
    Row(70, "-120.00", "Trader Joe's", "reconciled", GROCERIES, TJ, 0),
    Row(63, "2000.00", "Northwind Payserv", "cleared", INCOME, PAY, 2),
    Row(56, "-1200.00", "Jane Doe", "cleared", RENT, "jane doe rent ach", 1),
    # The card payment's checking leg — paired with the card's by the import.
    Row(50, "-500.00", f"Transfer : {CARD}", "cleared", None, "SAPPHIRE VISA ONLINE PMT", 0),
    Row(49, "-80.00", "Shell", "cleared", FUEL, "SHELL OIL 57442", 3),
    Row(42, "-40.00", "Brightline Electric", "cleared", POWER, "BRIGHTLINE ELEC AUTOPAY", 0),
    Row(35, "2000.00", "Northwind Payserv", "cleared", INCOME, PAY, 2),
    Row(28, "-1200.00", "Jane Doe", "cleared", RENT, "JANE DOE RENT ACH", 1),
    Row(21, "2000.00", "Northwind Payserv", "cleared", INCOME, PAY, 2),
    # DELIBERATELY AMBIGUOUS: a check, cashed three days later under a
    # descriptor that shares nothing with the payee. Same amount, but too far
    # apart for the structural rung and too unlike for the payee rung — so
    # the ladder asks. Cleared in YNAB, so until it is answered the cleared
    # balance holds it twice.
    Row(20, "-300.00", "Lawn Service", "cleared", YARD, "CHECK 1043", 3),
    Row(14, "-95.00", "Trader Joe's", "uncleared", GROCERIES, TJ.lower(), 2),
    Row(7, "2000.00", "Northwind Payserv", "uncleared", INCOME, PAY, 2),
    Row(5, "-60.00", "Shell", "uncleared", FUEL, "SHELL OIL 57442", 1),
]

#: In the feed and nowhere in YNAB. Sum: −112.
CHECKING_NEW = [
    (10, "-100.00", "ATM WITHDRAWAL 0042"),
    (3, "-12.00", "MONTHLY SERVICE FEE"),
]

#: 8,295 in YNAB − 112 the household never typed.
CHECKING_REPORTED = Decimal("8183.00")

#: Sapphire Visa as YNAB had it. Sum: +70 before the window − 411 inside = −341.
CARD_HISTORY = [
    Row(118, "-250.00", "Nordstrom", "reconciled", SHOPPING),
    Row(110, "-60.00", "Shell", "reconciled", FUEL),
    Row(100, "-120.00", "Trader Joe's", "reconciled", GROCERIES),
    Row(95, "500.00", f"Transfer : {CHECKING}", "reconciled"),
    # ── inside the file's window ──
    Row(86, "-15.00", "Netflix", "reconciled", STREAMING, "NETFLIX.COM 866-579", 0),
    Row(80, "-90.00", "Trader Joe's", "reconciled", GROCERIES, TJ, 1),
    Row(72, "-45.00", "Shell", "cleared", FUEL, "SHELL OIL 57442", 2),
    Row(60, "-300.00", "Nordstrom", "cleared", SHOPPING, "NORDSTROM #0420", 3),
    # The payment's card leg: a descriptor nothing like the transfer payee,
    # but a day late with nothing else near it — the structural rung.
    Row(50, "500.00", f"Transfer : {CHECKING}", "cleared", None, "PAYMENT THANK YOU", 1),
    Row(44, "-15.00", "Netflix", "cleared", STREAMING, "netflix.com", 0),
    # DELIBERATELY AMBIGUOUS: a market stall's card reader, three days late,
    # under a processor's descriptor. Never cleared in YNAB.
    Row(38, "-240.00", "Hearth & Home", "uncleared", SHOPPING, "SQ *HH GOODS 8812", 3),
    Row(30, "-110.00", "Trader Joe's", "cleared", GROCERIES, TJ.lower(), 2),
    Row(16, "-15.00", "Netflix", "uncleared", STREAMING, "NETFLIX.COM 866-579", 0),
    Row(9, "-6.00", "Cascade Coffee", "uncleared", DINING, "CASCADE COFFEE #4", 1),
    Row(6, "-75.00", "Shell", "uncleared", FUEL, "SHELL OIL 57442", 2),
]

#: In the file and nowhere in YNAB. Sum: −40.
CARD_NEW = [
    (20, "-32.00", "AMAZON MKTP US*2K4"),
    (12, "-8.00", "CITY PARKING 118"),
]

#: The statement's balance: −341 in YNAB − 40 the household never typed.
CARD_STATEMENT = Decimal("-381.00")


def _windowed(history: list[Row]) -> list[Row]:
    return [r for r in history if r.bank is not None]


def _ynab_budget(today: date) -> YNABBudget:
    def txn(account: str, row: Row) -> YNABTransaction:
        group, category = row.category or (None, None)
        return YNABTransaction(
            account_name=account,
            date=today - timedelta(days=row.days_ago),
            payee=row.payee,
            category_group=group,
            category=category,
            memo=None,
            amount=Decimal(row.amount),
            cleared=row.cleared,
        )

    return YNABBudget(
        transactions=[
            *(txn(CHECKING, r) for r in CHECKING_HISTORY),
            *(txn(CARD, r) for r in CARD_HISTORY),
        ]
    )


def _checking_feed(today: date) -> list[dict]:
    """The bank's 90 days of Harborstone Checking, as SimpleFIN serves them."""
    feed = [
        bank_txn(
            f"hb-{r.days_ago}",
            r.amount,
            today - timedelta(days=r.days_ago - r.lag),
            payee=r.bank or "",
        )
        for r in _windowed(CHECKING_HISTORY)
    ]
    feed += [
        bank_txn(f"hb-new-{days}", amount, today - timedelta(days=days), payee=name)
        for days, amount, name in CHECKING_NEW
    ]
    return feed


def _csv_line(day: date, amount: str, descriptor: str) -> str:
    value = Decimal(amount)
    debit, credit = (f"{-value:.2f}", "") if value < 0 else ("", f"{value:.2f}")
    return f"{day.isoformat()},{descriptor},{debit},{credit}\n"


def _card_csv(today: date) -> str:
    """The card's 90-day download, in posting order."""
    lines = [
        (today - timedelta(days=r.days_ago - r.lag), r.amount, r.bank or "")
        for r in _windowed(CARD_HISTORY)
    ]
    lines += [(today - timedelta(days=d), amount, name) for d, amount, name in CARD_NEW]
    lines.sort(key=lambda line: line[0])
    return HEADER + "".join(_csv_line(*line) for line in lines)


def _checking_csv(today: date) -> str:
    """Harborstone Checking's own 90-day download: the very rows the feed
    already delivered, same dates, same descriptors."""
    lines = [
        (today - timedelta(days=r.days_ago - r.lag), r.amount, r.bank or "")
        for r in _windowed(CHECKING_HISTORY)
    ]
    lines += [(today - timedelta(days=d), amount, name) for d, amount, name in CHECKING_NEW]
    lines.sort(key=lambda line: line[0])
    return HEADER + "".join(_csv_line(*line) for line in lines)


# ─── The migration, step by step ─────────────────────────────────────────────


@dataclass
class Household:
    services: Services
    budget: Budget
    checking: Account
    card: Account
    connection: SimpleFINConnection
    today: date


async def _migrate_from_ynab(db_session, api_client) -> Household:
    """Step one: the YNAB import, through the real importer, so the rows
    carry exactly what an import leaves — `created_via="import"`, an import
    id over the cleaned payee, YNAB's cleared state, linked transfer legs."""
    today = today_utc()
    services = make_services(db_session)
    budget = await create_budget(db_session, api_client.test_user)
    result = await _importer(
        services, db_session, budget, account_types={CARD: ("credit_card", True)}
    ).import_budget(_ynab_budget(today))
    assert result.errors == []
    assert result.transactions_imported == len(CHECKING_HISTORY) + len(CARD_HISTORY)

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    checking, card = accounts[CHECKING], accounts[CARD]
    assert await services.account_repo.get_balance(checking.id) == Decimal("8295.00")
    assert await services.account_repo.get_balance(card.id) == Decimal("-341.00")

    connection = await create_simplefin_connection(db_session, api_client.test_user)
    await db_session.commit()
    return Household(services, budget, checking, card, connection, today)


async def _link_and_sync_checking(db_session, home: Household) -> dict:
    """Step two: link Harborstone Checking and run its first sync."""
    home.checking.simplefin_account_id = SF_ACCT
    await db_session.flush()
    svc = _service(home.services, _checking_feed(home.today), {SF_ACCT: CHECKING_REPORTED})
    with PATCH_DECRYPT:
        result = await svc.sync(home.connection.id, home.budget.id)
    assert result.get("error") is None, result
    return result


async def _import_csv(api_client, home: Household, account: Account, csv: str) -> dict:
    r = await api_client.post(
        f"/api/v1/{home.budget.id}/import/csv",
        params={"account_id": str(account.id)},
        files={"file": ("export.csv", csv.encode(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _live(db_session, account: Account) -> list[Transaction]:
    await db_session.flush()
    result = await db_session.execute(
        select(Transaction).where(
            Transaction.account_id == account.id, Transaction.is_deleted.is_(False)
        )
    )
    return list(result.scalars())


async def _starting_balances(db_session, home: Household) -> list[Transaction]:
    await db_session.flush()
    result = await db_session.execute(
        select(Transaction).where(
            Transaction.account_id.in_((home.checking.id, home.card.id)),
            Transaction.is_deleted.is_(False),
            STARTING_BALANCE_ROW,
        )
    )
    return list(result.scalars())


async def _pending(home: Household, account: Account):
    return await home.services.match_repo.get_pending_for_account(account.id)


async def _accept_all(api_client, home: Household, account: Account) -> None:
    for match in await _pending(home, account):
        r = await api_client.post(f"/api/v1/simplefin/matches/{match.id}/accept")
        assert r.status_code == 204, r.text


async def _rows_by_id(db_session, ids) -> dict:
    rows = (await db_session.execute(select(Transaction).where(Transaction.id.in_(ids)))).scalars()
    return {t.id: t for t in rows}


# ─── The assertions ──────────────────────────────────────────────────────────


async def test_the_first_sync_adds_only_the_banks_new_rows(db_session, api_client):
    home = await _migrate_from_ynab(db_session, api_client)
    before = {t.id for t in await _live(db_session, home.checking)}

    result = await _link_and_sync_checking(db_session, home)

    # 15 windowed rows: 14 matched outright, 1 imported beside its YNAB twin
    # for review. Plus the 2 new rows.
    assert result["matched"] == len(_windowed(CHECKING_HISTORY)) - 1 == 14
    assert result["imported"] == len(CHECKING_NEW) + 1 == 3
    assert result["review_queued"] == 1
    # No anchor, and nothing to say about one: measured with the queued check
    # counted once, the register already IS the bank's figure, and agreement
    # is asked before history (`anchor_verdict`). Counted twice, as the
    # defect counted it, this was a 300.00 Starting Balance dated three months
    # back — the very row the next assertion forbids.
    assert result["anchored"] == 0
    assert result["refused_anchors"] == []
    assert result["anchors_skipped_for_history"] == []
    assert await _starting_balances(db_session, home) == []

    live = await _live(db_session, home.checking)
    added = [t for t in live if t.id not in before]
    assert sorted(t.amount for t in added) == sorted(
        [Decimal("-100.00"), Decimal("-12.00"), Decimal("-300.00")]
    )

    # The one review is the check, and nothing else.
    [match] = await _pending(home, home.checking)
    pair = await _rows_by_id(db_session, [match.manual_transaction_id, match.synced_transaction_id])
    ynab_side = pair[match.manual_transaction_id]
    bank_side = pair[match.synced_transaction_id]
    assert ynab_side.id in before and ynab_side.amount == Decimal("-300.00")
    assert bank_side.id not in before and bank_side.amount == Decimal("-300.00")

    # Every other YNAB row inside the window is now the bank's: linked, and
    # cleared where YNAB had it uncleared. Reconciled rows stay reconciled.
    windowed_from = home.today - timedelta(days=89)
    for txn in live:
        if txn.id not in before or txn.date < windowed_from or txn.id == ynab_side.id:
            continue
        await db_session.refresh(txn)
        assert txn.sync_id is not None, (txn.date, txn.amount)
        assert txn.cleared in ("cleared", "reconciled"), (txn.date, txn.amount)

    # Until the check is answered, the gap to the bank is the queue's.
    drift = (await home.services.account_repo.drift_for([home.checking]))[home.checking.id]
    assert drift is not None
    assert drift.reason == "in_review"
    assert drift.in_review == Decimal("-300.00")
    assert drift.unexplained == Decimal("0")


async def test_the_card_csv_adds_only_the_new_lines(db_session, api_client):
    home = await _migrate_from_ynab(db_session, api_client)
    before = {t.id for t in await _live(db_session, home.card)}

    result = await _import_csv(api_client, home, home.card, _card_csv(home.today))

    # 11 windowed lines: 10 matched, 1 written beside its YNAB twin for
    # review. The three uncleared matches are cleared by the file; the stall
    # charge stays uncleared until its review is answered.
    assert result["matched"] == len(_windowed(CARD_HISTORY)) - 1 == 10
    assert result["confirmed"] == 3
    assert result["imported"] == len(CARD_NEW) + 1 == 3
    assert result["review"] == 1
    assert result["errors"] == []
    assert await _starting_balances(db_session, home) == []

    live = await _live(db_session, home.card)
    added = [t for t in live if t.id not in before]
    assert sorted(t.amount for t in added) == sorted(
        [Decimal("-32.00"), Decimal("-8.00"), Decimal("-240.00")]
    )

    [match] = await _pending(home, home.card)
    pair = await _rows_by_id(db_session, [match.manual_transaction_id, match.synced_transaction_id])
    assert match.manual_transaction_id in before
    assert pair[match.manual_transaction_id].amount == Decimal("-240.00")
    assert pair[match.synced_transaction_id].amount == Decimal("-240.00")
    # And the checking account was never touched by the card's file.
    assert await _pending(home, home.checking) == []


async def test_after_the_reviews_each_account_agrees_with_its_bank(db_session, api_client):
    home = await _migrate_from_ynab(db_session, api_client)
    checking_rows = len(await _live(db_session, home.checking))
    card_rows = len(await _live(db_session, home.card))
    await _link_and_sync_checking(db_session, home)
    await _import_csv(api_client, home, home.card, _card_csv(home.today))

    await _accept_all(api_client, home, home.checking)
    await _accept_all(api_client, home, home.card)

    assert await _pending(home, home.checking) == []
    assert await _pending(home, home.card) == []
    # Net of the merges, exactly the genuinely new rows were added.
    assert len(await _live(db_session, home.checking)) == checking_rows + len(CHECKING_NEW)
    assert len(await _live(db_session, home.card)) == card_rows + len(CARD_NEW)
    assert await _starting_balances(db_session, home) == []

    repo = home.services.account_repo
    assert await repo.get_cleared_balance(home.checking.id) == CHECKING_REPORTED
    assert await repo.get_balance(home.checking.id) == CHECKING_REPORTED
    drift = (await repo.drift_for([home.checking]))[home.checking.id]
    assert drift is not None
    assert drift.reason == "agree"

    assert await repo.get_cleared_balance(home.card.id) == CARD_STATEMENT
    assert await repo.get_balance(home.card.id) == CARD_STATEMENT


async def test_a_later_csv_of_the_synced_account_adds_nothing(db_session, api_client):
    """Harborstone Checking's rows are bank-linked now. A statement download
    over the same 90 days describes exactly those rows, and the file's
    ladder must still see them — a candidate pool limited to unlinked rows
    would import the whole file again."""
    home = await _migrate_from_ynab(db_session, api_client)
    await _link_and_sync_checking(db_session, home)
    await _accept_all(api_client, home, home.checking)
    rows = len(await _live(db_session, home.checking))

    result = await _import_csv(api_client, home, home.checking, _checking_csv(home.today))

    assert result["imported"] == 0
    assert result["review"] == 0
    assert result["matched"] == len(_windowed(CHECKING_HISTORY)) + len(CHECKING_NEW) == 17
    # A file never rewrites what the feed owns.
    assert result["confirmed"] == 0
    assert len(await _live(db_session, home.checking)) == rows
    assert await _pending(home, home.checking) == []
    assert await home.services.account_repo.get_cleared_balance(home.checking.id) == (
        CHECKING_REPORTED
    )
