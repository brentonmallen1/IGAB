"""Which categories a report is about, from the three ways of saying it.

Explicit categories, a saved filter, or a bare tag — all one kind of answer, a
set of category ids. The resolver exists so every scoped report folds them the
same way; before it, the arithmetic sat inline in one endpoint next to private
controls no other chart could reach.

The two cases worth stating loudest are the ones a naive resolver gets wrong:

- **Union, not intersection.** Three controls side by side ADD to the scope.
  Narrowing twice by accident is a far worse surprise than widening.
- **None is not an empty set.** No scope asked for means everything; a scope
  asked for that matched nothing means nothing. Collapse the two and a question
  about an unused tag is answered with the whole budget.
"""

import uuid
from datetime import date

import pytest

from igab.repositories.budget_filter_repo import BudgetFilterRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_scope import resolve_category_scope

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
)


async def create_transaction_for(db_session, budget, category):
    """One posted outflow in the current month, so a scoped report has
    something to include or leave out."""
    checking = await create_account(db_session, budget)
    return await create_transaction(
        db_session, budget, checking, "-120.00", date.today().replace(day=1), category=category
    )


async def _make_world(db_session, user):
    """Three categories; Groceries and Fuel tagged Essential, Dining bare."""
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    fuel = await create_category(db_session, budget, group, "Fuel")
    dining = await create_category(db_session, budget, group, "Dining")

    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    essential = await tags.get_system_tag(budget.id, "essential")
    assert essential is not None
    await tags.set_category_tags(groceries.id, [essential.id])
    await tags.set_category_tags(fuel.id, [essential.id])
    return budget, groceries, fuel, dining, essential, tags


@pytest.fixture
async def world(db_session):
    return await _make_world(db_session, await create_user(db_session))


async def _resolve(db_session, budget, **kwargs):
    return await resolve_category_scope(
        budget.id,
        category_ids=kwargs.get("category_ids"),
        filter_id=kwargs.get("filter_id"),
        tag_ids=kwargs.get("tag_ids"),
        filter_repo=BudgetFilterRepository(db_session),
        tag_repo=TagRepository(db_session),
    )


class TestNoScopeIsNotAnEmptyScope:
    async def test_nothing_asked_for_means_everything(self, db_session, world):
        budget, *_ = world
        scope = await _resolve(db_session, budget)
        assert scope.category_ids is None
        assert scope.is_scoped is False

    async def test_a_tag_nobody_has_applied_means_nothing(self, db_session, world):
        """The case that separates the two. A resolver that returned None here
        would answer "show me Wishlist" with the entire budget."""
        budget, _g, _f, _d, _essential, tags = world
        unused = await tags.get_system_tag(budget.id, "wishlist")
        assert unused is not None

        scope = await _resolve(db_session, budget, tag_ids=[unused.id])
        assert scope.category_ids == []
        assert scope.is_scoped is True

    async def test_an_empty_explicit_list_is_still_a_scope(self, db_session, world):
        budget, *_ = world
        scope = await _resolve(db_session, budget, category_ids=[])
        assert scope.category_ids == []
        assert scope.is_scoped is True


class TestTheThreeSourcesUnion:
    async def test_a_tag_resolves_to_its_categories(self, db_session, world):
        budget, groceries, fuel, _dining, essential, _tags = world
        scope = await _resolve(db_session, budget, tag_ids=[essential.id])
        assert set(scope.category_ids or []) == {groceries.id, fuel.id}

    async def test_categories_and_a_tag_add_up(self, db_session, world):
        """Not an intersection: the answer is three categories, not zero."""
        budget, groceries, fuel, dining, essential, _tags = world
        scope = await _resolve(db_session, budget, category_ids=[dining.id], tag_ids=[essential.id])
        assert set(scope.category_ids or []) == {groceries.id, fuel.id, dining.id}

    async def test_a_saved_filter_brings_its_own_tag_axis(self, db_session, world):
        """A filter's effective set is its named categories PLUS everything
        carrying its tags — resolved by the repository the budget page reads,
        so the two cannot disagree about which rows a filter means."""
        budget, groceries, fuel, dining, essential, _tags = world
        repo = BudgetFilterRepository(db_session)
        saved = await repo.create(budget_id=budget.id, name="Fixed costs")
        await repo.set_categories(saved.id, [dining.id])
        await repo.set_tags(saved.id, [essential.id])

        scope = await _resolve(db_session, budget, filter_id=saved.id)
        assert set(scope.category_ids or []) == {groceries.id, fuel.id, dining.id}

    async def test_the_result_is_stable_across_calls(self, db_session, world):
        """Sorted, so the same request builds the same query text."""
        budget, _g, _f, dining, essential, _tags = world
        first = await _resolve(db_session, budget, category_ids=[dining.id], tag_ids=[essential.id])
        second = await _resolve(
            db_session, budget, category_ids=[dining.id], tag_ids=[essential.id]
        )
        assert first.category_ids == second.category_ids


