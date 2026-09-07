"""Subscriptions report: posted leaf outflows filed to subscription-tagged
categories, grouped by payee. The tag moved from payees to categories
(repositories/tag_repo.py CATEGORY_ONLY_SYSTEM_KEYS); a payee the household
never tagged used to vanish from here.

Pins the money semantics decided in the reports audit:
- `avg_monthly` is the TRUE monthly burden: total ÷ months from the first
  charged month through the end of the window (a quarterly $30 sub reads as
  $10/mo, not $30/mo).
- `avg_per_charge` is the typical charge: total ÷ charge count.
- Refunds (inflows) are ignored — the report tracks subscription cost, and
  the `amount < 0` filter pins that choice.
- Monthly buckets are exact Decimals: no float representation artifacts.
"""

from datetime import date
from decimal import Decimal

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

TODAY = date.today()


def months_ago(n: int) -> date:
    """First day of the month `n` months before the current month."""
    year, month = TODAY.year, TODAY.month - n
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


async def _setup(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    await seed_system_tags(db_session, budget.id)
    tag_repo = TagRepository(db_session)
    sub_tag = await tag_repo.get_system_tag(budget.id, "subscription")
    group = await create_category_group(db_session, budget, "Bills")
    streaming = await create_category(db_session, budget, group, "Streaming")
    await tag_repo.set_category_tags(streaming.id, [sub_tag.id])
    return budget, checking, tag_repo, streaming


async def _tag_payee(db_session, budget, tag_repo, streaming, name):
    """A payee whose charges are filed to the subscription category. Kept
    under its old name so the cases below read as they did: the payee is
    still the line the report draws, the category is what qualifies it."""
    return await create_payee(db_session, budget, name)


async def test_monthly_subscription_counts_posted_leaf_outflows_only(db_session):
    budget, checking, tag_repo, sub_cat = await _setup(db_session)
    netflix = await _tag_payee(db_session, budget, tag_repo, sub_cat, "Netflix")

    for k in (2, 1, 0):
        await create_transaction(
            db_session, budget, checking, "-15.99", months_ago(k), payee=netflix, category=sub_cat
        )
    # None of these may count: pending, deleted, refund (inflow)
    await create_transaction(
        db_session,
        budget,
        checking,
        "-15.99",
        months_ago(0),
        payee=netflix,
        category=sub_cat,
        cleared="pending",
    )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-15.99",
        months_ago(0),
        payee=netflix,
        category=sub_cat,
        is_deleted=True,
    )
    await create_transaction(
        db_session, budget, checking, "15.99", months_ago(0), payee=netflix, category=sub_cat
    )
    # Untagged payee: never a subscription, no matter the cadence
    rent = await create_payee(db_session, budget, "Rent")
    await create_transaction(db_session, budget, checking, "-1000.00", months_ago(1), payee=rent)

    data = await subscriptions_report(db_session, budget.id, months=12)

    assert len(data["subscriptions"]) == 1
    sub = data["subscriptions"][0]
    # The tagged CATEGORY is the line; the payee is the detail inside it.
    assert sub["category_name"] == "Streaming"
    assert [p["payee_name"] for p in sub["payees"]] == ["Netflix"]
    assert sub["payees"][0]["total"] == Decimal("47.97")
    assert sub["total"] == Decimal("47.97")
    assert sub["transaction_count"] == 3
    assert sub["last_charge_date"] == months_ago(0)
    assert sub["avg_per_charge"] == Decimal("15.99")
    # First charge 2 months ago -> active span of 3 months
    assert sub["avg_monthly"] == Decimal("15.99")

    months = data["months"]
    assert len(months) == 13
    amounts = dict(zip(months, sub["monthly_amounts"]))
    assert amounts[months_ago(2)] == Decimal("15.99")
    assert amounts[months_ago(1)] == Decimal("15.99")
    assert amounts[months_ago(0)] == Decimal("15.99")
    assert amounts[months_ago(5)] == Decimal("0")

    assert data["summary"]["total_monthly"] == Decimal("15.99")
    assert data["summary"]["total_annual"] == Decimal("191.88")
    assert data["summary"]["active_count"] == 1


async def test_quarterly_subscription_normalizes_to_true_monthly_cost(db_session):
    budget, checking, tag_repo, sub_cat = await _setup(db_session)
    gym = await _tag_payee(db_session, budget, tag_repo, sub_cat, "Quarterly Gym")

    # 4 quarterly charges; first charge 11 months ago -> 12-month active span
    for k in (11, 8, 5, 2):
        await create_transaction(
            db_session, budget, checking, "-30.00", months_ago(k), payee=gym, category=sub_cat
        )

    data = await subscriptions_report(db_session, budget.id, months=12)

    sub = data["subscriptions"][0]
    assert sub["total"] == Decimal("120.00")
    assert sub["avg_per_charge"] == Decimal("30.00")
    # $120 over a 12-month span = $10/mo — NOT the $30 per-charge figure
    assert sub["avg_monthly"] == Decimal("10.00")
    assert data["summary"]["total_monthly"] == Decimal("10.00")
    assert data["summary"]["total_annual"] == Decimal("120.00")


