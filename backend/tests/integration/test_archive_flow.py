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
    create_scheduled_transaction,
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


class TestALiveScheduleStopsIt:
    """Archiving leaves a schedule's pointer where it was, and the next time it
    fires the row it tries to enter is refused by `require_categorizable`.

    That is a landmine, not an error at the time: nothing tells the user, and
    the failure surfaces weeks later inside a cron job. The delete preview
    already counts schedules for the same reason; the archive preview did not.
    """

    async def test_a_schedule_filing_into_it_blocks_the_archive(self, db_session):
        services, budget, checking, _group, cat = await _world(db_session)
        await create_scheduled_transaction(
            db_session, budget, checking, "-15.00", "monthly", SEP, category=cat
        )

        svc = _svc(services, db_session)
        preview = await svc.preview_archive(budget.id, [cat.id], AUG)
        assert preview.blocked_by_schedule == ["Gym"]
        assert preview.may_archive is False

        with pytest.raises(InvariantViolation) as e:
            await svc.archive_categories(budget.id, [cat.id], month=AUG)
        # Names the envelope and the next action, not "cannot archive".
        assert "Gym" in str(e.value)
        assert "schedule" in str(e.value).lower()

    async def test_a_deleted_schedule_does_not(self, db_session):
        """A cancelled schedule never fires, so it strands nothing."""
        services, budget, checking, _group, cat = await _world(db_session)
        await create_scheduled_transaction(
            db_session,
            budget,
            checking,
            "-15.00",
            "monthly",
            SEP,
            category=cat,
            is_deleted=True,
        )

        svc = _svc(services, db_session)
        preview = await svc.preview_archive(budget.id, [cat.id], AUG)
        assert preview.blocked_by_schedule == []
        assert preview.may_archive is True
        await svc.archive_categories(budget.id, [cat.id], month=AUG)
        await db_session.refresh(cat)
        assert cat.is_archived is True

    async def test_re_filing_the_schedule_unblocks_it(self, db_session):
        """The refusal has to be a door, not a wall — the message tells the
        user to re-file the schedule, so doing that must actually work."""
        services, budget, checking, group, cat = await _world(db_session)
        elsewhere = await create_category(db_session, budget, group, "Dining")
        sched = await create_scheduled_transaction(
            db_session, budget, checking, "-15.00", "monthly", SEP, category=cat
        )
        svc = _svc(services, db_session)
        with pytest.raises(InvariantViolation):
            await svc.archive_categories(budget.id, [cat.id], month=AUG)

        sched.category_id = elsewhere.id
        await db_session.flush()
        await svc.archive_categories(budget.id, [cat.id], month=AUG)
        await db_session.refresh(cat)
        assert cat.is_archived is True


class TestArchivingAGroupRunsTheSameRefusal:
    """The "Hide group" button used to PATCH the flag straight onto the row — a
    plain column write with no balance check behind it. Archiving a group takes
    every envelope under it off the budget (`IN_ARCHIVED_GROUP`), so that route
    could stand a whole group's money somewhere unreachable in one click.
    """

    async def test_money_in_any_envelope_refuses_the_whole_group(self, db_session):
        services, budget, _checking, group, cat = await _world(db_session)
        await create_category(db_session, budget, group, "Dining")
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("40.00"))

        svc = _svc(services, db_session)
        preview = await svc.preview_archive_group(budget.id, group.id, AUG)
        assert preview.blocked_by_balance == ["Gym"]

        with pytest.raises(InvariantViolation) as e:
            await svc.archive_group(budget.id, group.id, month=AUG)
        assert "Gym" in str(e.value)
        await db_session.refresh(group)
        assert group.is_archived is False, "nothing moved, including the flag"

    async def test_an_empty_group_archives_and_stamps_the_date(self, db_session):
        services, budget, _checking, group, _cat = await _world(db_session)

        await _svc(services, db_session).archive_group(budget.id, group.id, month=AUG)
        await db_session.refresh(group)
        assert group.is_archived is True
        assert group.archived_at is not None

    async def test_the_categories_keep_their_own_flag(self, db_session):
        """The group's flag is the whole fact. Setting the categories' too
        would record one state in two places, and they would part company the
        first time the group came back with an envelope archived on its own
        merits inside it."""
        services, budget, _checking, group, cat = await _world(db_session)
        svc = _svc(services, db_session)

        await svc.archive_group(budget.id, group.id, month=AUG)
        await db_session.refresh(cat)
        assert cat.is_archived is False

        await svc.unarchive_group(budget.id, group.id)
        await db_session.refresh(group)
        await db_session.refresh(cat)
        assert group.is_archived is False
        assert group.archived_at is None
        assert cat.is_archived is False