class TestAFilterThatIsNoLongerThere:
    """A stale id must not silently WIDEN the report to the whole budget. That
    looks like data appearing rather than a filter going missing, which is why
    it is reported rather than ignored."""

    async def test_a_missing_filter_is_reported(self, db_session, world):
        budget, *_ = world
        scope = await _resolve(db_session, budget, filter_id=uuid.uuid4())
        assert scope.filter_unavailable is True
        assert scope.category_ids == []
        assert scope.is_scoped is True

    async def test_another_budgets_filter_is_reported_too(self, db_session, world):
        budget, *_ = world
        other_user = await create_user(db_session)
        other_budget = await create_budget(db_session, other_user)
        repo = BudgetFilterRepository(db_session)
        theirs = await repo.create(budget_id=other_budget.id, name="Theirs")

        scope = await _resolve(db_session, budget, filter_id=theirs.id)
        assert scope.filter_unavailable is True

    async def test_a_missing_filter_does_not_discard_the_other_sources(self, db_session, world):
        """The tag still scopes the report; only the filter's contribution is
        lost, and the caller is told so."""
        budget, groceries, fuel, _dining, essential, _tags = world
        scope = await _resolve(db_session, budget, filter_id=uuid.uuid4(), tag_ids=[essential.id])
        assert scope.filter_unavailable is True
        assert set(scope.category_ids or []) == {groceries.id, fuel.id}


class TestTagsDoNotReachAcrossBudgets:
    async def test_another_budgets_tag_contributes_nothing(self, db_session, world):
        budget, *_ = world
        other_user = await create_user(db_session)
        other_budget = await create_budget(db_session, other_user)
        other_group = await create_category_group(db_session, other_budget, "Everyday")
        other_cat = await create_category(db_session, other_budget, other_group, "Groceries")
        await seed_system_tags(db_session, other_budget.id)
        other_tags = TagRepository(db_session)
        other_essential = await other_tags.get_system_tag(other_budget.id, "essential")
        assert other_essential is not None
        await other_tags.set_category_tags(other_cat.id, [other_essential.id])

        scope = await _resolve(db_session, budget, tag_ids=[other_essential.id])
        assert scope.category_ids == []


class TestAnEmptyScopeReachesTheReport:
    """The resolver's None-vs-empty distinction is only worth having if the
    query builders honour it. Every one of them said `if category_ids:`, which
    treats an empty scope as no scope — so a report scoped to a tag nobody has
    applied answered with the whole budget. `report_service.scoped` is the one
    statement of the rule now; this is it end to end.
    """

    async def test_a_tag_with_no_categories_reports_nothing(self, db_session, api_client):
        # Owned by the API's user, so the endpoint will serve it.
        budget, groceries, _fuel, _dining, _essential, tags = await _make_world(
            db_session, api_client.test_user
        )
        await create_transaction_for(db_session, budget, groceries)

        unused = await tags.get_system_tag(budget.id, "wishlist")
        assert unused is not None
        resp = await api_client.get(
            f"/api/v1/{budget.id}/reports/spending-trends?tag_ids={unused.id}"
        )
        assert resp.status_code == 200, resp.text
        assert float(resp.json()["total"]) == 0.0, "an unused tag must not mean 'everything'"

    async def test_the_same_report_unscoped_still_sees_it(self, db_session, api_client):
        """The complement: without the scope the same row is counted, so the
        assertion above is about the scope and not about an empty budget."""
        budget, groceries, *_ = await _make_world(db_session, api_client.test_user)
        await create_transaction_for(db_session, budget, groceries)

        resp = await api_client.get(f"/api/v1/{budget.id}/reports/spending-trends")
        assert resp.status_code == 200, resp.text
        assert float(resp.json()["total"]) == 120.0


