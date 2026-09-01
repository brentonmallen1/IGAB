"""The card scenarios, generated as sample data — the third suite over
`ALL_SCENARIOS`.

The unit suite proves the arithmetic and the integration suite proves it
survives rows. This one proves the demo can actually *show* the shapes, which
until now it could not: the generator asserted that no card inflow may exist
anywhere in the register, which forbade the refund, reimbursement and
repayment cards outright.

The generator now asserts each declared card lands exactly where its scenario
says, so a passing generation is itself the contract. These tests read the
same figures back off the budget summary, which is what the page draws.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.repositories.target_repo import TargetRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.sample_budget.card_scenarios import ALL_SCENARIOS, CardScenario, build_scenario_spec
from igab.sample_budget.generator import SampleBudgetGenerator

from .factories import create_budget, create_user, make_services
from .invariants import assert_financial_invariants

ANCHOR = date(2026, 7, 25)
MONTH = date(2026, 7, 1)
IDS = [s.slug for s in ALL_SCENARIOS]


async def _generate(session, budget, spec):
    await seed_system_tags(session, budget.id)
    generator = SampleBudgetGenerator(
        session,
        budget.id,
        account_repo=AccountRepository(session),
        category_group_repo=CategoryGroupRepository(session),
        category_repo=CategoryRepository(session),
        payee_repo=PayeeRepository(session),
        transaction_repo=TransactionRepository(session),
        assignment_repo=BudgetAssignmentRepository(session),
        tag_repo=TagRepository(session),
        target_repo=TargetRepository(session),
        scheduled_repo=ScheduledTransactionRepository(session),
        reconciliation_repo=ReconciliationRepository(session),
        liability_repo=LiabilityRepository(session),
        spec=spec,
    )
    return await generator.generate(anchor=ANCHOR)


async def _summary(session, budget):
    services = make_services(session)
    return await services.budgets.get_budget_summary(budget.id, MONTH)


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=IDS)
async def test_a_scenario_can_be_generated_on_its_own(db_session, scenario: CardScenario):
    """One card, no distractions — what a `--scenario` reproduction is for.
    Generation asserting its own contract means reaching this line is most of
    the proof; the summary read is the rest."""
    budget = await create_budget(db_session, await create_user(db_session))
    await _generate(db_session, budget, build_scenario_spec((scenario,)))
    summary = await _summary(db_session, budget)
    card = next(c for c in summary.cards if c.name == scenario.card)
    assert card.set_aside == scenario.expect.set_aside, scenario.story
    assert card.uncovered == scenario.expect.uncovered
    assert card.card_credit == scenario.expect.card_credit
    assert card.reserve_discrepancy == Decimal("0")


async def test_all_six_shapes_on_one_budget(db_session):
    """The demo. Every shape visible in one Credit cards strip, which is what
    the strip was built for and what the row copy was written against."""
    budget = await create_budget(db_session, await create_user(db_session))
    await _generate(db_session, budget, build_scenario_spec(ALL_SCENARIOS))
    summary = await _summary(db_session, budget)
    rows = {c.name: c for c in summary.cards}
    assert len(rows) == len(ALL_SCENARIOS)
    for scenario in ALL_SCENARIOS:
        row = rows[scenario.card]
        assert row.set_aside == scenario.expect.set_aside, scenario.slug
        assert row.uncovered == scenario.expect.uncovered, scenario.slug
        assert row.over_reserved == scenario.expect.over_reserved, scenario.slug
        assert row.short_reserved == scenario.expect.short_reserved, scenario.slug
        assert row.card_credit == scenario.expect.card_credit, scenario.slug


async def test_the_generated_budget_is_sound_with_card_inflows_in_it(db_session):
    """The reserve identity has never run over generated data containing a
    refund or a residual — the generator forbade both. It does now."""
    budget = await create_budget(db_session, await create_user(db_session))
    await _generate(db_session, budget, build_scenario_spec(ALL_SCENARIOS))
    await assert_financial_invariants(db_session, budget.id)


async def test_generation_refuses_a_card_that_is_not_a_declared_scenario(db_session):
    """The ratchet in the other direction: the demo may not grow a card
    nobody can explain."""
    from dataclasses import replace

    from igab.sample_budget.spec import AccountSpec

    spec = build_scenario_spec((ALL_SCENARIOS[0],))
    spec = replace(spec, accounts=(*spec.accounts, AccountSpec("Stray Card", "credit_card")))
    budget = await create_budget(db_session, await create_user(db_session))
    with pytest.raises(AssertionError, match="not a declared scenario"):
        await _generate(db_session, budget, spec)


async def test_a_scenario_that_lies_about_itself_fails_generation(db_session):
    """The contract that replaced 'no card inflow may exist'. It is stronger:
    an unintended inflow now moves the position, and the position is checked."""
    from dataclasses import replace

    scenario = replace(
        ALL_SCENARIOS[0],
        expect=replace(ALL_SCENARIOS[0].expect, set_aside=Decimal("999")),
    )
    budget = await create_budget(db_session, await create_user(db_session))
    with pytest.raises(AssertionError, match="does not land where it says"):
        await _generate(db_session, budget, build_scenario_spec((scenario,)))
