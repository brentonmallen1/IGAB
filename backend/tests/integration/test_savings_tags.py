"""What makes the savings report show anything.

The report is driven entirely by categories carrying the `savings` or
`long_term_expense` system tag. Nothing tagged anything: the importer didn't,
the backfill only ran when a budget had NO system tags at all, and a user who
already had a tag named "Savings" could never get the system one — their
categories were tagged with a tag the report cannot see. The result was a
report that was empty forever and said only "no savings categories tracked".
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Tag
from igab.domain.tag_hints import suggest_system_tag
from igab.integrations.ynab.models import YNABBudget, YNABTransaction
from igab.repositories.tag_repo import SYSTEM_TAGS, TagRepository, seed_system_tags

from .factories import create_budget, create_category, create_category_group, create_user
from .test_ynab_import import _importer

JAN5 = date(2026, 1, 5)


async def _system_keys(db_session, budget) -> set[str]:
    rows = (
        await db_session.execute(
            select(Tag).where(Tag.budget_id == budget.id, Tag.is_deleted == False)  # noqa: E712
        )
    ).scalars()
    return {t.system_key for t in rows if t.system_key}


class TestSuggestSystemTag:
    def test_reads_the_obvious_names(self):
        assert suggest_system_tag("Savings", "Goals").system_key == "savings"
        assert suggest_system_tag("Emergency Fund", "Goals").system_key == "savings"
        assert suggest_system_tag("Car Repairs", "True Expenses").system_key == "long_term_expense"
        assert suggest_system_tag("Sinking Fund", "Whatever").system_key == "long_term_expense"

    def test_the_categorys_own_name_wins_over_its_group(self):
        # A "Savings" category inside "True Expenses" is savings.
        assert suggest_system_tag("Savings", "True Expenses").system_key == "savings"

    def test_says_nothing_when_nothing_is_obvious(self):
        assert suggest_system_tag("Groceries", "Everyday") is None
        assert suggest_system_tag("Rent", "Bills") is None


class TestBackfill:
    async def test_fills_in_only_the_missing_keys(self, db_session):
        """The all-or-nothing guard is why debt_principal never reached any
        budget that already had the other three."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        repo = TagRepository(db_session)
        await repo.create(
            budget_id=budget.id, name="Savings", system_key="savings", color_slot="green"
        )

        await seed_system_tags(db_session, budget.id)
        assert await _system_keys(db_session, budget) == {k for k, _, _ in SYSTEM_TAGS}

    async def test_adopts_a_same_named_tag_the_user_already_made(self, db_session):
        """Skipping it is what the original migration did — leaving a budget
        where "Savings" existed, categories were tagged with it, and the
        report stayed empty because the tag had no system key."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        repo = TagRepository(db_session)
        mine = await repo.create(budget_id=budget.id, name="Savings", color_slot="blue")

        await seed_system_tags(db_session, budget.id)
        await db_session.refresh(mine)
        assert mine.system_key == "savings", "the user's tag was adopted, not duplicated"

        names = (await db_session.execute(select(Tag).where(Tag.budget_id == budget.id))).scalars()
        assert len([t for t in names if t.name.lower() == "savings"]) == 1

    async def test_running_it_twice_changes_nothing(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        await seed_system_tags(db_session, budget.id)
        before = await _system_keys(db_session, budget)
        await seed_system_tags(db_session, budget.id)
        assert await _system_keys(db_session, budget) == before

    async def test_listing_tags_backfills_a_missing_key(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        repo = TagRepository(db_session)
        for key, name, colour in SYSTEM_TAGS[:3]:
            await repo.create(budget_id=budget.id, name=name, system_key=key, color_slot=colour)

        listed = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
        assert "debt_principal" in {t["system_key"] for t in listed if t["system_key"]}


class TestImportTagging:
    async def _import(self, db_session, transactions):
        from .factories import make_services

        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        result = await _importer(services, db_session, budget).import_budget(
            YNABBudget(transactions=transactions, budget_entries=[])
        )
        await db_session.flush()
        return budget, result

    def _txn(self, category, group):
        return YNABTransaction(
            account_name="Checking",
            date=JAN5,
            payee="Somewhere",
            category_group=group,
            category=category,
            memo=None,
            amount=Decimal("-100.00"),
            cleared="cleared",
        )

    async def test_an_imported_savings_category_is_tagged(self, db_session):
        """Otherwise a YNAB import produces a savings report that is empty
        forever — nothing else tags categories, and the only place to do it by
        hand is a panel the user has no reason to open."""
        budget, result = await self._import(db_session, [self._txn("Emergency Fund", "Goals")])
        assert result.categories_tagged == 1

        tag_repo = TagRepository(db_session)
        tagged = await tag_repo.get_category_ids_by_system_keys(budget.id, ["savings"])
        assert len(tagged) == 1

    async def test_an_ordinary_category_is_left_alone(self, db_session):
        _, result = await self._import(db_session, [self._txn("Groceries", "Everyday")])
        assert result.categories_tagged == 0

    async def test_the_report_has_something_to_show_after_an_import(self, db_session):
        from igab.services.report_service import ReportService

        budget, _ = await self._import(db_session, [self._txn("Emergency Fund", "Goals")])
        report = await ReportService(db_session).savings_report(budget.id, months=12)
        assert len(report["categories"]) == 1
        assert report["categories"][0]["category_name"] == "Emergency Fund"

    async def test_a_users_existing_tags_are_never_rewritten(self, db_session):
        """Only newly created categories are tagged. An existing category's
        tags are the user's answer, not ours to revise."""
        from .factories import make_services

        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        group = await create_category_group(db_session, budget, "Goals")
        existing = await create_category(db_session, budget, group, "Emergency Fund")
        await TagRepository(db_session).set_category_tags(existing.id, [])

        result = await _importer(services, db_session, budget).import_budget(
            YNABBudget(transactions=[self._txn("Emergency Fund", "Goals")], budget_entries=[])
        )
        assert result.categories_tagged == 0
