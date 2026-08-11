"""convert_to_split: in-place split conversion that preserves the parent row's
identity (attachments, AI links, sync ids) — the review modal's Apply-split."""

from datetime import date
from decimal import Decimal

import pytest

from igab.db.models import Transaction, TransactionAttachment
from igab.domain.exceptions import InvariantViolation
from igab.services.transaction_service import SplitSpec

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

TXN_DATE = date(2026, 8, 1)


async def _setup(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    household = await create_category(db_session, budget, group, "Household")
    services = make_services(db_session)
    return budget, account, groceries, household, services


class TestConvertToSplit:
    async def test_parent_keeps_identity_and_children_carry_categories(self, db_session):
        budget, account, groceries, household, services = await _setup(db_session)
        txn = await create_transaction(
            db_session, budget, account, "-100.00", TXN_DATE, approved=False
        )
        txn.created_via = "ai_receipt"
        db_session.add(
            TransactionAttachment(
                transaction_id=txn.id,
                filename="r.webp",
                original_filename="r.jpg",
                content_type="image/webp",
                file_size=10,
                storage_path=f"2026/08/01/{txn.id}/r.webp",
            )
        )
        await db_session.flush()

        parent = await services.transactions.convert_to_split(
            budget.id,
            txn.id,
            [
                SplitSpec(amount=Decimal("-60.00"), category_id=groceries.id),
                SplitSpec(amount=Decimal("-40.00"), category_id=household.id),
            ],
        )

        assert parent.id == txn.id  # same row — identity preserved
        assert parent.is_split is True
        assert parent.category_id is None
        assert parent.amount == Decimal("-100.00")
        assert parent.created_via == "ai_receipt"

        children = await services.transaction_repo.get_splits(txn.id)
        assert len(children) == 2
        assert {c.category_id for c in children} == {groceries.id, household.id}
        # Children mirror the parent's posting state
        assert all(c.date == txn.date for c in children)
        assert all(c.approved is False for c in children)

    async def test_sum_mismatch_rejected(self, db_session):
        budget, account, groceries, household, services = await _setup(db_session)
        txn = await create_transaction(db_session, budget, account, "-100.00", TXN_DATE)
        with pytest.raises(InvariantViolation, match="do not sum"):
            await services.transactions.convert_to_split(
                budget.id,
                txn.id,
                [
                    SplitSpec(amount=Decimal("-60.00"), category_id=groceries.id),
                    SplitSpec(amount=Decimal("-30.00"), category_id=household.id),
                ],
            )
        await db_session.refresh(txn)
        assert txn.is_split is False

    async def test_reconciled_rejected(self, db_session):
        budget, account, groceries, household, services = await _setup(db_session)
        txn = await create_transaction(
            db_session, budget, account, "-100.00", TXN_DATE, cleared="reconciled"
        )
        with pytest.raises(InvariantViolation, match="reconciled"):
            await services.transactions.convert_to_split(
                budget.id,
                txn.id,
                [
                    SplitSpec(amount=Decimal("-60.00"), category_id=groceries.id),
                    SplitSpec(amount=Decimal("-40.00"), category_id=household.id),
                ],
            )

    async def test_already_split_rejected(self, db_session):
        budget, account, groceries, household, services = await _setup(db_session)
        txn = await create_transaction(
            db_session, budget, account, "-100.00", TXN_DATE, is_split=True
        )
        with pytest.raises(InvariantViolation, match="already split"):
            await services.transactions.convert_to_split(
                budget.id,
                txn.id,
                [
                    SplitSpec(amount=Decimal("-60.00"), category_id=groceries.id),
                    SplitSpec(amount=Decimal("-40.00"), category_id=household.id),
                ],
            )

    async def test_cross_budget_category_rejected(self, db_session):
        budget, account, groceries, household, services = await _setup(db_session)
        other_user = await create_user(db_session, email="other-split@example.com")
        other_budget = await create_budget(db_session, other_user)
        other_group = await create_category_group(db_session, other_budget, "Theirs")
        foreign_cat = await create_category(db_session, other_budget, other_group, "Foreign")

        txn = await create_transaction(db_session, budget, account, "-100.00", TXN_DATE)
        with pytest.raises(InvariantViolation):
            await services.transactions.convert_to_split(
                budget.id,
                txn.id,
                [
                    SplitSpec(amount=Decimal("-60.00"), category_id=groceries.id),
                    SplitSpec(amount=Decimal("-40.00"), category_id=foreign_cat.id),
                ],
            )

    async def test_endpoint_round_trip(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        account = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        household = await create_category(db_session, budget, group, "Household")
        txn = await create_transaction(db_session, budget, account, "-100.00", TXN_DATE)

        resp = await api_client.post(
            f"/api/v1/transactions/{txn.id}/split",
            params={"budget_id": str(budget.id)},
            json={
                "splits": [
                    {"amount": "-60.00", "category_id": str(groceries.id)},
                    {"amount": "-40.00", "category_id": str(household.id)},
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == str(txn.id)
        assert body["is_split"] is True

    async def test_endpoint_foreign_transaction_404(self, api_client, db_session):
        other = await create_user(db_session, email="other-split-2@example.com")
        foreign_budget = await create_budget(db_session, other)
        foreign_account = await create_account(db_session, foreign_budget, "Theirs")
        txn = await create_transaction(
            db_session, foreign_budget, foreign_account, "-100.00", TXN_DATE
        )
        resp = await api_client.post(
            f"/api/v1/transactions/{txn.id}/split",
            params={"budget_id": str(foreign_budget.id)},
            json={"splits": [{"amount": "-100.00"}]},
        )
        assert resp.status_code == 404
