"""Every card scenario, built on a real budget and read back off the API's own
summary — the second of three suites over `ALL_SCENARIOS`.

The unit suite proves the arithmetic; this one proves the arithmetic survives
rows, repositories, and serialization. Same expectations, one definition.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.sample_budget.card_scenarios import (
    ALL_SCENARIOS,
    ANCHORED_SCENARIOS,
    SETTLED_BY_OTHERS,
    CardScenario,
    ExpectedPosition,
)

from .card_scenario_apply import apply_card_scenario
from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_financial_invariants

ANCHOR = date(2026, 8, 15)
MONTH = date(2026, 8, 1)
EVERY = ALL_SCENARIOS + ANCHORED_SCENARIOS
IDS = [s.slug for s in EVERY]
D = Decimal


async def _budget_with(db_session, *scenarios: CardScenario, user=None):
    """One budget carrying every scenario given — the demo's own shape.
    `user` is the API client's, for a test that reads the budget over HTTP."""
    services = make_services(db_session)
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    # Enough income that funding every envelope is possible without the
    # budget going negative — the scenarios are about cards, not scarcity.
    await create_transaction(
        db_session, budget, checking, "40000.00", date(2026, 5, 1), category=inflow
    )
    group = await create_category_group(db_session, budget, "Everyday")
    await db_session.flush()

    cache: dict = {}
    applied = []
    for s in scenarios:
        applied.append(
            await apply_card_scenario(
                db_session,
                services,
                budget,
                s,
                ANCHOR,
                cash_account=checking,
                group=group,
                categories=cache,
            )
        )
    return services, budget, applied


async def _card_row(services, budget, card_id):
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    return next(c for c in summary.cards if c.account_id == card_id)


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
async def test_the_served_row_reads_what_the_scenario_says(db_session, scenario: CardScenario):
    services, budget, applied = await _budget_with(db_session, scenario)
    card = await _card_row(services, budget, applied[0].card_id)
    actual = ExpectedPosition(
        balance=card.balance,
        set_aside=card.set_aside,
        uncovered=card.uncovered,
        over_reserved=card.over_reserved,
        short_reserved=card.short_reserved,
        card_credit=card.card_credit,
        riding=card.riding,
        imported_riding=card.imported_riding,
        written_off=card.written_off,
        reserve_discrepancy=card.reserve_discrepancy,
        charged_this_month=card.charged_this_month,
        inflows_this_month=card.inflows_this_month,
        paid_this_month=card.paid_this_month,
        debt_change_this_month=card.debt_change_this_month,
    )
    assert scenario.expect.differences(actual) == {}, scenario.story


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
async def test_the_served_row_is_in_the_state_the_scenario_says(db_session, scenario: CardScenario):
    """The state the API actually serves, not the one the pure walk reaches.

    Both are checked, because they are reached by different routes and the
    route is where this has gone wrong before: the served one builds the
    ledger set out of the summary's card-corrected Available, and a figure
    read one repayment too high would call a squared-up tab an envelope
    holding card money.
    """
    services, budget, applied = await _budget_with(db_session, scenario)
    card = await _card_row(services, budget, applied[0].card_id)
    assert card.set_aside_state is scenario.set_aside_state, scenario.story


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
async def test_the_scenario_leaves_the_budget_sound(db_session, scenario: CardScenario):
    """Every invariant the suite has, over each shape — including the reserve
    identity, which had never seen a refund or a residual in generated data."""
    _, budget, _ = await _budget_with(db_session, scenario)
    await assert_financial_invariants(db_session, budget.id)


async def test_every_scenario_on_one_budget_still_reads_the_same(db_session):
    """The demo's shape: six cards side by side. A card's figures must not
    depend on what its neighbours are doing — exposure is per (category, card)
    on purpose, and this is what says so at the served layer."""
    services, budget, applied = await _budget_with(db_session, *ALL_SCENARIOS)
    for item in applied:
        card = await _card_row(services, budget, item.card_id)
        assert card.uncovered == item.scenario.expect.uncovered, item.scenario.slug
        if item.scenario.expect.set_aside is not None:
            assert card.set_aside == item.scenario.expect.set_aside, item.scenario.slug
    await assert_financial_invariants(db_session, budget.id)