async def test_monthly_buckets_are_exact_decimals(db_session):
    budget, checking, tag_repo, sub_cat = await _setup(db_session)
    micro = await _tag_payee(db_session, budget, tag_repo, sub_cat, "Micro")

    # 0.1 + 0.2 is the canonical float-artifact trap
    await create_transaction(
        db_session, budget, checking, "-0.10", months_ago(0), payee=micro, category=sub_cat
    )
    await create_transaction(
        db_session, budget, checking, "-0.20", months_ago(0), payee=micro, category=sub_cat
    )

    data = await subscriptions_report(db_session, budget.id, months=12)

    sub = data["subscriptions"][0]
    assert sub["monthly_amounts"][-1] == Decimal("0.30")
    assert str(sub["monthly_amounts"][-1]) != "0.30000000000000004"
    assert sub["total"] == Decimal("0.30")
    assert sub["avg_per_charge"] == Decimal("0.15")


async def test_split_child_charge_counts_once_at_child_amount(db_session):
    budget, checking, tag_repo, sub_cat = await _setup(db_session)
    spotify = await _tag_payee(db_session, budget, tag_repo, sub_cat, "Spotify")

    parent = await create_transaction(
        db_session,
        budget,
        checking,
        "-50.00",
        months_ago(1),
        payee=spotify,
        category=sub_cat,
        is_split=True,
    )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-9.99",
        months_ago(1),
        payee=spotify,
        category=sub_cat,
        parent_transaction_id=parent.id,
    )

    data = await subscriptions_report(db_session, budget.id, months=12)

    sub = data["subscriptions"][0]
    assert sub["total"] == Decimal("9.99")
    assert sub["transaction_count"] == 1


async def test_no_subscription_tag_or_no_tagged_payees_is_empty(db_session):
    user = await create_user(db_session)
    untagged_budget = await create_budget(db_session, user)
    data = await subscriptions_report(db_session, untagged_budget.id, months=12)
    assert data == {
        "subscriptions": [],
        "summary": {
            "total_monthly": Decimal("0"),
            "total_annual": Decimal("0"),
            "active_count": 0,
        },
        "months": [],
    }

    # Tag exists but nothing is tagged with it
    seeded_budget = await create_budget(db_session, user)
    await seed_system_tags(db_session, seeded_budget.id)
    data = await subscriptions_report(db_session, seeded_budget.id, months=12)
    assert data["subscriptions"] == []
    assert data["summary"]["active_count"] == 0


async def test_several_tagged_categories_each_get_a_line(db_session):
    """Tagging three categories used to produce a list of PAYEES with no sign
    of which envelope any of them belonged to — the tag was on categories and
    the report never mentioned one. Now each tagged category is a line, and
    the services inside it are the detail."""
    budget, checking, tag_repo, streaming = await _setup(db_session)
    sub_tag = await tag_repo.get_system_tag(budget.id, "subscription")
    group = await create_category_group(db_session, budget, "Digital")
    software = await create_category(db_session, budget, group, "Software")
    await tag_repo.set_category_tags(software.id, [sub_tag.id])

    netflix = await create_payee(db_session, budget, "Netflix")
    hulu = await create_payee(db_session, budget, "Hulu")
    editor = await create_payee(db_session, budget, "Pixelworks")
    for k in (1, 0):
        await create_transaction(
            db_session, budget, checking, "-20.00", months_ago(k), payee=netflix, category=streaming
        )
        await create_transaction(
            db_session, budget, checking, "-10.00", months_ago(k), payee=hulu, category=streaming
        )
        await create_transaction(
            db_session, budget, checking, "-45.00", months_ago(k), payee=editor, category=software
        )

    data = await subscriptions_report(db_session, budget.id, months=12)

    lines = {s["category_name"]: s for s in data["subscriptions"]}
    assert set(lines) == {"Streaming", "Software"}
    # Biggest envelope first: Software at 90 over Streaming at 60.
    assert [s["category_name"] for s in data["subscriptions"]] == ["Software", "Streaming"]

    assert lines["Streaming"]["total"] == Decimal("60.00")
    assert lines["Streaming"]["group_name"] == "Bills"
    # Payees inside, biggest first — "which service grew" is the next question.
    assert [p["payee_name"] for p in lines["Streaming"]["payees"]] == ["Netflix", "Hulu"]
    assert lines["Streaming"]["payees"][0]["total"] == Decimal("40.00")

    assert lines["Software"]["total"] == Decimal("90.00")
    assert [p["payee_name"] for p in lines["Software"]["payees"]] == ["Pixelworks"]

    # A category's own figures are the sum of its payees', not a separate walk.
    for line in data["subscriptions"]:
        assert line["total"] == sum(p["total"] for p in line["payees"])
        assert line["transaction_count"] == sum(p["transaction_count"] for p in line["payees"])

    assert data["summary"]["active_count"] == 2
