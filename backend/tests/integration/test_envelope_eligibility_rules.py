"""Two questions that were one, and the two defects that hid in the gap.

`IS_ASSIGNABLE` answered "what may a picker offer" and was also read as "where
may money go". Those are different envelope sets, and the difference is exactly
a credit card's payment envelope: funded by the cards section, listed by
nothing. Conflated, each side got the other's answer:

- `assign_service` filtered on `is_assignable`, so a paydown target set on a
  card silently never filled. The comment defending the conflation claimed
  excluding card envelopes "would" cause that; it already had.
- `budget_service._require_envelope` checked the system group alone under a
  comment claiming it was "the same rule", so money could be assigned into an
  archived envelope by anything that was not a picker.

`IS_FUNDABLE` is the second question, written down.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.db.models import CategoryTarget
from igab.domain.exceptions import InvariantViolation
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.target_repo import TargetRepository
from igab.services.assign_service import AssignService
from igab.services.card_payment import ensure_payment_category
from igab.services.target_service import TargetService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

D = Decimal
JUL = date(2026, 7, 1)
AUG = date(2026, 8, 1)


def _assign(db_session, services) -> AssignService:
    target_repo = TargetRepository(db_session)
    return AssignService(
        services.budgets,
        target_repo,
        TargetService(target_repo),
        services.category_repo,
        services.category_group_repo,
    )


async def _world(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Redwood Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    await create_transaction(
        db_session, budget, checking, "2000.00", date(2026, 7, 2), category=inflow
    )
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    await db_session.flush()
    return services, budget, checking, group, cat


class TestACardPaydownTargetFinallyFills:
    async def test_auto_assign_funds_a_card_envelopes_target(self, db_session):
        """The defect, end to end. `ensure_payment_category` puts the envelope
        in a hidden group, `is_assignable` came back False, and the strategy
        that exists to fill targets skipped it every month."""
        services, budget, _checking, _group, _cat = await _world(db_session)
        visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
        linked = await ensure_payment_category(db_session, visa)
        assert linked is not None
        db_session.add(
            CategoryTarget(
                category_id=linked.id, target_type="monthly", target_amount=D("150.00")
            )
        )
        await db_session.flush()

        preview = await _assign(db_session, services).preview(budget.id, AUG, "underfunded")
        funded = {i.category_id: i.delta for i in preview.items}
        assert funded.get(linked.id) == D("150.00"), (
            "a paydown target on a card is what the target is for"
        )

    async def test_the_envelope_is_still_offered_by_nothing(self, db_session):
        """The other half. Fixing the funding must not put a card envelope
        into the move-money picker, which reads `is_assignable`."""
        services, budget, _checking, _group, _cat = await _world(db_session)
        visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
        linked = await ensure_payment_category(db_session, visa)
        await db_session.flush()

        loaded = await CategoryRepository(db_session).get(linked.id)
        assert loaded.is_assignable is False
        assert loaded.is_fundable is True


class TestMoneyEntersOnlyALiveEnvelope:
    async def test_assigning_into_an_archived_envelope_is_refused(self, db_session):
        services, budget, _checking, _group, cat = await _world(db_session)
        cat.is_hidden = True
        await db_session.flush()

        with pytest.raises(InvariantViolation, match="archived"):
            await services.budgets.set_assignment(budget.id, cat.id, AUG, D("100.00"))

    async def test_moving_money_into_an_archived_envelope_is_refused(self, db_session):
        services, budget, _checking, _group, cat = await _world(db_session)
        other = await create_category(
            db_session, budget, await create_category_group(db_session, budget, "Fun"), "Dining"
        )
        await services.budgets.set_assignment(budget.id, other.id, AUG, D("100.00"))
        cat.is_hidden = True
        await db_session.flush()

        with pytest.raises(InvariantViolation, match="archived"):
            await services.budgets.move_money(budget.id, other.id, cat.id, D("50.00"), AUG)

    async def test_money_may_always_leave_an_archived_envelope(self, db_session):
        """The asymmetry, and the reason it exists: a balance stranded in an
        archived envelope has to be rescuable. The archive sweep depends on
        this, so it is a test rather than a hope."""
        services, budget, _checking, _group, cat = await _world(db_session)
        other = await create_category(
            db_session, budget, await create_category_group(db_session, budget, "Fun"), "Dining"
        )
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("100.00"))
        cat.is_hidden = True
        await db_session.flush()

        await services.budgets.move_money(budget.id, cat.id, other.id, D("100.00"), AUG)

        summary = await services.budgets.get_budget_summary(budget.id, AUG)
        balances = {b.category_id: b.available for b in summary.category_balances}
        assert balances[cat.id] == D("0.00")
        assert balances[other.id] == D("100.00")

    async def test_reducing_an_archived_envelope_is_allowed(self, db_session):
        """`set_assignment` sets an absolute figure, so the same call is a
        deposit or a withdrawal depending on where it stands. Only the
        increase has to clear the rule."""
        services, budget, _checking, _group, cat = await _world(db_session)
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("100.00"))
        cat.is_hidden = True
        await db_session.flush()

        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("0.00"))

        summary = await services.budgets.get_budget_summary(budget.id, AUG)
        balances = {b.category_id: b.available for b in summary.category_balances}
        assert balances[cat.id] == D("0.00")

    async def test_income_still_refuses_both_directions(self, db_session):
        """The rule that was already there, and must survive the split."""
        services, budget, _checking, _group, _cat = await _world(db_session)
        income = await CategoryRepository(db_session).get_all(budget.id, include_hidden=True)
        inflow = next(c for c in income if c.name == "Inflow")

        with pytest.raises(InvariantViolation, match="Income categories"):
            await services.budgets.set_assignment(budget.id, inflow.id, AUG, D("50.00"))
