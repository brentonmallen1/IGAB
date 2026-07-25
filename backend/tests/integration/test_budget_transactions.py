"""Spec for GET /{budget_id}/transactions — the report drill-down listing.

Panel totals must reconcile exactly with the report aggregates they drill
into: leaf scope for category-keyed charts (split children as rows), parent
scope for payee/month charts (one row per real purchase), and POSTED /
CASH_FLOW_ROW semantics identical to report_service.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.services.report_service import ReportService
from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()
START = TODAY - timedelta(days=20)


async def _setup(api_client, db_session):
    services = make_services(db_session)
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    gas = await create_category(db_session, budget, everyday, "Gas")
    return services, budget, checking, savings, groceries, gas


async def _fetch(api_client, budget_id, **params):
    resp = await api_client.get(f"/api/v1/{budget_id}/transactions", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_split(services, budget, account, groceries, gas, *, payee_id=None):
    """The canonical -100 = -60 Groceries + -40 Gas split."""
    header = TransactionCreate(
        account_id=account.id,
        date=TODAY - timedelta(days=5),
        amount=Decimal("-100.00"),
        payee_id=payee_id,
        cleared="cleared",
    )
    splits = [
        TransactionCreate(
            account_id=account.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-60.00"),
            payee_id=payee_id,
            category_id=groceries.id,
        ),
        TransactionCreate(
            account_id=account.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-40.00"),
            payee_id=payee_id,
            category_id=gas.id,
        ),
    ]
    return await services.transactions.create_split(budget.id, header, splits)


async def test_date_boundaries_inclusive(api_client, db_session):
    _, budget, checking, _, groceries, _ = await _setup(api_client, db_session)
    for offset in (-1, 0, 10, 20, 21):  # days after START; window is START..START+20
        await create_transaction(
            db_session,
            budget,
            checking,
            "-10.00",
            START + timedelta(days=offset),
            category=groceries,
        )

    body = await _fetch(
        api_client,
        budget.id,
        start_date=START.isoformat(),
        end_date=(START + timedelta(days=20)).isoformat(),
    )
    dates = sorted(t["date"] for t in body["transactions"])
    assert len(dates) == 3
    assert dates[0] == START.isoformat()
    assert dates[-1] == (START + timedelta(days=20)).isoformat()
    assert body["total_count"] == 3
    assert Decimal(body["total_amount"]) == Decimal("-30.00")


async def test_split_leaf_scope_returns_children_not_parent(api_client, db_session):
    services, budget, checking, _, groceries, gas = await _setup(api_client, db_session)
    await _create_split(services, budget, checking, groceries, gas)

    body = await _fetch(
        api_client, budget.id, scope="leaf", category_ids=str(groceries.id)
    )
    assert body["total_count"] == 1
    assert Decimal(body["total_amount"]) == Decimal("-60.00")
    row = body["transactions"][0]
    assert Decimal(row["amount"]) == Decimal("-60.00")
    assert row["category_id"] == str(groceries.id)
    assert row["parent_transaction_id"] is not None  # a split child, not the parent

    # Leaf scope without a category filter: both children, never the parent
    body = await _fetch(api_client, budget.id, scope="leaf")
    assert body["total_count"] == 2
    assert all(not t["is_split"] for t in body["transactions"])


async def test_parent_scope_returns_split_as_one_row(api_client, db_session):
    services, budget, checking, _, groceries, gas = await _setup(api_client, db_session)
    payee = await create_payee(db_session, budget, "Superstore")
    await _create_split(services, budget, checking, groceries, gas, payee_id=payee.id)

    body = await _fetch(
        api_client, budget.id, scope="parent", payee_ids=str(payee.id)
    )
    assert body["total_count"] == 1
    row = body["transactions"][0]
    assert row["is_split"] is True
    assert Decimal(row["amount"]) == Decimal("-100.00")

    # Reconciles with the payee-analysis aggregate (PARENT_ROW-based)
    reports = ReportService(db_session)
    payees, _total = await reports.payee_analysis(budget.id, START, TODAY)
    superstore = next(p for p in payees if p["payee_name"] == "Superstore")
    assert abs(Decimal(body["total_amount"])) == Decimal(str(superstore["total"]))


async def test_leaf_reconciles_with_spending_report(api_client, db_session):
    services, budget, checking, savings, groceries, gas = await _setup(
        api_client, db_session
    )
    reports = ReportService(db_session)

    await create_transaction(
        db_session, budget, checking, "-200.00", TODAY - timedelta(days=6), category=groceries
    )
    await _create_split(services, budget, checking, groceries, gas)
    # Pending: excluded from spending aggregates
    await create_transaction(
        db_session,
        budget,
        checking,
        "-75.00",
        TODAY - timedelta(days=2),
        category=groceries,
        cleared="pending",
    )
    # On-budget transfer: internal movement, no category → not cash flow
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=3),
            amount=Decimal("150.00"),
            transfer_account_id=savings.id,
            cleared="cleared",
        ),
    )
    # Refund: positive amount in the category — spending charts count outflow only
    await create_transaction(
        db_session, budget, checking, "25.00", TODAY - timedelta(days=1), category=groceries
    )

    categories, _grand = await reports.spending_by_category(budget.id, START, TODAY)
    report_total = next(c["total"] for c in categories if c["name"] == "Groceries")

    body = await _fetch(
        api_client,
        budget.id,
        scope="leaf",
        posted_only=True,
        cash_flow_only=True,
        direction="outflow",
        category_ids=str(groceries.id),
        start_date=START.isoformat(),
        end_date=TODAY.isoformat(),
    )
    assert abs(Decimal(body["total_amount"])) == Decimal(str(report_total))
    assert body["total_count"] == 2  # plain -200 and split child -60


async def test_month_reconciles_with_income_vs_expense(api_client, db_session):
    services, budget, checking, savings, groceries, _ = await _setup(
        api_client, db_session
    )
    reports = ReportService(db_session)
    offbudget = await create_account(
        db_session, budget, "Brokerage", account_type="tracking", on_budget=False
    )
    payee = await create_payee(db_session, budget, "Employer")

    # All rows dated TODAY so the calendar-month window always contains them
    await create_transaction(db_session, budget, checking, "500.00", TODAY, payee=payee)
    await create_transaction(
        db_session, budget, checking, "-200.00", TODAY, category=groceries
    )
    # Uncategorized on-budget transfer: excluded from cash flow
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("150.00"),
            transfer_account_id=savings.id,
            cleared="cleared",
        ),
    )
    # Categorized transfer to an off-budget account: counts as spending
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("-50.00"),
            category_id=groceries.id,
            transfer_account_id=offbudget.id,
            cleared="cleared",
        ),
    )

    this_month = (await reports.income_vs_expense(budget.id, months=1))[-1]

    month_start = TODAY.replace(day=1)
    body = await _fetch(
        api_client,
        budget.id,
        scope="parent",
        posted_only=True,
        cash_flow_only=True,
        start_date=month_start.isoformat(),
        end_date=TODAY.isoformat(),
    )
    rows = [Decimal(t["amount"]) for t in body["transactions"]]
    income = sum(a for a in rows if a > 0)
    expenses = -sum(a for a in rows if a < 0)
    assert income == Decimal(str(this_month["income"]))
    assert expenses == Decimal(str(this_month["expenses"]))

    # direction narrows to one side, totals still reconcile
    inflow = await _fetch(
        api_client,
        budget.id,
        scope="parent",
        posted_only=True,
        cash_flow_only=True,
        direction="inflow",
        start_date=month_start.isoformat(),
        end_date=TODAY.isoformat(),
    )
    assert Decimal(inflow["total_amount"]) == Decimal(str(this_month["income"]))
    outflow = await _fetch(
        api_client,
        budget.id,
        scope="parent",
        posted_only=True,
        cash_flow_only=True,
        direction="outflow",
        start_date=month_start.isoformat(),
        end_date=TODAY.isoformat(),
    )
    assert abs(Decimal(outflow["total_amount"])) == Decimal(str(this_month["expenses"]))


async def test_pending_excluded_iff_posted_only(api_client, db_session):
    _, budget, checking, _, groceries, _ = await _setup(api_client, db_session)
    await create_transaction(
        db_session, budget, checking, "-30.00", TODAY, category=groceries
    )
    pending = await create_transaction(
        db_session, budget, checking, "-75.00", TODAY, category=groceries, cleared="pending"
    )

    loose = await _fetch(api_client, budget.id)
    assert loose["total_count"] == 2
    assert Decimal(loose["total_amount"]) == Decimal("-105.00")

    posted = await _fetch(api_client, budget.id, posted_only=True)
    assert posted["total_count"] == 1
    assert Decimal(posted["total_amount"]) == Decimal("-30.00")
    assert str(pending.id) not in [t["id"] for t in posted["transactions"]]


async def test_account_filter_combinations(api_client, db_session):
    _, budget, checking, savings, groceries, gas = await _setup(api_client, db_session)
    payee = await create_payee(db_session, budget, "Cafe")
    await create_transaction(
        db_session, budget, checking, "-10.00", TODAY, category=groceries, payee=payee
    )
    await create_transaction(
        db_session, budget, checking, "-20.00", TODAY, category=gas
    )
    await create_transaction(
        db_session, budget, savings, "-40.00", TODAY, category=groceries, payee=payee
    )

    only_checking = await _fetch(api_client, budget.id, account_ids=str(checking.id))
    assert only_checking["total_count"] == 2
    assert Decimal(only_checking["total_amount"]) == Decimal("-30.00")

    checking_groceries = await _fetch(
        api_client,
        budget.id,
        account_ids=str(checking.id),
        category_ids=str(groceries.id),
    )
    assert checking_groceries["total_count"] == 1
    assert Decimal(checking_groceries["total_amount"]) == Decimal("-10.00")

    savings_cafe = await _fetch(
        api_client, budget.id, account_ids=str(savings.id), payee_ids=str(payee.id)
    )
    assert savings_cafe["total_count"] == 1
    assert Decimal(savings_cafe["total_amount"]) == Decimal("-40.00")

    both_accounts = await _fetch(
        api_client, budget.id, account_ids=f"{checking.id},{savings.id}"
    )
    assert both_accounts["total_count"] == 3


async def test_day_of_week_boundaries(api_client, db_session):
    _, budget, checking, _, groceries, _ = await _setup(api_client, db_session)
    monday = TODAY - timedelta(days=TODAY.weekday())
    sunday = monday - timedelta(days=1)
    await create_transaction(
        db_session, budget, checking, "-11.00", monday, category=groceries
    )
    await create_transaction(
        db_session, budget, checking, "-13.00", sunday, category=groceries
    )

    mondays = await _fetch(api_client, budget.id, day_of_week=0)
    assert mondays["total_count"] == 1
    assert mondays["transactions"][0]["date"] == monday.isoformat()

    sundays = await _fetch(api_client, budget.id, day_of_week=6)
    assert sundays["total_count"] == 1
    assert sundays["transactions"][0]["date"] == sunday.isoformat()

    resp = await api_client.get(
        f"/api/v1/{budget.id}/transactions", params={"day_of_week": 7}
    )
    assert resp.status_code == 422


async def test_direction_filter(api_client, db_session):
    _, budget, checking, _, groceries, _ = await _setup(api_client, db_session)
    await create_transaction(
        db_session, budget, checking, "-30.00", TODAY, category=groceries
    )
    await create_transaction(
        db_session, budget, checking, "25.00", TODAY, category=groceries
    )

    outflow = await _fetch(api_client, budget.id, direction="outflow")
    assert [Decimal(t["amount"]) for t in outflow["transactions"]] == [Decimal("-30.00")]
    inflow = await _fetch(api_client, budget.id, direction="inflow")
    assert [Decimal(t["amount"]) for t in inflow["transactions"]] == [Decimal("25.00")]


async def test_pagination_keeps_totals_stable(api_client, db_session):
    _, budget, checking, _, groceries, _ = await _setup(api_client, db_session)
    for i in range(5):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-10.00",
            TODAY - timedelta(days=i),
            category=groceries,
        )

    seen: list[str] = []
    for offset in (0, 2, 4):
        page = await _fetch(api_client, budget.id, limit=2, offset=offset)
        assert page["total_count"] == 5
        assert Decimal(page["total_amount"]) == Decimal("-50.00")
        seen += [t["id"] for t in page["transactions"]]
    assert len(seen) == 5
    assert len(set(seen)) == 5  # no row repeated or dropped across pages


async def test_deleted_never_appears(api_client, db_session):
    _, budget, checking, _, groceries, _ = await _setup(api_client, db_session)
    await create_transaction(
        db_session, budget, checking, "-30.00", TODAY, category=groceries
    )
    await create_transaction(
        db_session, budget, checking, "-99.00", TODAY, category=groceries, is_deleted=True
    )

    for scope in ("parent", "leaf"):
        body = await _fetch(api_client, budget.id, scope=scope)
        assert body["total_count"] == 1
        assert Decimal(body["total_amount"]) == Decimal("-30.00")


async def test_foreign_budget_404(api_client, db_session):
    stranger = await create_user(db_session)
    foreign_budget = await create_budget(db_session, stranger)
    resp = await api_client.get(f"/api/v1/{foreign_budget.id}/transactions")
    assert resp.status_code == 404
    assert resp.json()["detail"] != "Not Found"  # ownership 404, not a missing route


async def _setup_search(api_client, db_session):
    """Three transactions: a Whole Foods purchase, a memo mention, a decoy."""
    services, budget, checking, _, groceries, gas = await _setup(api_client, db_session)
    whole_foods = await create_payee(db_session, budget, "Whole Foods")
    shell = await create_payee(db_session, budget, "Shell")
    await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, category=groceries, payee=whole_foods
    )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-20.00",
        TODAY,
        category=gas,
        payee=shell,
        memo="snacks from whole foods run",
    )
    await create_transaction(
        db_session, budget, checking, "-10.00", TODAY, category=gas, payee=shell, memo="fuel"
    )
    return budget


async def test_search_matches_payee_name(api_client, db_session):
    budget = await _setup_search(api_client, db_session)
    body = await _fetch(api_client, budget.id, search="Whole Foods")
    # Payee match (-50) plus memo match (-20)
    assert body["total_count"] == 2
    assert Decimal(body["total_amount"]) == Decimal("-70.00")


async def test_search_matches_memo_only(api_client, db_session):
    budget = await _setup_search(api_client, db_session)
    body = await _fetch(api_client, budget.id, search="fuel")
    assert body["total_count"] == 1
    assert Decimal(body["total_amount"]) == Decimal("-10.00")


async def test_search_case_insensitive(api_client, db_session):
    budget = await _setup_search(api_client, db_session)
    body = await _fetch(api_client, budget.id, search="wHoLe fOoDs")
    assert body["total_count"] == 2


async def test_search_composes_with_filters(api_client, db_session):
    budget = await _setup_search(api_client, db_session)
    # "whole foods" matches two rows; outflow direction keeps both, but a
    # payee-name search string composes with structured filters via AND
    body = await _fetch(api_client, budget.id, search="whole foods", direction="outflow")
    assert body["total_count"] == 2
    body = await _fetch(api_client, budget.id, search="whole foods", direction="inflow")
    assert body["total_count"] == 0


async def test_search_no_match_returns_empty(api_client, db_session):
    budget = await _setup_search(api_client, db_session)
    body = await _fetch(api_client, budget.id, search="zebra")
    assert body["total_count"] == 0
    assert body["transactions"] == []