class TestTheListingSaysWhyARowIsThere:
    """A category under an archived group is listed but is not itself archived,
    so "Restore" on it cleared a flag that was already false and the row stayed
    exactly where it was — a button that did nothing, twice in a row.

    The client cannot work this out for itself: archived groups are not in the
    groups listing it holds, so it cannot see the flag that put the row here.
    """

    async def test_a_group_archived_row_says_so(self, db_session):
        services, budget, _checking, group, cat = await _world(db_session)
        svc = _svc(services, db_session)
        await svc.archive_group(budget.id, group.id, month=AUG)

        rows = await svc.list_archived(budget.id, AUG)
        row = next(r for r in rows if r.id == cat.id)
        assert row.group_is_archived is True
        assert row.group_id == group.id
        # Its own flag is untouched — which is exactly why restoring it alone
        # would have changed nothing.
        await db_session.refresh(cat)
        assert cat.is_archived is False

    async def test_an_individually_archived_row_does_not(self, db_session):
        services, budget, _checking, _group, cat = await _world(db_session)
        svc = _svc(services, db_session)
        await svc.archive_categories(budget.id, [cat.id], month=AUG)

        rows = await svc.list_archived(budget.id, AUG)
        row = next(r for r in rows if r.id == cat.id)
        assert row.group_is_archived is False

    async def test_restoring_the_group_takes_the_row_off_the_listing(self, db_session):
        services, budget, _checking, group, cat = await _world(db_session)
        svc = _svc(services, db_session)
        await svc.archive_group(budget.id, group.id, month=AUG)
        assert any(r.id == cat.id for r in await svc.list_archived(budget.id, AUG))

        await svc.unarchive_group(budget.id, group.id)
        assert not any(r.id == cat.id for r in await svc.list_archived(budget.id, AUG))

    async def test_a_row_archived_both_ways_stays_until_both_are_undone(self, db_session):
        """Two states, two restores. Restoring the group leaves an envelope
        that was also archived on its own merits still archived, which is the
        honest answer rather than a surprise un-archive."""
        services, budget, _checking, group, cat = await _world(db_session)
        svc = _svc(services, db_session)
        await svc.archive_categories(budget.id, [cat.id], month=AUG)
        await svc.archive_group(budget.id, group.id, month=AUG)

        await svc.unarchive_group(budget.id, group.id)
        rows = await svc.list_archived(budget.id, AUG)
        row = next(r for r in rows if r.id == cat.id)
        assert row.group_is_archived is False, "now it offers the plain Restore"

        await svc.unarchive_categories(budget.id, [cat.id])
        assert not any(r.id == cat.id for r in await svc.list_archived(budget.id, AUG))


class TestRetiringAGroupReturnsItsMoney:
    """`archive_group` refuses over a balance because archiving one envelope is
    a tidying act, and moving someone's money to achieve it is not the caller's
    decision. Switching a whole feature off is a different act — there is no
    envelope left to move the money into — so `retire_group` returns it.

    One change row for both halves, because undoing half of it would put the
    envelopes back on the budget showing nothing in them.
    """

    async def test_the_money_reaches_ready_to_assign(self, db_session):
        services, budget, _checking, group, cat = await _world(db_session)
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("40.00"))
        before = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned

        released = await _svc(services, db_session).retire_group(budget.id, group.id, month=AUG)

        after = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
        assert released == D("40.00")
        assert after - before == D("40.00")
        await db_session.refresh(group)
        assert group.is_archived is True

    async def test_a_link_still_refuses(self, db_session):
        """Returning money does not fix a card envelope, so this is not swept
        past — it would strand the card instead of the money."""
        services, budget, _checking, _group, _cat = await _world(db_session)
        visa = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card"
        )
        linked = await ensure_payment_category(db_session, visa)
        assert linked is not None
        with pytest.raises(InvariantViolation):
            await _svc(services, db_session).retire_group(
                budget.id, linked.category_group_id, month=AUG
            )

    async def test_a_schedule_still_refuses(self, db_session):
        services, budget, checking, group, cat = await _world(db_session)
        await create_scheduled_transaction(
            db_session, budget, checking, "-15.00", "monthly", SEP, category=cat
        )
        with pytest.raises(InvariantViolation):
            await _svc(services, db_session).retire_group(budget.id, group.id, month=AUG)

    async def test_undo_puts_the_money_and_the_group_back(self, db_session):
        from igab.db.models import ChangeLog
        from igab.services.undo_service import UndoService
        from sqlalchemy import select

        services, budget, _checking, group, cat = await _world(db_session)
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("40.00"))
        before = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned

        await _svc(services, db_session).retire_group(budget.id, group.id, month=AUG)
        await db_session.flush()

        change = (
            await db_session.execute(
                select(ChangeLog)
                .where(ChangeLog.budget_id == budget.id, ChangeLog.action == "archive")
                .order_by(ChangeLog.created_at.desc())
            )
        ).scalars().first()
        assert change is not None

        await UndoService(db_session).undo_change(budget.id, change.id)
        await db_session.flush()

        await db_session.refresh(group)
        assert group.is_archived is False
        # Both halves, not one: the envelope holds its money again and Ready to
        # Assign is back where it started.
        after = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
        assert after == before
        balance = await services.budgets.get_category_balance(cat.id, AUG)
        assert balance.available == D("40.00")
