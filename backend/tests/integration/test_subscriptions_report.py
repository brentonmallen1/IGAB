"""Subscriptions report: posted leaf rows filed to subscription-tagged
categories, grouped by category with the services (payees) inside. The tag
moved from payees to categories (repositories/tag_repo.py
CATEGORY_ONLY_SYSTEM_KEYS); a payee the household never tagged used to vanish
from here.

What each service costs is `domain.subscriptions.service_cost`, pinned case by
case in tests/unit/test_domain_subscriptions.py. What this file pins is the
wiring: which rows reach it, that the range picker moves only the chart, that
the table adds up, and what the summary counts.

The reader's day is fixed, so the year Annual reads is fixed too: the 12
complete months 1 Sep 2025 – 31 Aug 2026.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.dates import add_months
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_basics import subscriptions_report

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
TODAY = date(2026, 9, 26)
THIS_MONTH = date(2026, 9, 1)


def months_ago(n: int, day: int = 1) -> date:
    return add_months(THIS_MONTH, -n).replace(day=day)


async def _setup(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    await seed_system_tags(db_session, budget.id)
    tag_repo = TagRepository(db_session)
    group = await create_category_group(db_session, budget, "Bills")
    streaming = await _tagged(db_session, budget, tag_repo, group, "Streaming")
    # The budget's history reaches past every window, so no window is clamped.
    await create_transaction(db_session, budget, checking, "-10.00", months_ago(30))
    return budget, checking, tag_repo, group, streaming


async def _tagged(db_session, budget, tag_repo, group, name):
    sub_tag = await tag_repo.get_system_tag(budget.id, "subscription")
    category = await create_category(db_session, budget, group, name)
    await tag_repo.set_category_tags(category.id, [sub_tag.id])
    return category


async def _monthly(db_session, budget, account, amount, payee, category, ages, day=5):
    for k in ages:
        await create_transaction(
            db_session, budget, account, amount, months_ago(k, day), payee=payee, category=category
        )


async def report(db_session, budget, months=12):
    return await subscriptions_report(db_session, budget.id, months=months, today=TODAY)


async def test_posted_leaf_rows_count_and_refunds_net(db_session):
    budget, checking, _, _, streaming = await _setup(db_session)
    stream = await create_payee(db_session, budget, "Northstar Stream")
    # Fourteen months ago through this month: a mature monthly service.
    await _monthly(db_session, budget, checking, "-15.00", stream, streaming, range(14, -1, -1))
    # None of these may count as a charge: pending, deleted, and a split
    # parent (its child below is the leaf).
    for kwargs in ({"cleared": "pending"}, {"is_deleted": True}):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-99.00",
            months_ago(2, 9),
            payee=stream,
            category=streaming,
            **kwargs,
        )
    parent = await create_transaction(
        db_session,
        budget,
        checking,
        "-50.00",
        months_ago(3, 9),
        payee=stream,
        category=streaming,
        is_split=True,
    )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-5.00",
        months_ago(3, 9),
        payee=stream,
        category=streaming,
        parent_transaction_id=parent.id,
    )
    # A refund inside the year nets. It was filtered out (`amount < 0`), so a
    # refunded month still read as a month paid.
    await create_transaction(
        db_session, budget, checking, "15.00", months_ago(2, 20), payee=stream, category=streaming
    )
    # Untagged: never a subscription, whatever its cadence.
    rent = await create_payee(db_session, budget, "Harborstone Rentals")
    await create_transaction(db_session, budget, checking, "-1000.00", months_ago(1), payee=rent)

    data = await report(db_session, budget)

    (line,) = data["subscriptions"]
    assert line["category_name"] == "Streaming"
    (service,) = line["services"]
    assert service["payee_name"] == "Northstar Stream"
    # 12 × 15 + the 5 split leg − the 15 refund.
    assert service["basis"] == "observed"
    assert service["charges_in_year"] == 13
    assert service["refunded_in_year"] == D("15.00")
    assert service["annual"] == D("170.00")
    assert service["monthly"] == D("14.17")
    assert service["last_charge_date"] == months_ago(0, 5)

    # The chart is net too: months_ago(2) is 15 − 15, months_ago(3) 15 + 5.
    amounts = dict(zip(data["months"], line["monthly_amounts"], strict=True))
    assert amounts[months_ago(2)] == D("0")
    assert amounts[months_ago(3)] == D("20")
    assert amounts[months_ago(1)] == D("15")
    assert data["monthly_totals"] == line["monthly_amounts"]


async def test_the_range_picker_moves_the_chart_not_the_cost(db_session):
    """Annual used to swing threefold with the picker: each service divided
    its charges by the months since its first charge INSIDE the range, so an
    annual bill charged in June read $20/mo on three months and $5/mo on
    twelve — and $240 a year on the first, four times the bill."""
    budget, checking, _, _, streaming = await _setup(db_session)
    yearly = await create_payee(db_session, budget, "Cascade Cloud")
    for k in (27, 15, 3):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-60.00",
            months_ago(k, 10),
            payee=yearly,
            category=streaming,
        )

    by_range = {m: await report(db_session, budget, months=m) for m in (3, 6, 12, 24)}

    for data in by_range.values():
        assert data["summary"]["total_annual"] == D("60.00")
        assert data["summary"]["total_monthly"] == D("5.00")
        assert (data["year_start"], data["year_end"]) == (date(2025, 9, 1), date(2026, 8, 31))
    assert [len(d["months"]) for d in by_range.values()] == [3, 6, 12, 24]


async def test_the_table_adds_up_and_monthly_is_annual_over_twelve(db_session):
    budget, checking, tag_repo, group, streaming = await _setup(db_session)
    software = await _tagged(db_session, budget, tag_repo, group, "Software")
    stream = await create_payee(db_session, budget, "Northstar Stream")
    newcomer = await create_payee(db_session, budget, "Harbor Play")
    editor = await create_payee(db_session, budget, "Pixelworks")
    # Established; young (first charged two months ago); established.
    await _monthly(db_session, budget, checking, "-15.00", stream, streaming, range(14, -1, -1))
    await _monthly(db_session, budget, checking, "-10.00", newcomer, streaming, (2, 1, 0))
    await _monthly(db_session, budget, checking, "-40.00", editor, software, range(14, -1, -1))

    data = await report(db_session, budget)

    lines = {s["category_name"]: s for s in data["subscriptions"]}
    services = {s["payee_name"]: s for s in lines["Streaming"]["services"]}
    assert services["Northstar Stream"]["annual"] == D("180.00")
    # Younger than the year: its cadence projected, not its two months summed.
    assert services["Harbor Play"]["basis"] == "new"
    assert services["Harbor Play"]["annual"] == D("120.00")

    for line in data["subscriptions"]:
        assert line["annual"] == sum(s["annual"] for s in line["services"])
        assert line["monthly"] == (line["annual"] / 12).quantize(D("0.01"))
    assert lines["Streaming"]["annual"] == D("300.00")
    assert lines["Software"]["annual"] == D("480.00")
    # Costliest first.
    assert [s["category_name"] for s in data["subscriptions"]] == ["Software", "Streaming"]

    summary = data["summary"]
    assert summary["total_annual"] == D("780.00")
    assert summary["total_monthly"] == D("65.00")
    assert summary["projected_services"] == 1


async def test_a_stopped_service_is_listed_and_counts_in_nothing(db_session):
    """Cancelled services stayed in Monthly, Annual and Active for the rest of
    the year. A service quiet for 1.5 cycles is stopped (`has_stopped`, the
    rule the cash projection reads too)."""
    budget, checking, tag_repo, group, streaming = await _setup(db_session)
    fitness = await _tagged(db_session, budget, tag_repo, group, "Fitness")
    news = await _tagged(db_session, budget, tag_repo, group, "News")  # never charged
    stream = await create_payee(db_session, budget, "Northstar Stream")
    gym = await create_payee(db_session, budget, "Harborstone Gym")
    await _monthly(db_session, budget, checking, "-15.00", stream, streaming, range(14, -1, -1))
    # Last charged four months ago.
    await _monthly(db_session, budget, checking, "-30.00", gym, fitness, range(14, 3, -1))

    data = await report(db_session, budget)

    lines = {s["category_name"]: s for s in data["subscriptions"]}
    (gym_row,) = lines["Fitness"]["services"]
    assert gym_row["basis"] == "stopped"
    assert gym_row["annual"] == D("0.00")
    assert gym_row["last_charge_date"] == months_ago(4, 5)
    # Its past charges are still drawn on the chart.
    assert sum(lines["Fitness"]["monthly_amounts"]) > 0

    summary = data["summary"]
    assert summary["total_annual"] == D("180.00")
    assert summary["stopped_services"] == 1
    # "Active 2" counted categories charged in the range, stopped ones
    # included. It is now "1 of 3 tagged categories charged".
    assert summary["charged_categories"] == 1
    assert summary["tagged_categories"] == 3
    assert "News" not in lines
    assert news  # tagged, uncharged: counted in the 3, drawn nowhere


async def test_a_service_stopped_before_the_year_is_history(db_session):
    budget, checking, _, _, streaming = await _setup(db_session)
    old = await create_payee(db_session, budget, "Retired Stream")
    await _monthly(db_session, budget, checking, "-9.00", old, streaming, range(26, 16, -1))

    data = await report(db_session, budget)

    assert data["subscriptions"] == []
    assert data["summary"]["stopped_services"] == 0


async def test_new_this_month_counts_services_first_charged_this_month(db_session):
    budget, checking, _, _, streaming = await _setup(db_session)
    stream = await create_payee(db_session, budget, "Northstar Stream")
    fresh = await create_payee(db_session, budget, "Pixelworks")
    await _monthly(db_session, budget, checking, "-15.00", stream, streaming, range(14, -1, -1))
    await create_transaction(
        db_session, budget, checking, "-9.00", date(2026, 9, 12), payee=fresh, category=streaming
    )

    data = await report(db_session, budget)

    services = {s["payee_name"]: s for s in data["subscriptions"][0]["services"]}
    assert services["Pixelworks"]["basis"] == "new"
    assert services["Pixelworks"]["cadence_assumed"]
    # One charge: monthly assumed, so twelve a year — and it says so.
    assert services["Pixelworks"]["annual"] == D("108.00")
    assert data["summary"]["new_this_month"] == 1
    # The running month is not a chart column.
    assert THIS_MONTH not in data["months"]


async def test_a_payee_less_charge_is_its_own_service(db_session):
    budget, checking, _, _, streaming = await _setup(db_session)
    await _monthly(db_session, budget, checking, "-6.00", None, streaming, range(14, -1, -1))

    data = await report(db_session, budget)

    (service,) = data["subscriptions"][0]["services"]
    assert service["payee_id"] is None
    assert service["payee_name"] == "No payee"
    assert service["annual"] == D("72.00")


@pytest.mark.parametrize("seed_tags", [False, True])
async def test_nothing_tagged_is_empty(db_session, seed_tags):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    if seed_tags:
        await seed_system_tags(db_session, budget.id)

    data = await report(db_session, budget)

    assert data["subscriptions"] == []
    assert data["months"] == []
    assert data["monthly_totals"] == []
    assert data["summary"] == {
        "total_monthly": D("0"),
        "total_annual": D("0"),
        "charged_categories": 0,
        "tagged_categories": 0,
        "new_this_month": 0,
        "projected_services": 0,
        "stopped_services": 0,
    }
