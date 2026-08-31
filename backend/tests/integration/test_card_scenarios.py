"""Every card scenario, built on a real budget and read back off the API's own
summary — the second of three suites over `ALL_SCENARIOS`.

The unit suite proves the arithmetic; this one proves the arithmetic survives
rows, repositories, and serialization. Same expectations, one definition.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.sample_budget.card_scenarios import ALL_SCENARIOS, CardScenario

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
IDS = [s.slug for s in ALL_SCENARIOS]
D = Decimal


async def _budget_with(db_session, *scenarios: CardScenario):
    """One budget carrying every scenario given — the demo's own shape."""
    services = make_services(db_session)
    user = await create_user(db_session)
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


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=IDS)
async def test_the_served_row_reads_what_the_scenario_says(db_session, scenario: CardScenario):
    services, budget, applied = await _budget_with(db_session, scenario)
    card = await _card_row(services, budget, applied[0].card_id)
    actual = {
        "balance": card.balance,
        "set_aside": card.set_aside,
        "uncovered": card.uncovered,
        "over_reserved": card.over_reserved,
        "short_reserved": card.short_reserved,
        "card_credit": card.card_credit,
        "riding": card.riding,
        "reserve_discrepancy": card.reserve_discrepancy,
    }
    assert actual == dict(vars(scenario.expect)), scenario.story


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=IDS)
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
        assert card.set_aside == item.scenario.expect.set_aside, item.scenario.slug
        assert card.uncovered == item.scenario.expect.uncovered, item.scenario.slug
    await assert_financial_invariants(db_session, budget.id)


async def test_a_shared_category_does_not_leak_between_cards(db_session):
    """Groceries is charged on three of these cards. A refund on one must not
    release another's reserve — the cost of that rule is the `reimbursed`
    scenario's residual, and this is the benefit."""
    services, budget, applied = await _budget_with(db_session, *ALL_SCENARIOS)
    rows = {i.scenario.slug: await _card_row(services, budget, i.card_id) for i in applied}
    assert rows["paid-in-full"].set_aside == D("200")
    assert rows["reimbursed"].short_reserved == D("100")
