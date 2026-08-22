"""Spending rolled up by a view's groups instead of the budget's own.

derkus: "i guess i'd like to have a report that looks at the category groups
where you can pick the view as a really high level look at the data."

The rule that matters: a report and the budget grid must never disagree about
where a category sits. Both hide what the view hides, and both collect the
unplaced under Unassigned unless the view says otherwise.
"""

import uuid
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


async def _world(db_session, owner=None):
    user = owner or await create_user(db_session)
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
    items, total, _ = await ReportService(db_session).spending_grouped(
        budget.id, START, TODAY, **kw
    )
    by_parent: dict[str, Decimal] = {}
    for i in items:
        by_parent[i["parent_name"]] = by_parent.get(i["parent_name"], Decimal("0")) + i["total"]
    return by_parent, total


class TestDefaultArrangement:
    async def test_without_a_view_it_uses_the_budgets_own_groups(self, db_session):
        budget, c = await _world(db_session)
        items, total, _ = await ReportService(db_session).spending_grouped(budget.id, START, TODAY)
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
        items, _, _ = await ReportService(db_session).spending_grouped(
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

    async def test_a_complete_view_reports_nothing_dropped(self, db_session):
        budget, c = await _world(db_session)
        view = await self._need_want_view(db_session, budget, c)
        _, _, dropped = await ReportService(db_session).spending_grouped(
            budget.id, START, TODAY, view_id=view.id
        )
        assert dropped is None

    async def test_hidden_spending_is_reported_not_just_dropped(self, db_session):
        budget, c = await _world(db_session)
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="No Dining")
        groups = await repo.set_groups(view.id, ["Need"])
        await repo.set_placements(
            view.id,
            [
                {"category_id": c["rent"].id, "group_id": groups[0].id},
                {"category_id": c["power"].id, "group_id": groups[0].id},
                {"category_id": c["dining"].id, "is_hidden": True},
            ],
        )
        _, total, dropped = await ReportService(db_session).spending_grouped(
            budget.id, START, TODAY, view_id=view.id
        )
        assert total == Decimal("1300.00")
        assert dropped == {"categories": 1, "total": Decimal("200.00")}

    async def test_hide_unassigned_spending_counts_as_dropped(self, db_session):
        """hide_unassigned quietly removes every unplaced category — the
        summary is what keeps that legible on a chart."""
        budget, c = await _world(db_session)
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="Tidy", hide_unassigned=True)
        groups = await repo.set_groups(view.id, ["Need"])
        await repo.set_placements(
            view.id, [{"category_id": c["rent"].id, "group_id": groups[0].id}]
        )
        _, total, dropped = await ReportService(db_session).spending_grouped(
            budget.id, START, TODAY, view_id=view.id
        )
        assert total == Decimal("1200.00")
        assert dropped == {"categories": 2, "total": Decimal("300.00")}

    async def test_a_view_that_hides_everything_still_explains_itself(self, db_session):
        """The report the user actually hit: a sparse view + hide_unassigned
        left one category standing. Taken to the limit — nothing standing —
        the empty result must carry the reason, or it reads as data loss."""
        budget, c = await _world(db_session)
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="Void", hide_unassigned=True)
        items, total, dropped = await ReportService(db_session).spending_grouped(
            budget.id, START, TODAY, view_id=view.id
        )
        assert items == []
        assert total == Decimal("0")
        assert dropped == {"categories": 3, "total": Decimal("1500.00")}

    async def test_an_unknown_view_falls_back_to_the_default_groups(self, db_session):
        """A stale id in a persisted report filter must not empty the report."""
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


