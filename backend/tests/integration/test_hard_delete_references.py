"""What still points at a category decides whether its row may go.

Fourteen tables carry a foreign key to `categories`. The delete preview's
`is_empty` checked five, so "empty" meant "no transactions, no money, no payee
default, no schedule" and said nothing about the other nine. Removing the row
on that basis would have taken a saved view's layout with it — `ondelete`
is CASCADE on targets, placements, filter selections and snapshots — and
blanked the from/to on historical money moves, which are SET NULL.

So the preview now names every contact point, split by whether severing it
costs anything, and only a category nothing records at all is removed outright.
Everything else keeps today's soft delete, whose whole virtue is that the name
goes on resolving for the records that mention it.
"""

from datetime import date
from decimal import Decimal

from igab.db.models import (
    BudgetAssignment,
    BudgetFilter,
    BudgetFilterCategory,
    Category,
    CategoryTarget,
)
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.category_service import CategoryService
from igab.services.undo_service import UndoService

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


def _service(db_session, services) -> CategoryService:
    return CategoryService(
        db_session,
        CategoryRepository(db_session),
        CategoryGroupRepository(db_session),
        services.budgets,
        TransactionRepository(db_session),
        BudgetAssignmentRepository(db_session),
    )


async def _world(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Redwood Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Gym")
    await db_session.flush()
    return services, budget, checking, group, cat


class TestNothingPointsAtIt:
    async def test_the_row_goes_outright(self, db_session):
        services, budget, _checking, _group, cat = await _world(db_session)
        svc = _service(db_session, services)
        assert (await svc.preview_delete(budget.id, [cat.id], AUG)).may_hard_delete is True

        await svc.delete_categories(budget.id, [cat.id], month=AUG)

        db_session.expunge_all()
        assert await db_session.get(Category, cat.id) is None

    async def test_undo_builds_it_again(self, db_session):
        """There is no flag to flip back, so the change record has to carry
        enough to rebuild the row — and rebuild it under the same id, since a
        new one would leave the change row pointing at nothing."""
        services, budget, _checking, group, cat = await _world(db_session)
        result = await _service(db_session, services).delete_categories(
            budget.id, [cat.id], month=AUG
        )
        await db_session.flush()

        await UndoService(db_session).undo_change(budget.id, result.change_id)
        await db_session.flush()

        db_session.expunge_all()
        again = await db_session.get(Category, cat.id)
        assert again is not None
        assert again.id == cat.id
        assert again.name == "Gym"
        assert again.category_group_id == group.id
        assert again.is_deleted is False


class TestSomethingRecordsIt:
    async def test_a_money_move_keeps_the_row(self, db_session):
        """The sharp case. `BudgetMove` is SET NULL, so removing the row would
        leave a record saying money moved from nowhere to nowhere — and the
        move is the only place that history exists."""
        services, budget, _checking, group, cat = await _world(db_session)
        other = await create_category(db_session, budget, group, "Dining")
        await create_transaction(
            db_session, budget, _checking, "500.00", AUG, category=None
        )
        await services.budgets.set_assignment(budget.id, cat.id, AUG, D("50.00"))
        await services.budgets.move_money(budget.id, cat.id, other.id, D("50.00"), AUG)

        svc = _service(db_session, services)
        preview = await svc.preview_delete(budget.id, [cat.id], AUG)
        assert [r.kind for r in preview.blocking_references] == ["budget_move"]
        assert preview.may_hard_delete is False

        await svc.delete_categories(budget.id, [cat.id], month=AUG)
        db_session.expunge_all()
        kept = await db_session.get(Category, cat.id)
        assert kept is not None and kept.is_deleted is True

    async def test_a_target_is_named_but_does_not_block(self, db_session):
        """A target describes the category and means nothing without it, so it
        is listed for the dialog to mention and severed by the cascade."""
        services, budget, _checking, _group, cat = await _world(db_session)
        db_session.add(
            CategoryTarget(category_id=cat.id, target_type="monthly", target_amount=D("100"))
        )
        await db_session.flush()

        preview = await _service(db_session, services).preview_delete(budget.id, [cat.id], AUG)

        assert [r.kind for r in preview.clearable_references] == ["target"]
        assert preview.blocking_references == []
        assert preview.may_hard_delete is True

    async def test_a_saved_filter_selection_is_named(self, db_session):
        services, budget, _checking, _group, cat = await _world(db_session)
        flt = BudgetFilter(budget_id=budget.id, name="Essentials")
        db_session.add(flt)
        await db_session.flush()
        db_session.add(BudgetFilterCategory(filter_id=flt.id, category_id=cat.id))
        await db_session.flush()

        preview = await _service(db_session, services).preview_delete(budget.id, [cat.id], AUG)

        assert "filter_selection" in [r.kind for r in preview.clearable_references]

    async def test_the_labels_are_countable_sentences(self, db_session):
        """The dialog shows these verbatim, so they have to read as a list a
        person can act on rather than as field names."""
        services, budget, _checking, _group, cat = await _world(db_session)
        db_session.add(
            CategoryTarget(category_id=cat.id, target_type="monthly", target_amount=D("100"))
        )
        await db_session.flush()

        preview = await _service(db_session, services).preview_delete(budget.id, [cat.id], AUG)

        assert preview.references[0].label == "1 savings target"

    async def test_history_still_soft_deletes(self, db_session):
        """The ordinary case, unchanged: a category with spending keeps its
        row so every report can still name it."""
        services, budget, checking, _group, cat = await _world(db_session)
        await create_transaction(db_session, budget, checking, "-30.00", AUG, category=cat)
        await db_session.flush()

        svc = _service(db_session, services)
        assert (await svc.preview_delete(budget.id, [cat.id], AUG)).may_hard_delete is False

        await svc.delete_categories(budget.id, [cat.id], month=AUG)
        db_session.expunge_all()
        kept = await db_session.get(Category, cat.id)
        assert kept is not None and kept.is_deleted is True