#: Every report the shared filter bar can scope, and how to read a total out of
#: its response. One list, so a seventh scoped report either joins it or fails
#: the coverage check below — which is the whole reason this file exists rather
#: than one assertion per chart, written whenever someone remembers.
SCOPED_REPORTS: list[tuple[str, str, object]] = [
    ("spending-trends", "spending-trends", lambda body: float(body["total"])),
    ("spending-grouped", "spending-grouped", lambda body: float(body["total"])),
    ("day-patterns", "day-patterns", lambda body: sum(float(d["total"]) for d in body["days"])),
    ("timeline", "large-transactions", lambda body: float(len(body["transactions"]))),
]


class TestEveryScopedReportHonoursTheSameScope:
    """`spending-grouped` serves three tabs on its own (pareto, treemap,
    spending breakdown), which is why four endpoints cover six."""

    @pytest.mark.parametrize(
        ("name", "path", "read"), SCOPED_REPORTS, ids=[r[0] for r in SCOPED_REPORTS]
    )
    async def test_a_tag_scopes_it(self, db_session, api_client, name, path, read):
        budget, groceries, _fuel, dining, essential, _tags = await _make_world(
            db_session, api_client.test_user
        )
        await create_transaction_for(db_session, budget, groceries)
        await create_transaction_for(db_session, budget, dining)

        everything = await api_client.get(f"/api/v1/{budget.id}/reports/{path}")
        tagged = await api_client.get(f"/api/v1/{budget.id}/reports/{path}?tag_ids={essential.id}")
        assert everything.status_code == 200, everything.text
        assert tagged.status_code == 200, tagged.text
        # Groceries is tagged, Dining is not: the scope must lose exactly one.
        assert read(tagged.json()) < read(everything.json()), name

    @pytest.mark.parametrize(
        ("name", "path", "read"), SCOPED_REPORTS, ids=[r[0] for r in SCOPED_REPORTS]
    )
    async def test_a_saved_filter_scopes_it_the_same_way(
        self, db_session, api_client, name, path, read
    ):
        budget, groceries, _fuel, dining, essential, _tags = await _make_world(
            db_session, api_client.test_user
        )
        await create_transaction_for(db_session, budget, groceries)
        await create_transaction_for(db_session, budget, dining)
        repo = BudgetFilterRepository(db_session)
        saved = await repo.create(budget_id=budget.id, name="Fixed costs")
        await repo.set_tags(saved.id, [essential.id])

        by_tag = await api_client.get(f"/api/v1/{budget.id}/reports/{path}?tag_ids={essential.id}")
        by_filter = await api_client.get(f"/api/v1/{budget.id}/reports/{path}?filter_id={saved.id}")
        assert by_filter.status_code == 200, by_filter.text
        # A filter over the same tag is the same scope, or the two controls in
        # the bar would answer one question differently.
        assert read(by_filter.json()) == read(by_tag.json()), name

    @pytest.mark.parametrize(
        ("name", "path", "read"), SCOPED_REPORTS, ids=[r[0] for r in SCOPED_REPORTS]
    )
    async def test_a_tag_nobody_applied_reports_nothing(
        self, db_session, api_client, name, path, read
    ):
        budget, groceries, *_rest, tags = await _make_world(db_session, api_client.test_user)
        await create_transaction_for(db_session, budget, groceries)
        unused = await tags.get_system_tag(budget.id, "wishlist")
        assert unused is not None

        resp = await api_client.get(f"/api/v1/{budget.id}/reports/{path}?tag_ids={unused.id}")
        assert resp.status_code == 200, resp.text
        assert read(resp.json()) == 0.0, name


def test_the_list_covers_every_scoped_report():
    """The coverage check. `TAB_FILTER_SUPPORT` on the client is the other half
    of this contract; here we assert against the endpoints, so adding a scoped
    report without wiring the resolver fails rather than silently ignoring the
    scope a user set.
    """
    import inspect

    from igab.api.v1 import reports as reports_module

    scoped_endpoints = {
        name
        for name, fn in vars(reports_module).items()
        if inspect.iscoroutinefunction(fn)
        and "category_ids" in inspect.signature(fn).parameters
        and "report_svc" in inspect.signature(fn).parameters
    }
    resolved = {
        name
        for name in scoped_endpoints
        if "resolve_category_scope" in inspect.getsource(getattr(reports_module, name))
    }
    assert scoped_endpoints - resolved == set(), (
        "these endpoints take category_ids but never resolve a filter or tag scope: "
        f"{sorted(scoped_endpoints - resolved)}"
    )
