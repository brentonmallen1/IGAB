"""Every report is read for the reader's day, not the server's.

The container runs on UTC, so from 8pm Eastern the server is already in
tomorrow, and on a month's last evening in next month. Two reports honoured
`client_today`; the rest read the server's clock, so on the evening of
31 August, Net Worth drew a September point, the averaging reports called
August complete with an evening still to go, and the Overview's net-worth
card — which was reader-dated — fell back to a stated asset's step function
because its "now" was not the server's.

The reader here is on the last day of the month before the server's: one day
before the boundary, at the latest. Two rows mark the line — a paycheck and a
few groceries on the reader's today, and a 5,000 grocery spike on the first
of the server's month, which is the reader's tomorrow and must be in nothing.

Parametrised over the endpoints, with a ratchet: a report route added without
a row here fails `test_every_report_route_is_covered`.
"""

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.db.models import Asset, WishlistItem
from igab.domain.dates import add_months, month_start, months_spanned
from igab.main import app

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_liability,
    create_liability_snapshot,
    create_payee,
    create_transaction,
    tag_with_system_tags,
)

D = Decimal
SERVER_MONTH = month_start(date.today())
#: The reader's today: the last day of the month before the server's.
READER = SERVER_MONTH - timedelta(days=1)
READER_MONTH = month_start(READER)
#: The last complete month, as the reader sees it.
LAST_COMPLETE = add_months(READER_MONTH, -1)
#: The reader's tomorrow — on or before the server's today.
AHEAD = SERVER_MONTH
#: Six complete months of groceries before the reader's month: enough history
#: for the anomaly report to score anything.
GROCERIES = [D("90"), D("110"), D("100"), D("95"), D("105"), D("100")]
FIRST = add_months(READER_MONTH, -len(GROCERIES)) + timedelta(days=4)


def num(value) -> Decimal:
    return D(str(value))


async def _household(db_session, user):
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    sysgroup = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, sysgroup, "Ready to Assign")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    streaming = await create_category(db_session, budget, everyday, "Streaming")
    await tag_with_system_tags(db_session, streaming, "subscription")
    payserv = await create_payee(db_session, budget, "Northwind Payserv")
    market = await create_payee(db_session, budget, "Harborstone Market")

    async def paycheck(day: date) -> None:
        await create_transaction(
            db_session, budget, checking, "3000.00", day, payee=payserv, category=inflow
        )

    async def shop(day: date, amount: str) -> None:
        await create_transaction(
            db_session, budget, checking, amount, day, payee=market, category=groceries
        )

    for n, spent in enumerate(GROCERIES):
        day = add_months(FIRST, n)
        await paycheck(day)
        await shop(day, str(-spent))
    for n in (2, 1):
        day = add_months(READER_MONTH, -n) + timedelta(days=4)
        await create_transaction(db_session, budget, checking, "-15.00", day, category=streaming)
    # The line: the reader's today, and the reader's tomorrow.
    await paycheck(READER)
    await shop(READER, "-40.00")
    await paycheck(AHEAD)
    await shop(AHEAD, "-5000.00")

    # A stated value with no dated point: "now" reads it, a past day cannot.
    db_session.add(Asset(budget_id=budget.id, name="Car", manual_value=D("1000")))
    # A stated debt, recorded at the start and unchanged since.
    loan = await create_liability(db_session, budget, "Jane Doe Loan", manual_balance=D("5000"))
    await create_liability_snapshot(db_session, loan, FIRST, D("5000"))
    await db_session.flush()
    return budget, groceries


#: Cash as the reader's day closes: seven paychecks, less the groceries and
#: streaming through today. Not tomorrow's paycheck, nor the 5,000 spike.
CASH = D("21000") - (sum(GROCERIES) + D("40")) - D("30")
#: Net worth then: the cash, the car, less the loan.
NET_WORTH = CASH + D("1000") - D("5000")


def _no_spike(total) -> None:
    assert 0 < num(total) < D("5000")