async def test_a_shared_category_does_not_leak_between_cards(db_session):
    """Groceries is charged on three of these cards. A refund on one must not
    release another's reserve — the cost of that rule is the `reimbursed`
    scenario's residual, and this is the benefit."""
    services, budget, applied = await _budget_with(db_session, *ALL_SCENARIOS)
    rows = {i.scenario.slug: await _card_row(services, budget, i.card_id) for i in applied}
    assert rows["paid-in-full"].set_aside == D("200")
    assert rows["reimbursed"].short_reserved == D("100")


async def _reserving_rows(api_client, budget, card_id, month: str) -> dict:
    """The rows behind a card's Set aside for one month, as the card-reserve
    peek asks for them."""
    resp = await api_client.get(
        f"/api/v1/{budget.id}/transactions",
        params={
            "card_reserving": "true",
            "account_ids": str(card_id),
            "budget_month": month,
            "scope": "leaf",
            "limit": 5000,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _timeline(api_client, budget, card_id) -> dict:
    resp = await api_client.get(f"/api/v1/{budget.id}/cards/{card_id}/timeline/{MONTH}")
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
async def test_the_rows_behind_set_aside_reconcile_to_its_legs(
    db_session, api_client, scenario: CardScenario
):
    """What the card-reserve peek lists, against what the walk served.

    Two routes to one answer: the listing filters rows with
    `CARD_RESERVING_ROW` and `BUDGET_MONTH`; the timeline is the walk over
    `sum_credit_outflows_by_category`. Every month, the listed rows must net
    to the spending legs plus what rode and less what a refund repaid of a
    ride — the lines the peek draws under its list. A row the walk summed
    but the listing missed, or the other way round, breaks the sum by its
    own amount.
    """
    _, budget, applied = await _budget_with(db_session, scenario, user=api_client.test_user)
    card_id = applied[0].card_id
    timeline = await _timeline(api_client, budget, card_id)
    anchor = timeline["anchor_month"]
    walked = [m for m in timeline["months"] if anchor is None or m["month"] >= anchor]
    assert walked, scenario.slug
    for m in walked:
        listed = await _reserving_rows(api_client, budget, card_id, m["month"])
        spent = -D(str(listed["total_amount"]))
        legs = (
            D(str(m["reserved"]))
            - D(str(m["released"]))
            - D(str(m["residual"]))
            + D(str(m["rode"]))
            - D(str(m["ride_repaid"]))
        )
        assert spent == legs, f"{scenario.slug} {m['month']}"


async def test_the_settle_up_month_lists_the_tab_and_its_repayment(db_session, api_client):
    """By hand, on SETTLED_BY_OTHERS: the settle-up month charged the tab 200
    on the card and took 1,000 back, so the list nets to an 800 inflow. Of
    that, 400 repaid what the tab had ridden onto the card the two months
    before — moving nothing in Set aside — and 400 had nowhere to go but Set
    aside, as residual. Groceries spent nothing on the card that month and is
    not in the list."""
    _, budget, applied = await _budget_with(
        db_session, SETTLED_BY_OTHERS, user=api_client.test_user
    )
    card_id = applied[0].card_id
    listed = await _reserving_rows(api_client, budget, card_id, MONTH.isoformat())
    assert sorted(D(str(t["amount"])) for t in listed["transactions"]) == [D("-200"), D("1000")]
    assert D(str(listed["total_amount"])) == D("800")

    [month] = [
        m
        for m in (await _timeline(api_client, budget, card_id))["months"]
        if m["month"] == MONTH.isoformat()
    ]
    assert D(str(month["ride_repaid"])) == D("400")
    assert D(str(month["residual"])) == D("400")
    assert D(str(month["reserved"])) == D("0")
    assert D(str(month["rode"])) == D("0")
