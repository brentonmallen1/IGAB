"""Every leaf-row report that groups by payee groups by the payee of record.

A split's legs usually carry no payee — the app's split editor names the shop
(or the employer) on the parent — so grouping leaf rows by the raw
`Transaction.payee_id` filed every split under "No payee", beside the same
payee's unsplit rows. Payee Analysis, the Pareto and the Sankey's spent mode
already read `txn_filters.PAYEE_OF_RECORD`; Subscriptions, Income by Source,
the savings-rate dialog's income sources, the cash projection's subscription
arm and the Sankey's payee bands did not. Each test is one of those, named for
it. Amounts are invented and round.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.domain.dates import add_months, month_end
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_basics import income_by_source, savings_contributors, subscriptions_report
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
)

D = Decimal
TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)
LAST_MONTH = add_months(THIS_MONTH, -1)


async def _world(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    return budget, checking, group


async def _split(db_session, budget, account, when, payee, legs):
    """A split as the app's editor writes it: the payee on the parent only."""
    total = sum((D(a) for a, _ in legs), D("0"))
    parent = await create_transaction(
        db_session, budget, account, total, when, payee=payee, is_split=True
    )
    for amount, category in legs:
        await create_transaction(
            db_session,
            budget,
            account,
            amount,
            when,
            category=category,
            parent_transaction_id=parent.id,
        )
    return parent


async def _subscription_category(db_session, budget, group, name):
    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    sub = await tags.get_system_tag(budget.id, "subscription")
    category = await create_category(db_session, budget, group, name)
    await tags.set_category_tags(category.id, [sub.id])
    return category


async def _split_paycheck(db_session):
    """1,000 of pay from Northwind Payserv, 300 of it split off to a fee."""
    budget, checking, group = await _world(db_session)
    system = await create_category_group(db_session, budget, "Income", is_system=True)
    ready = await create_category(db_session, budget, system, "Ready to Assign")
    fees = await create_category(db_session, budget, group, "Bank Fees")
    employer = await create_payee(db_session, budget, "Northwind Payserv")
    when = LAST_MONTH + timedelta(days=4)
    await _split(
        db_session, budget, checking, when, employer, [("1000.00", ready), ("-300.00", fees)]
    )
    return budget, employer, when


async def test_income_by_source_names_a_split_paycheck_by_its_employer(db_session):
    budget, employer, _ = await _split_paycheck(db_session)
    report = await income_by_source(db_session, budget.id, months=1)
    assert [(s["payee_id"], s["payee_name"], s["total"]) for s in report["sources"]] == [
        (employer.id, "Northwind Payserv", D("1000.00"))
    ]


async def test_the_savings_rate_dialog_names_it_the_same_way(db_session):
    budget, employer, when = await _split_paycheck(db_session)
    report = await savings_contributors(
        db_session, budget.id, LAST_MONTH, month_end(LAST_MONTH), today=TODAY
    )
    assert [(s["payee_id"], s["payee_name"]) for s in report["income_sources"]] == [
        (employer.id, "Northwind Payserv")
    ]


async def test_subscriptions_file_a_split_charge_under_its_service(db_session):
    """A 30 streaming bundle split across two tagged envelopes, monthly for
    fifteen months: one service in each, not "No payee"."""
    budget, checking, group = await _world(db_session)
    video = await _subscription_category(db_session, budget, group, "Video")
    music = await _subscription_category(db_session, budget, group, "Music")
    service = await create_payee(db_session, budget, "Streamwell")
    # Billed on the 1st through this month, so it is live whatever today is.
    for k in range(14, -1, -1):
        await _split(
            db_session,
            budget,
            checking,
            add_months(THIS_MONTH, -k),
            service,
            [("-20.00", video), ("-10.00", music)],
        )

    report = await subscriptions_report(db_session, budget.id, months=12, today=TODAY)

    by_category = {s["category_name"]: s["services"] for s in report["subscriptions"]}
    for name, annual in (("Video", D("240.00")), ("Music", D("120.00"))):
        (svc,) = by_category[name]
        assert (svc["payee_id"], svc["payee_name"], svc["annual"]) == (
            str(service.id),
            "Streamwell",
            annual,
        )


async def test_the_projection_projects_a_split_subscription_charge(db_session):
    """The projection's subscription arm inner-joined the raw payee, so a
    split charge's legs matched no payee and the service was never projected."""
    budget, checking, group = await _world(db_session)
    video = await _subscription_category(db_session, budget, group, "Video")
    service = await create_payee(db_session, budget, "Streamwell")
    last_charge = TODAY.replace(day=14 if TODAY.day == 15 else 15)
    if last_charge >= TODAY:
        last_charge = add_months(last_charge, -1)
    for charged in (add_months(last_charge, -1), last_charge):
        await _split(db_session, budget, checking, charged, service, [("-15.00", video)])

    data = await ReportService(db_session).cash_projection(
        budget.id, horizon_days=(add_months(last_charge, 1) - TODAY).days, today=TODAY
    )

    assert [(e["date"], e["amount"]) for e in data["events"] if e["source"] == "subscription"] == [
        (add_months(last_charge, 1), D("-15.00"))
    ]


async def test_the_sankey_serves_a_payee_bands_id(db_session):
    """The page matched a band's name against every payee: two payees sharing
    a name opened the first one's rows. The band carries its payee of record's
    id now, a split's included; "Other payees" and payee-less rows carry none."""
    budget, checking, group = await _world(db_session)
    groceries = await create_category(db_session, budget, group, "Groceries")
    market = await create_payee(db_session, budget, "Cascade Market")
    when = LAST_MONTH + timedelta(days=4)
    await _split(db_session, budget, checking, when, market, [("-60.00", groceries)])
    await create_transaction(db_session, budget, checking, "-15.00", when, category=groceries)

    data = await ReportService(db_session).cash_flow_sankey(
        budget.id, LAST_MONTH, month_end(LAST_MONTH), mode="spent"
    )

    (bands,) = data["category_payees"].values()
    assert [(b["name"], b["total"], b["payee_id"]) for b in bands] == [
        ("Cascade Market", D("60.00"), str(market.id)),
        ("Unknown", D("15.00"), None),
    ]
