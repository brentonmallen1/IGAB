"""The card walk, cached in process on the snapshot cache's generation.

`BudgetService.card_walk` keeps its history-wide reads and the walk over them
in `services.walk_cache`, valid for one `BudgetSnapshotMeta.generation`. Three
things have to hold, and each has its own tests here:

1. **A hit serves what a cold walk would.** Every card scenario, read three
   ways — the live path (no snapshot cache, so nothing is cached), the
   snapshot path cold, and the snapshot path again from the cache — serves
   one summary. A caller that mutated a cached walk would make the third read
   differ from the second.
2. **A write is seen.** Every input the walk reads — a card charge, an
   assignment to a card's envelope, an account's columns — reaches the next
   summary, which then agrees with the live path. This is the invalidation:
   the hooks in `igab.db.invalidation` delete the meta row, and no entry is
   ever stored or served without one.
3. **An account switched off budget leaves the envelopes.** Account was not
   watched before the walk was cached, so the category snapshots kept the
   account's spending until some unrelated write — named here because the
   cache needed `Account` watched and found the older bug on the way.
"""

import copy
from datetime import date

import pytest

from igab.repositories.account_repo import AccountRepository
from igab.repositories.snapshot_repo import SnapshotRepository
from igab.services.budget_service import BudgetService

from .factories import create_account, create_category, create_category_group, create_transaction
from .test_card_scenarios import EVERY, IDS, MONTH, _budget_with


def _pair(services) -> tuple[BudgetService, BudgetService]:
    """(live, snapshot-backed): the live path caches nothing, so it is the
    oracle a cached walk is checked against."""
    live = services.budgets
    assert live.snapshot_repo is None
    snap = copy.copy(live)
    snap.snapshot_repo = SnapshotRepository(live.assignment_repo.session)
    return live, snap


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
async def test_a_cached_walk_serves_what_a_cold_one_does(db_session, scenario):
    services, budget, _ = await _budget_with(db_session, scenario)
    live, snap = _pair(services)

    oracle = await live.get_budget_summary(budget.id, MONTH)
    cold = await snap.get_budget_summary(budget.id, MONTH)
    first = await snap.card_walk(budget.id, MONTH)
    warm = await snap.get_budget_summary(budget.id, MONTH)
    again = await snap.card_walk(budget.id, MONTH)

    # It was a hit: the same walk object, not an equal recomputation.
    assert again.funding is first.funding
    assert cold == oracle
    assert warm == cold


async def test_the_live_path_never_stores_a_walk(db_session):
    """No snapshot cache means no generation, and no generation means no
    entry — the oracle above is only an oracle if this holds."""
    services, budget, _ = await _budget_with(db_session, EVERY[0])
    live, _snap = _pair(services)
    first = await live.card_walk(budget.id, MONTH)
    again = await live.card_walk(budget.id, MONTH)
    assert again.funding is not first.funding
    assert again.funding == first.funding


async def _primed(db_session, scenario=EVERY[0]):
    services, budget, applied = await _budget_with(db_session, scenario)
    live, snap = _pair(services)
    before = await snap.get_budget_summary(budget.id, MONTH)
    # Primed: the next read would be a hit if nothing were written.
    walk = await snap.card_walk(budget.id, MONTH)
    assert (await snap.card_walk(budget.id, MONTH)).funding is walk.funding
    return live, snap, budget, applied[0], before


def _card(summary, card_id):
    return next(c for c in summary.cards if c.account_id == card_id)


async def test_a_card_charge_after_a_cached_walk_reaches_the_summary(db_session):
    live, snap, budget, applied, before = await _primed(db_session)
    card = await AccountRepository(db_session).get_or_raise(applied.card_id)
    # An envelope the scenario spends from on this card — not Interest &
    # fees, which the scenario's category map also carries.
    spent_from = next(e.category for e in applied.scenario.events if e.kind == "spend")
    envelope = applied.categories[spent_from]

    await create_transaction(
        db_session, budget, card, "-37.00", date(2026, 8, 12), category=envelope
    )

    after = await snap.get_budget_summary(budget.id, MONTH)
    was, now = _card(before, card.id), _card(after, card.id)
    assert now.balance == was.balance - 37
    # The walk's own legs moved: the charge reserved what the envelope had
    # and rode on the card for the rest. A stale walk moves neither.
    assert (now.reserved + now.riding) - (was.reserved + was.riding) == 37
    assert after == await live.get_budget_summary(budget.id, MONTH)


async def test_an_assignment_to_a_card_after_a_cached_walk_reaches_the_summary(db_session):
    live, snap, budget, applied, before = await _primed(db_session)
    set_aside = _card(before, applied.card_id).set_aside

    payment = next(
        b for b in before.category_balances if b.category_id == applied.payment_category_id
    )
    await snap.set_assignment(budget.id, applied.payment_category_id, MONTH, payment.assigned + 50)

    after = await snap.get_budget_summary(budget.id, MONTH)
    assert _card(after, applied.card_id).set_aside == set_aside + 50
    assert after == await live.get_budget_summary(budget.id, MONTH)


async def test_closing_off_a_card_after_a_cached_walk_takes_it_off_the_page(db_session):
    """A card moved off budget stops being a card: the walk's account list
    is one of its inputs, and an `on_budget` write is one the hooks watch."""
    live, snap, budget, applied, before = await _primed(db_session)
    assert any(c.account_id == applied.card_id for c in before.cards)

    await AccountRepository(db_session).update(applied.card_id, on_budget=False)

    after = await snap.get_budget_summary(budget.id, MONTH)
    assert all(c.account_id != applied.card_id for c in after.cards)
    assert after == await live.get_budget_summary(budget.id, MONTH)


async def test_an_account_switched_off_budget_leaves_the_envelopes(db_session):
    """The category snapshots sum envelope activity over on-budget accounts
    only (`txn_filters.ON_BUDGET_ACCOUNT`). Switching an account off budget
    used to leave its spending in the cached activity until the next
    unrelated write; it is now an invalidating write itself."""
    services, budget, _ = await _budget_with(db_session, EVERY[0])
    live, snap = _pair(services)
    group = await create_category_group(db_session, budget, "Side Gig")
    envelope = await create_category(db_session, budget, group, "Side Gig Supplies")
    side = await create_account(db_session, budget, "Side Checking")
    await create_transaction(
        db_session, budget, side, "-80.00", date(2026, 8, 9), category=envelope
    )
    before = await snap.get_budget_summary(budget.id, MONTH)
    row = next(b for b in before.category_balances if b.category_id == envelope.id)
    assert row.activity == -80

    await AccountRepository(db_session).update(side.id, on_budget=False)

    after = await snap.get_budget_summary(budget.id, MONTH)
    row = next(b for b in after.category_balances if b.category_id == envelope.id)
    assert row.activity == 0
    assert after == await live.get_budget_summary(budget.id, MONTH)


async def test_renaming_an_account_keeps_the_cache(db_session):
    """Only the columns a cache reads invalidate — `invalidation._ACCOUNT_COLUMNS`.
    A rename moves no figure, and a bank sync touches its account every run."""
    _live, snap, budget, applied, _before = await _primed(db_session)
    walk = await snap.card_walk(budget.id, MONTH)

    await AccountRepository(db_session).update(applied.card_id, name="Sapphire Visa (old)")

    assert (await snap.card_walk(budget.id, MONTH)).funding is walk.funding