#: (name, path, params, check) — `check` asserts what the reader's day decides.
Case = tuple[str, str, dict, Callable[[dict], None]]
CASES: list[Case] = [
    # Seven months touched through the reader's day; the server's day would
    # count its own month too.
    ("range", "range", {}, lambda d: _eq(d["months_available"], 7)),
    ("dashboard", "dashboard", {}, lambda d: _eq(num(d["net_worth"]), NET_WORTH)),
    (
        "net-worth",
        "net-worth",
        {"months": 3},
        lambda d: (
            _eq(d["points"][-1]["date"], READER_MONTH.isoformat()),
            _eq(num(d["points"][-1]["net_worth"]), NET_WORTH),
        ),
    ),
    (
        "account-composition",
        "account-composition",
        {"months": 3},
        lambda d: _eq(d["points"][-1]["date"], READER_MONTH.isoformat()),
    ),
    (
        "burn-rate",
        "burn-rate",
        {"months": 3},
        lambda d: _eq(d["points"][-1]["date"], READER_MONTH.isoformat()),
    ),
    (
        "income-expense",
        "income-expense",
        {"months": 3},
        lambda d: _eq(d["months"][-1]["month"], READER_MONTH.isoformat()),
    ),
    (
        "cash-flow",
        "cash-flow",
        {},
        lambda d: (
            _eq(num(d["total_income"]), D("3000")),
            _eq(num(d["total_expense"]), D("40")),
        ),
    ),
    ("budget-actual", "budget-actual", {}, lambda d: _eq(num(d["total_spent"]), D("40"))),
    (
        "plan-vs-reality",
        "plan-vs-reality",
        {"months": 3},
        lambda d: _eq(d["months"][-1], READER_MONTH.isoformat()),
    ),
    (
        "variance",
        "variance",
        {"months": 3},
        lambda d: _eq(d["points"][-1]["month"], READER_MONTH.isoformat()),
    ),
    (
        "volatility",
        "volatility",
        {"months": 3},
        lambda d: _eq(d["window_end"], (READER_MONTH - timedelta(days=1)).isoformat()),
    ),
    ("spending", "spending", {}, lambda d: _no_spike(d["total"])),
    ("spending-grouped", "spending-grouped", {}, lambda d: _eq(num(d["total"]), D("40"))),
    (
        "spending-trends",
        "spending-trends",
        {},
        lambda d: (
            _eq(d["months"], [READER_MONTH.isoformat()]),
            _eq(num(d["total"]), D("40")),
        ),
    ),
    (
        "income-by-source",
        "income-by-source",
        {"months": 3},
        lambda d: _eq(d["months"][-1], LAST_COMPLETE.isoformat()),
    ),
    (
        "category-history",
        "category-history",
        {"months": 3},  # category_id added per test
        lambda d: _eq(d["months"][-1]["month"], READER_MONTH.isoformat()),
    ),
    (
        "seasonality",
        "seasonality",
        {"months": 3},
        lambda d: _eq(d["months"][-1], LAST_COMPLETE.isoformat()),
    ),
    (
        "essentials",
        "essentials",
        {"months": 3},
        lambda d: _eq(d["window_end"], (READER_MONTH - timedelta(days=1)).isoformat()),
    ),
    ("payee-analysis", "payee-analysis", {}, lambda d: _no_spike(d["total"])),
    (
        "day-patterns",
        "day-patterns",
        {},
        lambda d: _no_spike(sum(num(day["total"]) for day in d["days"])),
    ),
    (
        "large-transactions",
        "large-transactions",
        {},
        lambda d: _eq([t for t in d["transactions"] if t["date"] == AHEAD.isoformat()], []),
    ),
    (
        "liabilities",
        "liabilities",
        {},
        lambda d: _eq(d["balance_over_time"][-1]["date"], READER_MONTH.isoformat()),
    ),
    (
        "subscriptions",
        "subscriptions",
        {"months": 3},
        lambda d: _eq(d["months"][-1], LAST_COMPLETE.isoformat()),
    ),
    (
        "savings-rate",
        "savings-rate",
        {"months": 3},
        # The summary's window is the reader's complete months (D5): it ends
        # the day before the reader's month began, not on the server's.
        lambda d: _eq(d["end_date"], (READER_MONTH - timedelta(days=1)).isoformat()),
    ),
    (
        "savings-contributors",
        "savings-contributors",
        {"start_date": READER_MONTH.isoformat(), "end_date": AHEAD.isoformat()},
        lambda d: _eq(d["end_date"], READER.isoformat()),
    ),
    (
        "savings",
        "savings",
        {"months": 3},
        lambda d: _eq(d["months"][-1], READER_MONTH.isoformat()),
    ),
    # The spike is the server's running month; the reader has not reached it.
    ("anomalies", "anomalies", {"months": 12}, lambda d: _eq(d["anomalies"], [])),
    # Seven paydays through the reader's day, not the eighth tomorrow.
    ("payday-effect", "payday-effect", {"months": 12}, lambda d: _eq(d["event_count"], 7)),
    (
        "cost-of-living",
        "cost-of-living",
        {"months": 3},
        lambda d: _eq(d["window_end"], (READER_MONTH - timedelta(days=1)).isoformat()),
    ),
    (
        "discretionary",
        "discretionary",
        {"months": 3},
        lambda d: _eq(d["window_end"], (READER_MONTH - timedelta(days=1)).isoformat()),
    ),
    # The path starts on the reader's today, from the cash that day closed on.
    (
        "cash-projection",
        "cash-projection",
        {"days": 30},
        lambda d: (
            _eq(d["points"][0]["date"], READER.isoformat()),
            _eq(num(d["start_balance"]), CASH),
        ),
    ),
    (
        "emergency-fund",
        "emergency-fund",
        {"months": 3},
        lambda d: _eq(d["current_month"], READER_MONTH.isoformat()),
    ),
    # A wish whose wait ends on the reader's tomorrow is still cooling for
    # the reader, and ready to decide on the server's day.
    (
        "wishlist",
        "wishlist",
        {},
        lambda d: (_eq(d["still_cooling"], 1), _eq(d["ready_to_decide"], 0)),
    ),
]