class TestThroughTheApi:
    """The service returns plain dicts; the endpoint validates them against
    `SpendingGroupedResponse`. Every test above stops short of that boundary,
    which is how `parent_id: uuid.UUID` shipped while the Unassigned bucket
    emitted `"__unassigned__"` — a 500 on the one path the service tests
    cover most carefully. These go over HTTP so the schema is in the loop.
    """

    async def _view(self, db_session, budget, c, *, place_all: bool, hide_unassigned=False):
        repo = BudgetViewRepository(db_session)
        view = await repo.create(
            budget_id=budget.id, name="Need / Want", hide_unassigned=hide_unassigned
        )
        groups = await repo.set_groups(view.id, ["Need", "Want"])
        placements = [{"category_id": c["rent"].id, "group_id": groups[0].id}]
        if place_all:
            placements += [
                {"category_id": c["power"].id, "group_id": groups[0].id},
                {"category_id": c["dining"].id, "group_id": groups[1].id},
            ]
        await repo.set_placements(view.id, placements)
        return view

    async def _get(self, api_client, budget, **params):
        return await api_client.get(
            f"/api/v1/{budget.id}/reports/spending-grouped",
            params={"start_date": START.isoformat(), "end_date": TODAY.isoformat(), **params},
        )

    async def test_a_view_that_leaves_a_category_unplaced_still_responds(
        self, api_client, db_session
    ):
        budget, c = await _world(db_session, api_client.test_user)
        view = await self._view(db_session, budget, c, place_all=False)

        resp = await self._get(api_client, budget, view_id=str(view.id))

        assert resp.status_code == 200
        body = resp.json()
        by_parent = {g["parent_name"] for g in body["groups"]}
        assert by_parent == {"Need", "Unassigned"}
        assert Decimal(body["total"]) == Decimal("1500.00")

    async def test_the_unassigned_bucket_shares_one_rollup_key(self, api_client, db_session):
        """The client groups on `parent_id`, so both unplaced categories have
        to arrive under the same key or Unassigned splits into two slices."""
        budget, c = await _world(db_session, api_client.test_user)
        view = await self._view(db_session, budget, c, place_all=False)

        body = (await self._get(api_client, budget, view_id=str(view.id))).json()

        keys = {g["parent_id"] for g in body["groups"] if g["parent_name"] == "Unassigned"}
        assert keys == {"__unassigned__"}

    async def test_a_fully_placed_view_responds(self, api_client, db_session):
        budget, c = await _world(db_session, api_client.test_user)
        view = await self._view(db_session, budget, c, place_all=True)

        resp = await self._get(api_client, budget, view_id=str(view.id))

        assert resp.status_code == 200
        assert {g["parent_name"] for g in resp.json()["groups"]} == {"Need", "Want"}

    async def test_hide_unassigned_responds(self, api_client, db_session):
        budget, c = await _world(db_session, api_client.test_user)
        view = await self._view(
            db_session, budget, c, place_all=False, hide_unassigned=True
        )

        resp = await self._get(api_client, budget, view_id=str(view.id))

        assert resp.status_code == 200
        assert {g["parent_name"] for g in resp.json()["groups"]} == {"Need"}

    async def test_the_default_arrangement_still_returns_group_uuids(
        self, api_client, db_session
    ):
        """Widening `parent_id` to a string must not change what the ordinary
        path emits — the client keys off it either way."""
        budget, c = await _world(db_session, api_client.test_user)

        body = (await self._get(api_client, budget)).json()

        assert {g["parent_name"] for g in body["groups"]} == {"Monthly Bills", "Everyday"}
        by_name = {g["parent_name"]: g["parent_id"] for g in body["groups"]}
        assert by_name["Monthly Bills"] == str(c["bills"].id)
        assert by_name["Everyday"] == str(c["fun"].id)

    async def test_the_response_carries_what_the_view_hid(self, api_client, db_session):
        budget, c = await _world(db_session, api_client.test_user)
        view = await self._view(
            db_session, budget, c, place_all=False, hide_unassigned=True
        )

        body = (await self._get(api_client, budget, view_id=str(view.id))).json()

        assert body["view_hidden_categories"] == 2
        assert Decimal(body["view_hidden_total"]) == Decimal("300.00")

    async def test_without_a_view_the_hidden_fields_are_zero(self, api_client, db_session):
        budget, _ = await _world(db_session, api_client.test_user)

        body = (await self._get(api_client, budget)).json()

        assert body["view_hidden_categories"] == 0
        assert Decimal(body["view_hidden_total"]) == Decimal("0")

    async def test_a_stale_view_id_falls_back_rather_than_erroring(
        self, api_client, db_session
    ):
        budget, _ = await _world(db_session, api_client.test_user)

        resp = await self._get(api_client, budget, view_id=str(uuid.uuid4()))

        assert resp.status_code == 200
        assert {g["parent_name"] for g in resp.json()["groups"]} == {
            "Monthly Bills",
            "Everyday",
        }
