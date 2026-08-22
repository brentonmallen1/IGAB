"""Spending rolled up by a view's groups instead of the budget's own.

derkus: "i guess i'd like to have a report that looks at the category groups
where you can pick the view as a really high level look at the data."

The rule that matters: a report and the budget grid must never disagree about
where a category sits. Both hide what the view hides, and both collect the
unplaced under Unassigned unless the view says otherwise.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.repositories.budget_view_repo import BudgetViewRepository
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
)

TODAY = date.today()
START = TODAY - timedelta(days=20)


async def _world(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking", on_budget=True)
    bills = await create_category_group(db_session, budget, "Monthly Bills")
    fun = await create_category_group(db_session, budget, "Everyday")
    rent = await create_category(db_session, budget, bills, "Rent")
    power = await create_category(db_session, budget, bills, "Power")
    dining = await create_category(db_session, budget, fun, "Dining")

    for cat, amount in ((rent, "-1200.00"), (power, "-100.00"), (dining, "-200.00")):
        await create_transaction(db_session, budget, checking, amount, TODAY, category=cat)

    return budget, {"rent": rent, "power": power, "dining": dining, "bills": bills, "fun": fun}


async def _grouped(db_session, budget, **kw):
    """Roll the per-category rows up by their parent, the way the charts do."""
    items, total = await ReportService(db_session).spending_grouped(
        budget.id, START, TODAY, **kw
    )
    by_parent: dict[str, Decimal] = {}
    for i in items:
        by_parent[i["parent_name"]] = by_parent.get(i["parent_name"], Decimal("0")) + i["total"]
    return by_parent, total


class TestDefaultArrangement:
    async def test_without_a_view_it_uses_the_budgets_own_groups(self, db_session):
        budget, c = await _world(db_session)
        items, total = await ReportService(db_session).spending_grouped(budget.id, START, TODAY)
        names = {i["parent_name"] for i in items}
        assert names == {"Monthly Bills", "Everyday"}
        assert total == Decimal("1500.00")


class TestViewArrangement:
    async def _need_want_view(self, db_session, budget, c, **view_kw):
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="Need / Want", **view_kw)
        groups = await repo.set_groups(view.id, ["Need", "Want"])
        need, want = groups[0], groups[1]
        await repo.set_placements(
            view.id,
            [
                {"category_id": c["rent"].id, "group_id": need.id},
                {"category_id": c["power"].id, "group_id": need.id},
                {"category_id": c["dining"].id, "group_id": want.id},
            ],
        )
        return view

    async def test_regroups_the_same_money(self, db_session):
        budget, c = await _world(db_session)
        view = await self._need_want_view(db_session, budget, c)

        by_name, total = await _grouped(db_session, budget, view_id=view.id)
        assert set(by_name) == {"Need", "Want"}
        assert by_name["Need"] == Decimal("1300.00")
        assert by_name["Want"] == Decimal("200.00")
        # Same money, read differently.
        assert total == Decimal("1500.00")

    async def test_categories_keep_their_own_names(self, db_session):
        budget, c = await _world(db_session)
        view = await self._need_want_view(db_session, budget, c)
        items, _ = await ReportService(db_session).spending_grouped(
            budget.id, START, TODAY, view_id=view.id
        )
        assert {i["name"] for i in items} == {"Rent", "Power", "Dining"}

    async def test_unplaced_categories_collect_under_unassigned(self, db_session):
        budget, c = await _world(db_session)
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="Partial")
        groups = await repo.set_groups(view.id, ["Need"])
        await repo.set_placements(
            view.id, [{"category_id": c["rent"].id, "group_id": groups[0].id}]
        )

        by_name, total = await _grouped(db_session, budget, view_id=view.id)
        assert by_name["Need"] == Decimal("1200.00")
        assert by_name["Unassigned"] == Decimal("300.00")
        assert total == Decimal("1500.00"), "nothing is lost by an incomplete view"

    async def test_hide_unassigned_drops_them_from_the_report_too(self, db_session):
        budget, c = await _world(db_session)
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="Tidy", hide_unassigned=True)
        groups = await repo.set_groups(view.id, ["Need"])
        await repo.set_placements(
            view.id, [{"category_id": c["rent"].id, "group_id": groups[0].id}]
        )

        by_name, total = await _grouped(db_session, budget, view_id=view.id)
        assert set(by_name) == {"Need"}
        assert total == Decimal("1200.00")

    async def test_hidden_categories_are_excluded(self, db_session):
        budget, c = await _world(db_session)
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="No Dining")
        groups = await repo.set_groups(view.id, ["Need"])
        await repo.set_placements(
            view.id,
            [
                {"category_id": c["rent"].id, "group_id": groups[0].id},
                {"category_id": c["dining"].id, "is_hidden": True},
            ],
        )

        by_name, total = await _grouped(db_session, budget, view_id=view.id)
        assert total == Decimal("1300.00"), "hidden money leaves the total as well"

    async def test_the_category_filter_still_narrows_within_a_view(self, db_session):
        """View and filter are separate axes here too: the view decides the
        grouping, the category filter decides the subset."""
        budget, c = await _world(db_session)
        view = await self._need_want_view(db_session, budget, c)

        by_name, total = await _grouped(
            db_session, budget, view_id=view.id, category_ids=[c["rent"].id]
        )
        assert set(by_name) == {"Need"}
        assert total == Decimal("1200.00")

    async def test_an_unknown_view_falls_back_to_the_default_groups(self, db_session):
        """A stale id in a persisted report filter must not empty the report."""
        import uuid

        budget, c = await _world(db_session)
        by_name, total = await _grouped(db_session, budget, view_id=uuid.uuid4())
        assert set(by_name) == {"Monthly Bills", "Everyday"}
        assert total == Decimal("1500.00")

    async def test_another_budgets_view_is_ignored(self, db_session):
        user = await create_user(db_session)
        budget, c = await _world(db_session)
        other = await create_budget(db_session, user, "Other")
        foreign = await BudgetViewRepository(db_session).create(
            budget_id=other.id, name="Theirs"
        )

        by_name, _ = await _grouped(db_session, budget, view_id=foreign.id)
        assert set(by_name) == {"Monthly Bills", "Everyday"}