#: Report routes with no day in them: settings, favourites, the export (its
#: dates are the caller's).
NOT_DATED = {"favorites", "settings", "export"}


def _eq(actual, expected) -> None:
    assert actual == expected


@pytest.mark.parametrize(
    ("path", "params", "check"), [c[1:] for c in CASES], ids=[c[0] for c in CASES]
)
async def test_a_report_reads_the_readers_day(api_client, db_session, path, params, check):
    budget, groceries = await _household(db_session, api_client.test_user)
    if path == "category-history":
        params = {**params, "category_id": str(groceries.id)}
    if path == "wishlist":
        db_session.add(
            WishlistItem(
                budget_id=budget.id,
                name="Standing desk",
                cost=D("400"),
                added_on=READER - timedelta(days=29),
                cooling_until=AHEAD,
            )
        )
        await db_session.flush()

    resp = await api_client.get(
        f"/api/v1/{budget.id}/reports/{path}",
        params={**params, "client_today": READER.isoformat()},
    )

    assert resp.status_code == 200, resp.text
    check(resp.json())


async def test_without_a_reader_the_server_day_decides(api_client, db_session):
    """The fallback, pinned: a caller with no browser still gets an answer —
    the server's day, and so the server's month."""
    budget, _ = await _household(db_session, api_client.test_user)
    resp = await api_client.get(f"/api/v1/{budget.id}/reports/range")
    assert resp.json()["months_available"] == months_spanned(FIRST, date.today()) == 8


def test_every_report_route_is_covered():
    """A report route added without a row above has not been shown to read the
    reader's day — which is how twenty-odd of them came not to."""
    served = {
        route.path.rsplit("/reports/", 1)[1]
        for route in app.routes
        if "/reports/" in getattr(route, "path", "") and "GET" in getattr(route, "methods", ())
    }
    covered = {c[1] for c in CASES}
    assert served - covered - NOT_DATED == set()
    assert covered <= served
