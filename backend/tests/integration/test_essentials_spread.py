"""Sinking-fund bills spread over twelve months, on every essentials surface.

One household throughout: $2,000 of Essential rent in each of the last three
months, and a $2,400 yearly home-insurance premium filed last month to a
category tagged Essential and Long-term expense. As paid that is
(6,000 + 2,400) / 3 = $2,800 a month; spread it is 2,000 + 2,400 / 12 =
$2,200. Three months of essentials is $6,600 spread and $8,400 as paid.

Everything is read through the API, the way the surfaces read it.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.domain.dates import add_months, month_start
from igab.guide.repo import GuideRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_settings import SPREAD_SINKING_FUNDS_KEY

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
)

TODAY = date.today()
LAST_MONTH = add_months(month_start(TODAY), -1)
SPREAD = Decimal("2200.00")
AS_PAID = Decimal("2800.00")


def money(value) -> Decimal:
    return Decimal(str(value))


def figures(served: dict) -> tuple[Decimal, Decimal, bool, Decimal]:
    return (
        money(served["as_paid"]),
        money(served["spread"]),
        served["spread_on"],
        money(served["monthly"]),
    )


async def _household(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    bills = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, bills, "Rent")
    insurance = await create_category(db_session, budget, bills, "Home Insurance")
    coffee = await create_category(db_session, budget, bills, "Coffee")
    goals = await create_category_group(db_session, budget, "Goals")
    fund = await create_category(db_session, budget, goals, "Emergency Fund")

    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    by_key = {t.system_key: t for t in await tags.list_for_budget(budget.id)}
    await tags.set_category_tags(rent.id, [by_key["essential"].id])
    await tags.set_category_tags(
        insurance.id, [by_key["essential"].id, by_key["long_term_expense"].id]
    )
    await tags.set_category_tags(fund.id, [by_key["savings"].id])

    # History from over a year back, so every coverage point averages three
    # real months.
    await create_transaction(
        db_session, budget, checking, "-4.00", add_months(LAST_MONTH, -13), category=coffee
    )
    for days in (5, 35, 65):
        await create_transaction(
            db_session, budget, checking, "-2000.00", TODAY - timedelta(days=days), category=rent
        )
    # Day 3 of last month is always 29–61 days back: inside the 90-day window.
    await create_transaction(
        db_session, budget, checking, "-2400.00", LAST_MONTH + timedelta(days=2), category=insurance
    )
    await create_budget_assignment(db_session, budget, fund, LAST_MONTH, "1000.00")
    await db_session.commit()
    return budget


async def _get(api_client, path: str, **params) -> dict:
    r = await api_client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def _dashboard_monthly(api_client, base: str) -> Decimal:
    return money((await _get(api_client, f"{base}/reports/dashboard"))["essentials"]["monthly"])


async def _set_spread(api_client, budget, on: bool) -> dict:
    r = await api_client.put(
        f"/api/v1/{budget.id}/reports/settings", json={"spread_sinking_funds": on}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _surfaces(api_client, budget) -> dict[str, dict]:
    """Every surface's served figures, keyed by surface."""
    base = f"/api/v1/{budget.id}"
    dashboard = await _get(api_client, f"{base}/reports/dashboard")
    essentials = await _get(api_client, f"{base}/reports/essentials")
    coverage = await _get(api_client, f"{base}/reports/emergency-fund")
    signals = await _get(api_client, f"{base}/guide/signals")
    signal = next(c for c in signals["concepts"] if c["key"] == "essential_expenses")
    sizer = await api_client.post(
        f"{base}/guide/scenarios/emergency-fund",
        json={"months": 3, "monthly_contribution": "0"},
    )
    assert sizer.status_code == 200, sizer.text
    return {
        "dashboard": dashboard,
        "essentials": essentials,
        "coverage": coverage,
        "signal": signal,
        "sizer": sizer.json(),
        "signals": signals,
    }


def _assert_reads(s: dict[str, dict], monthly: Decimal, *, spread_on: bool) -> None:
    both = (AS_PAID, SPREAD, spread_on, monthly)
    for surface in ("dashboard", "essentials", "coverage", "signal", "sizer"):
        assert figures(s[surface]["essentials"]) == both, surface

    # Everything built on `.monthly` follows it: the signal's value, the
    # reserve, the targets, the Guide's emergency-fund target and starter.
    assert money(s["signal"]["value"]) == monthly

    three = monthly * 3
    reserve = {r["months"]: money(r["amount"]) for r in s["essentials"]["reserve"]}
    assert reserve[3] == three
    assert money(s["coverage"]["target_low"]) == three
    assert money(s["sizer"]["target"]) == three
    fund = next(c for c in s["signals"]["concepts"] if c["key"] == "emergency_fund")
    assert money(fund["target"]) == three
    assert money(fund["starter_target"]) == monthly


async def test_every_surface_serves_both_figures(db_session, api_client):
    budget = await _household(db_session, api_client)
    _assert_reads(await _surfaces(api_client, budget), SPREAD, spread_on=True)


