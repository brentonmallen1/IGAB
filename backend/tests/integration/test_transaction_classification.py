"""The "why is this classified this way?" endpoint.

Phase 2 silently changed what 169 transactions in a real budget count as. A
reclassification the user cannot audit is worse than one they can argue with,
so every row can say which rule decided it and why, in a sentence.
"""

from datetime import date

from igab.domain.activity_class import ActivityClass, ActivityReason

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
)

TODAY = date.today()


async def _setup(db_session, owner):
    budget = await create_budget(db_session, owner)
    return budget, await create_account(db_session, budget, "Checking", on_budget=True)


async def test_explains_ordinary_spending(api_client, db_session):
    budget, checking = await _setup(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    txn = await create_transaction(db_session, budget, checking, "-60.00", TODAY, category=cat)

    resp = await api_client.get(f"/api/v1/transactions/{txn.id}/classification")
    assert resp.status_code == 200
    body = resp.json()
    assert body["activity_class"] == ActivityClass.SPENDING
    assert body["label"] == "Spending"
    assert body["reason"] == ActivityReason.DEFAULT_SPENDING
    assert body["explanation"]


async def test_explains_a_transfer_into_savings(api_client, db_session):
    """The case that changed. A user seeing this drop out of their spending
    report should be able to find out why without reading the source."""
    from igab.repositories.payee_repo import PayeeRepository

    budget, checking = await _setup(db_session, api_client.test_user)
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Savings")
    cat = await create_category(db_session, budget, group, "Investments")
    payee = await PayeeRepository(db_session).find_or_create_transfer(
        budget.id, brokerage.id, brokerage.name
    )
    txn = await create_transaction(
        db_session, budget, checking, "-500.00", TODAY, category=cat, payee=payee
    )

    body = (await api_client.get(f"/api/v1/transactions/{txn.id}/classification")).json()
    assert body["activity_class"] == ActivityClass.SAVINGS
    assert body["label"] == "Savings"
    assert body["reason"] == ActivityReason.TRANSFER_TO_TRACKED_ASSET
    assert "tracked account" in body["explanation"]


async def test_unknown_transaction_is_404(api_client, db_session):
    import uuid

    resp = await api_client.get(f"/api/v1/transactions/{uuid.uuid4()}/classification")
    assert resp.status_code == 404


async def test_another_budget_cannot_be_read(api_client, db_session):
    from .factories import create_user

    other = await create_user(db_session)
    budget, checking = await _setup(db_session, other)
    txn = await create_transaction(db_session, budget, checking, "-10.00", TODAY)

    resp = await api_client.get(f"/api/v1/transactions/{txn.id}/classification")
    assert resp.status_code in (403, 404), "must not leak another budget's rows"


async def test_every_class_has_a_label():
    from igab.domain.activity_class import CLASS_LABEL

    for cls in ActivityClass:
        assert CLASS_LABEL.get(cls), f"{cls} has no label"


class TestASplitSaysWhatTheTimelineSays:
    """A split parent carries no category, so the classifier falls through to
    SPENDING on it. The Timeline rolled the legs up and this endpoint did not:
    an all-savings split was a Savings dot on the Timeline and "ordinary
    spending from a budget account" in the editor for the same row. Both read
    `activity_class.rolled_up_classes` now, and each case below asks both."""

    @staticmethod
    async def _split(db_session, owner, second_leg_saves: bool):
        from datetime import timedelta
        from decimal import Decimal

        from igab.repositories.tag_repo import TagRepository, seed_system_tags
        from igab.services.transaction_service import TransactionCreate

        from .factories import make_services

        budget, checking = await _setup(db_session, owner)
        goals = await create_category_group(db_session, budget, "Goals")
        fund = await create_category(db_session, budget, goals, "Emergency Fund")
        everyday = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, everyday, "Groceries")
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        savings_tag = await tags.get_system_tag(budget.id, "savings")
        await tags.set_category_tags(fund.id, [savings_tag.id])

        when = TODAY - timedelta(days=1)
        second = fund if second_leg_saves else groceries
        parent = await make_services(db_session).transactions.create_split(
            budget.id,
            TransactionCreate(
                account_id=checking.id, date=when, amount=Decimal("-900.00"), cleared="cleared"
            ),
            [
                TransactionCreate(
                    account_id=checking.id,
                    date=when,
                    amount=Decimal("-600.00"),
                    category_id=fund.id,
                ),
                TransactionCreate(
                    account_id=checking.id,
                    date=when,
                    amount=Decimal("-300.00"),
                    category_id=second.id,
                ),
            ],
        )
        await db_session.commit()
        return budget, parent, when

    @staticmethod
    async def _both(api_client, db_session, budget, parent, when):
        from igab.services.report_service import ReportService

        editor = (await api_client.get(f"/api/v1/transactions/{parent.id}/classification")).json()
        (timeline,) = await ReportService(db_session).large_transactions(budget.id, when, when)
        return editor, timeline

    async def test_an_all_savings_split_is_savings_in_both(self, api_client, db_session):
        budget, parent, when = await self._split(db_session, api_client.test_user, True)
        editor, timeline = await self._both(api_client, db_session, budget, parent, when)

        assert editor["activity_class"] == timeline["activity_class"] == ActivityClass.SAVINGS
        assert editor["label"] == timeline["activity_label"] == "Savings"
        assert editor["reason"] == "split_legs_agree"
        assert editor["explanation"] == "every line of the split counts this way"

    async def test_a_mixed_split_is_split_in_both(self, api_client, db_session):
        budget, parent, when = await self._split(db_session, api_client.test_user, False)
        editor, timeline = await self._both(api_client, db_session, budget, parent, when)

        assert editor["activity_class"] is None
        assert timeline["activity_class"] is None
        assert editor["label"] == timeline["activity_label"] == "Split"
        assert editor["reason"] == "split_legs_differ"
