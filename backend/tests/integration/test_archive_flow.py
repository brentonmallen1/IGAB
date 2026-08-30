"""Archiving refuses while money would be left behind.

Once archived, an envelope is off the budget grid entirely — there is no
"show archived" toggle to find it behind any more — so a balance left in one is
unreachable rather than merely untidy. That is the whole reason this refuses
instead of tidying up quietly: sweeping someone's money without asking is the
wrong default on the one screen whose job is telling them where their money is.

The complement is `test_envelope_eligibility_rules.py`: money may always LEAVE
an archived envelope, which is what makes "move it out first" a real
instruction rather than a dead end.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.category_service import CategoryService
from igab.services.card_payment import ensure_payment_category

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
AUG = date(2026, 8, 1)
SEP = date(2026, 9, 1)


async def _world(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Redwood Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    await create_transaction(
        db_session, budget, checking, "2000.00", date(2026, 8, 2), category=inflow
    )
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Gym")
    await db_session.flush()
    return services, budget, checking, group, cat


def _svc(services, db_session):
    return CategoryService(
        db_session,
        CategoryRepository(db_session),
        CategoryGroupRepository(db_session),
        services.budgets,
        TransactionRepository(db_session),
        BudgetAssignmentRepository(db_session),
    )


class TestArchivingRefusesToStrandMoney:
    async def test_an_envelope_holding_money_cannot_be_archived(self, db_session):
        services, budget, _checking, _group, cat = await _world(db_session)
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("100.00"))

        with pytest.raises(InvariantViolation, match="still holds money"):
            await _svc(services, db_session).archive_categories(
                budget.id, [cat.id], month=AUG
            )

        assert (await CategoryRepository(db_session).get(cat.id)).is_archived is False

    async def test_the_preview_names_the_envelope_rather_than_a_total(self, db_session):
        """A dialog that says "$100 must move" over three envelopes tells the
        user nothing about which one to open."""
        services, budget, _checking, group, cat = await _world(db_session)
        other = await create_category(db_session, budget, group, "Dining")
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("100.00"))

        preview = await _svc(services, db_session).preview_archive(
            budget.id, [cat.id, other.id], AUG
        )
        assert preview.blocked_by_balance == ["Gym"]
        assert preview.may_archive is False
        assert preview.available == D("100.00")

    async def test_money_committed_to_a_later_month_also_blocks(self, db_session):
        """`available` is a viewed-month figure and cannot see it. The delete
        preview learned this the same way, which is why it carries
        `future_assigned` too."""
        services, budget, _checking, _group, cat = await _world(db_session)
        await services.budgets.set_assignment(budget.id, cat.id, SEP, D("60.00"))

        preview = await _svc(services, db_session).preview_archive(budget.id, [cat.id], AUG)
        assert preview.future_assigned == D("60.00")
        assert preview.may_archive is False

    async def test_a_card_envelope_cannot_be_archived_at_all(self, db_session):
        """The card owns it. Archiving would leave the card reserving into an
        envelope the budget no longer draws."""
        services, budget, _checking, _group, _cat = await _world(db_session)
        visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
        linked = await ensure_payment_category(db_session, visa)
        await db_session.flush()

        with pytest.raises(InvariantViolation, match="card or a tracked debt"):
            await _svc(services, db_session).archive_categories(
                budget.id, [linked.id], month=AUG
            )


class TestArchivingWhenTheMoneyHasMoved:
    async def test_an_empty_envelope_archives_and_is_stamped(self, db_session):
        services, budget, _checking, _group, cat = await _world(db_session)

        await _svc(services, db_session).archive_categories(budget.id, [cat.id], month=AUG)

        loaded = await CategoryRepository(db_session).get(cat.id)
        assert loaded.is_archived is True
        assert loaded.archived_at is not None

    async def test_moving_the_money_out_unblocks_it(self, db_session):
        """The instruction the dialog gives, followed end to end."""
        services, budget, _checking, group, cat = await _world(db_session)
        other = await create_category(db_session, budget, group, "Dining")
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("100.00"))

        await services.budgets.move_money(budget.id, cat.id, other.id, D("100.00"), AUG)
        await _svc(services, db_session).archive_categories(budget.id, [cat.id], month=AUG)

        assert (await CategoryRepository(db_session).get(cat.id)).is_archived is True

    async def test_history_survives_archiving(self, db_session):
        """The point of archiving rather than deleting."""
        services, budget, checking, _group, cat = await _world(db_session)
        txn = await create_transaction(
            db_session, budget, checking, "-40.00", date(2026, 8, 9), category=cat
        )
        # Assigned 40, spent 40: the envelope is empty, which is the state
        # archiving requires. Nothing left to move.
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("40.00"))

        await _svc(services, db_session).archive_categories(budget.id, [cat.id], month=AUG)

        again = await TransactionRepository(db_session).get(txn.id)
        assert again is not None and again.category_id == cat.id

    async def test_an_overspent_envelope_is_blocked_too(self, db_session):
        """Non-zero in the other direction. Archiving an overspent envelope
        would hide a debt behind a screen with no toggle to open it."""
        services, budget, checking, _group, cat = await _world(db_session)
        await create_transaction(
            db_session, budget, checking, "-25.00", date(2026, 8, 9), category=cat
        )
        await db_session.flush()

        preview = await _svc(services, db_session).preview_archive(budget.id, [cat.id], AUG)
        assert preview.available == D("-25.00")
        assert preview.may_archive is False

    async def test_restoring_clears_the_stamp(self, db_session):
        """A stale "archived on" date against a live envelope is a worse
        answer than none."""
        services, budget, _checking, _group, cat = await _world(db_session)
        svc = _svc(services, db_session)
        await svc.archive_categories(budget.id, [cat.id], month=AUG)

        await svc.unarchive_categories(budget.id, [cat.id])

        loaded = await CategoryRepository(db_session).get(cat.id)
        assert loaded.is_archived is False
        assert loaded.archived_at is None


class TestTheArchivedListing:
    """Archived envelopes are off the grid entirely, so this listing is their
    only face. It has to be complete, or money goes missing from both places
    at once."""

    async def test_it_carries_what_the_modal_shows(self, db_session):
        services, budget, checking, _group, cat = await _world(db_session)
        await create_transaction(
            db_session, budget, checking, "-40.00", date(2026, 8, 9), category=cat
        )
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("40.00"))
        svc = _svc(services, db_session)
        await svc.archive_categories(budget.id, [cat.id], month=AUG)

        rows = await svc.list_archived(budget.id, AUG)

        assert len(rows) == 1
        assert rows[0].name == "Gym"
        assert rows[0].group_name == "Everyday"
        assert rows[0].transaction_count == 1
        assert rows[0].archived_at is not None
        assert rows[0].available == D("0.00")

    async def test_a_category_whose_group_is_archived_is_listed_too(self, db_session):
        """Its own flag is false, so `get_all(include_archived=False)` returns
        it and the grid would draw it while the group it belongs to is gone.
        That asymmetry is the one `category_filters` opens with."""
        services, budget, _checking, group, cat = await _world(db_session)
        group.is_archived = True
        await db_session.flush()

        rows = await _svc(services, db_session).list_archived(budget.id, AUG)

        assert [r.name for r in rows] == ["Gym"]

    async def test_a_balance_left_by_an_older_archive_is_visible(self, db_session):
        """The reason `available` is on this row at all. Flipping the flag
        directly is what the app did before the flow existed, and those rows
        exist in real budgets — this listing is the only place their money
        shows up now."""
        services, budget, _checking, _group, cat = await _world(db_session)
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("75.00"))
        cat.is_archived = True
        await db_session.flush()

        rows = await _svc(services, db_session).list_archived(budget.id, AUG)

        assert rows[0].available == D("75.00")
        assert rows[0].archived_at is None  # never stamped, and not invented

    async def test_a_live_envelope_is_not_listed(self, db_session):
        services, budget, _checking, _group, _cat = await _world(db_session)
        assert await _svc(services, db_session).list_archived(budget.id, AUG) == []