async def test_off_uses_as_paid_everywhere(db_session, api_client):
    budget = await _household(db_session, api_client)
    assert await _set_spread(api_client, budget, False) == {"spread_sinking_funds": False}
    _assert_reads(await _surfaces(api_client, budget), AS_PAID, spread_on=False)


async def test_charts_stay_as_paid(db_session, api_client):
    """The Essentials chart draws what was spent: last month carries the whole
    premium, and says how much of it was a sinking fund."""
    budget = await _household(db_session, api_client)
    report = await _get(api_client, f"/api/v1/{budget.id}/reports/essentials")
    last = next(m for m in report["monthly_series"] if m["month"] == LAST_MONTH.isoformat())
    assert money(last["sinking_total"]) == Decimal("2400.00")
    assert sum(money(m["sinking_total"]) for m in report["monthly_series"]) == Decimal("2400.00")
    # Every dollar as it was paid: the premium whole, plus the rent that fell
    # in complete months.
    rent_paid = sum(
        Decimal("2000.00")
        for days in (5, 35, 65)
        if TODAY - timedelta(days=days) < month_start(TODAY)
    )
    assert sum(money(m["total"]) for m in report["monthly_series"]) == rent_paid + Decimal(
        "2400.00"
    )


async def test_the_coverage_point_spreads_like_the_headline(db_session, api_client):
    """Last month's point: spread, the premium is 200 of it; as paid, it is a
    third of 2,400 = 800 of the trailing three-month average. The rest is the
    same months either way, so the two points differ by exactly 600."""
    budget = await _household(db_session, api_client)
    path = f"/api/v1/{budget.id}/reports/emergency-fund"

    on = (await _get(api_client, path, months=1))["series"][-1]
    await _set_spread(api_client, budget, False)
    off = (await _get(api_client, path, months=1))["series"][-1]

    assert on["month"] == off["month"] == LAST_MONTH.isoformat()
    assert money(off["essentials"]) - money(on["essentials"]) == Decimal("600.00")


async def test_a_category_that_is_also_savings_is_not_spread(db_session, api_client):
    """Savings and Long-term expense on one category: no silent precedence. A
    kept-here savings envelope's spending is essential spending, but it is not
    a sinking fund, so it counts as paid in both figures."""
    budget = await _household(db_session, api_client)
    tags = TagRepository(db_session)
    by_key = {t.system_key: t for t in await tags.list_for_budget(budget.id)}
    goals = await create_category_group(db_session, budget, "Set aside")
    both = await create_category(db_session, budget, goals, "Roof")
    both.savings_mode = "kept_here"
    await tags.set_category_tags(
        both.id,
        [by_key["essential"].id, by_key["long_term_expense"].id, by_key["savings"].id],
    )
    checking = await create_account(db_session, budget, "Second Checking")
    await create_transaction(
        db_session, budget, checking, "-1200.00", TODAY - timedelta(days=8), category=both
    )
    await db_session.commit()

    served = (await _get(api_client, f"/api/v1/{budget.id}/reports/essentials"))["essentials"]
    assert (money(served["as_paid"]), money(served["spread"])) == (
        AS_PAID + Decimal("400.00"),
        SPREAD + Decimal("400.00"),
    )


async def test_the_setting_defaults_on_with_no_row(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    body = await _get(api_client, f"/api/v1/{budget.id}/reports/settings")
    assert body == {"spread_sinking_funds": True}
    assert SPREAD_SINKING_FUNDS_KEY not in await GuideRepository(db_session).state(budget.id)


async def test_turning_it_back_on_deletes_the_row(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    await _set_spread(api_client, budget, False)
    assert await _set_spread(api_client, budget, True) == {"spread_sinking_funds": True}
    assert SPREAD_SINKING_FUNDS_KEY not in await GuideRepository(db_session).state(budget.id)


async def test_turning_it_off_is_undoable_and_recorded(db_session, api_client):
    budget = await _household(db_session, api_client)
    base = f"/api/v1/{budget.id}"
    await _set_spread(api_client, budget, False)

    changes = (await _get(api_client, f"{base}/changes", limit=5))["changes"]
    latest = changes[0]
    assert latest["entity_type"] == "guide_state"
    assert latest["after"] == {"_key": SPREAD_SINKING_FUNDS_KEY, "_value": {"on": False}}
    assert money(
        (await _get(api_client, f"{base}/reports/dashboard"))["essentials"]["monthly"]
    ) == (AS_PAID)

    r = await api_client.post(f"{base}/changes/undo")
    assert r.status_code == 200, r.text

    assert await _get(api_client, f"{base}/reports/settings") == {"spread_sinking_funds": True}
    assert money(
        (await _get(api_client, f"{base}/reports/dashboard"))["essentials"]["monthly"]
    ) == (SPREAD)


async def test_the_setting_is_per_budget(db_session, api_client):
    one = await _household(db_session, api_client)
    two = await _household(db_session, api_client)
    await _set_spread(api_client, one, False)

    assert await _get(api_client, f"/api/v1/{two.id}/reports/settings") == {
        "spread_sinking_funds": True
    }
    two_report = await _get(api_client, f"/api/v1/{two.id}/reports/essentials")
    assert money(two_report["essentials"]["monthly"]) == SPREAD
