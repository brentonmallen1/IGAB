"""Copying a budget, whole or as a fresh start.

Both go through the snapshot round trip, so a clone inherits its guarantees:
every id remapped, the bank link dropped, nothing written until the file
validates. A structure-only copy then empties the ledger and gives each
account one Starting Balance row, so it opens on the balances you have
rather than on zero.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from igab.db.models import (
    Account,
    Asset,
    AssetValueSnapshot,
    BudgetAssignment,
    Category,
    Payee,
    ScheduledTransaction,
    Transaction,
)
from igab.domain.payee_names import STARTING_BALANCE_PAYEE

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
)

MONTH = date(2026, 8, 1)
AS_OF = date(2026, 8, 31)


async def _source(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user, name="Household")
    checking = await create_account(db_session, budget, "Checking")
    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    payee = await create_payee(db_session, budget, "Corner Market")
    await create_transaction(db_session, budget, checking, "2000.00", MONTH)
    await create_transaction(
        db_session, budget, checking, "-150.00", MONTH, category=groceries, payee=payee
    )
    await create_transaction(db_session, budget, card, "-90.00", MONTH, category=groceries)
    await create_budget_assignment(db_session, budget, groceries, MONTH, "300.00")
    await db_session.commit()
    return budget, checking, card, groceries


async def _clone(api_client, budget, **body):
    r = await api_client.post(f"/api/v1/budgets/{budget.id}/clone", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _count(db_session, model, budget_id) -> int:
    return (
        await db_session.execute(
            select(func.count()).select_from(model).where(model.budget_id == budget_id)
        )
    ).scalar_one()


class TestFullCopy:
    async def test_it_copies_everything_and_names_itself(self, db_session, api_client):
        budget, *_ = await _source(db_session, api_client)
        body = await _clone(api_client, budget, name="Household 2027")

        assert body["budget_name"] == "Household 2027"
        assert body["structure_only"] is False
        assert body["opening_balances"] == 0
        copy_id = body["budget_id"]
        for model in (Transaction, BudgetAssignment, Category, Account):
            assert await _count(db_session, model, copy_id) == await _count(
                db_session, model, budget.id
            )

    async def test_the_copy_is_separate_rows_not_a_second_name(self, db_session, api_client):
        budget, checking, *_ = await _source(db_session, api_client)
        copy_id = (await _clone(api_client, budget))["budget_id"]
        copies = (
            (
                await db_session.execute(
                    select(Account).where(Account.budget_id == copy_id, Account.name == "Checking")
                )
            )
            .scalars()
            .all()
        )
        assert len(copies) == 1
        assert copies[0].id != checking.id

    async def test_a_name_that_is_taken_is_made_unique_rather_than_refused(
        self, db_session, api_client
    ):
        budget, *_ = await _source(db_session, api_client)
        first = await _clone(api_client, budget, name="Household")
        second = await _clone(api_client, budget, name="Household")
        assert first["budget_name"] != second["budget_name"]


class TestStructureOnly:
    async def test_the_arrangement_stays_and_the_history_goes(self, db_session, api_client):
        budget, *_ = await _source(db_session, api_client)
        body = await _clone(
            api_client, budget, name="Fresh start", structure_only=True, as_of=AS_OF.isoformat()
        )
        copy_id = body["budget_id"]

        assert await _count(db_session, Category, copy_id) == await _count(
            db_session, Category, budget.id
        )
        assert await _count(db_session, Account, copy_id) == await _count(
            db_session, Account, budget.id
        )
        assert await _count(db_session, BudgetAssignment, copy_id) == 0
        assert await _count(db_session, ScheduledTransaction, copy_id) == 0

    async def test_every_account_opens_on_the_balance_it_had(self, db_session, api_client):
        budget, checking, card, _ = await _source(db_session, api_client)
        body = await _clone(api_client, budget, structure_only=True, as_of=AS_OF.isoformat())
        copy_id = body["budget_id"]

        # Checking: 2000 − 150 = 1850. Card: −90.
        assert body["opening_balances"] == 2
        rows = (
            (await db_session.execute(select(Transaction).where(Transaction.budget_id == copy_id)))
            .scalars()
            .all()
        )
        assert len(rows) == 2
        by_account = {}
        for row in rows:
            account = await db_session.get(Account, row.account_id)
            by_account[account.name] = row
            assert row.date == AS_OF
            assert row.category_id is None
            assert row.cleared == "reconciled"
        assert by_account["Checking"].amount == Decimal("1850.00")
        assert by_account["Sapphire Visa"].amount == Decimal("-90.00")

    async def test_the_opening_row_is_a_starting_balance_the_register_can_explain(
        self, db_session, api_client
    ):
        budget, *_ = await _source(db_session, api_client)
        copy_id = (await _clone(api_client, budget, structure_only=True))["budget_id"]
        rows = (
            (await db_session.execute(select(Transaction).where(Transaction.budget_id == copy_id)))
            .scalars()
            .all()
        )
        for row in rows:
            payee = await db_session.get(Payee, row.payee_id)
            assert payee is not None and payee.name == STARTING_BALANCE_PAYEE

    async def test_an_account_that_was_empty_gets_no_row(self, db_session, api_client):
        budget, *_ = await _source(db_session, api_client)
        await create_account(db_session, budget, "Unused Savings")
        await db_session.commit()
        body = await _clone(api_client, budget, structure_only=True, as_of=AS_OF.isoformat())
        # Still two: an account at zero has no position to carry.
        assert body["opening_balances"] == 2

    async def test_only_activity_before_the_date_counts(self, db_session, api_client):
        budget, checking, *_ = await _source(db_session, api_client)
        await create_transaction(db_session, budget, checking, "-500.00", AS_OF + timedelta(days=5))
        await db_session.commit()
        body = await _clone(api_client, budget, structure_only=True, as_of=AS_OF.isoformat())
        rows = (
            (
                await db_session.execute(
                    select(Transaction).where(Transaction.budget_id == body["budget_id"])
                )
            )
            .scalars()
            .all()
        )
        by_name = {}
        for row in rows:
            account = await db_session.get(Account, row.account_id)
            by_name[account.name] = row
        # The 500 five days after the date is not part of the position.
        assert by_name["Checking"].amount == Decimal("1850.00")

    async def test_an_asset_keeps_its_newest_value_and_loses_the_history(
        self, db_session, api_client
    ):
        """Clearing these outright would silently restate the copy's net
        worth: an asset's value is read newest-first from them."""
        budget, *_ = await _source(db_session, api_client)
        asset = Asset(budget_id=budget.id, name="House")
        db_session.add(asset)
        await db_session.flush()
        for when, value in ((date(2026, 6, 1), "400000"), (date(2026, 8, 1), "425000")):
            db_session.add(AssetValueSnapshot(asset_id=asset.id, date=when, value=Decimal(value)))
        await db_session.commit()

        copy_id = (await _clone(api_client, budget, structure_only=True))["budget_id"]
        kept = (
            (
                await db_session.execute(
                    select(AssetValueSnapshot)
                    .join(Asset, AssetValueSnapshot.asset_id == Asset.id)
                    .where(Asset.budget_id == copy_id)
                )
            )
            .scalars()
            .all()
        )
        assert [(k.date, k.value) for k in kept] == [(date(2026, 8, 1), Decimal("425000.0000"))]


class TestAccess:
    async def test_a_member_cannot_clone(self, db_session, api_client):
        """Owner-only, like the snapshot it is built on: a copy creates a
        budget the caller owns out of someone else's data."""
        other = await create_user(db_session)
        budget = await create_budget(db_session, other, name="Theirs")
        await db_session.commit()
        r = await api_client.post(f"/api/v1/budgets/{budget.id}/clone", json={})
        assert r.status_code in (403, 404)
