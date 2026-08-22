"""Deleting a budget destroys its full entity graph and nothing else.

The endpoint issues a single DELETE FROM budgets and relies on ON DELETE
CASCADE / SET NULL for everything downstream, so this exercises the whole FK
graph: transactions (plain, split parent+children, transfer pair, sync-linked
pair), assignments, moves, scheduled, targets, views, tags and their
association rows, liabilities with snapshots, reconciliation snapshots,
attachments, matches, and change-log rows.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from igab.db.models import (
    Account,
    Budget,
    BudgetAssignment,
    BudgetMember,
    BudgetMove,
    BudgetView,
    BudgetViewCategory,
    Category,
    CategoryGroup,
    CategoryTarget,
    ChangeLog,
    Liability,
    LiabilityBalanceSnapshot,
    Payee,
    ReconciliationSnapshot,
    ScheduledTransaction,
    Tag,
    Transaction,
    TransactionAttachment,
    TransactionMatch,
    category_tags,
    payee_tags,
)

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_liability,
    create_liability_snapshot,
    create_payee,
    create_scheduled_transaction,
    create_tag,
    create_transaction,
)

TODAY = date.today()
MONTH = TODAY.replace(day=1)


async def _count(session, column, value) -> int:
    return (await session.execute(select(func.count()).where(column == value))).scalar_one()


async def _build_full_budget(db_session, user):
    """One budget touching every table that hangs off the budget graph."""
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group)
    payee = await create_payee(db_session, budget, default_category_id=category.id)
    checking = await create_account(db_session, budget)
    savings = await create_account(db_session, budget, account_type="savings")
    loan = await create_account(db_session, budget, account_type="loan", on_budget=False)

    plain = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, category=category, payee=payee
    )
    parent = await create_transaction(db_session, budget, checking, "-90.00", TODAY, is_split=True)
    await create_transaction(
        db_session, budget, checking, "-40.00", TODAY,
        category=category, parent_transaction_id=parent.id,
    )
    await create_transaction(
        db_session, budget, checking, "-50.00", TODAY,
        category=category, parent_transaction_id=parent.id,
    )
    leg_out = await create_transaction(db_session, budget, checking, "-200.00", TODAY)
    leg_in = await create_transaction(
        db_session, budget, savings, "200.00", TODAY, transfer_id=leg_out.id
    )
    leg_out.transfer_id = leg_in.id
    manual = await create_transaction(db_session, budget, checking, "-15.00", TODAY)
    synced = await create_transaction(
        db_session, budget, checking, "-15.00", TODAY,
        sync_id=f"sync-{budget.id}", sync_source="simplefin",
    )
    synced.linked_transaction_id = manual.id

    await create_budget_assignment(db_session, budget, category, MONTH, "100.00")
    await create_scheduled_transaction(
        db_session, budget, checking, "-20.00", "monthly", TODAY + timedelta(days=10),
        category=category, payee=payee,
    )

    managed = await create_liability(db_session, budget, linked_account_id=loan.id)
    unmanaged = await create_liability(db_session, budget, manual_balance=Decimal("500.00"))
    await create_liability_snapshot(db_session, unmanaged, TODAY, Decimal("500.00"))

    tag = await create_tag(db_session, budget)
    await db_session.execute(
        category_tags.insert().values(category_id=category.id, tag_id=tag.id)
    )
    await db_session.execute(payee_tags.insert().values(payee_id=payee.id, tag_id=tag.id))

    view = BudgetView(budget_id=budget.id, name="View")
    db_session.add(view)
    await db_session.flush()
    db_session.add_all(
        [
            BudgetViewCategory(view_id=view.id, category_id=category.id),
            CategoryTarget(
                category_id=category.id,
                target_type="monthly_funding",
                target_amount=Decimal("100.00"),
            ),
            ReconciliationSnapshot(
                account_id=checking.id,
                statement_balance=Decimal("0"),
                cleared_balance=Decimal("0"),
            ),
            BudgetMove(
                budget_id=budget.id,
                month=MONTH,
                from_category_id=None,
                to_category_id=category.id,
                amount=Decimal("25.00"),
            ),
            TransactionAttachment(
                transaction_id=plain.id,
                filename="r.webp",
                original_filename="r.jpg",
                content_type="image/webp",
                file_size=123,
            ),
            TransactionMatch(
                synced_transaction_id=synced.id,
                manual_transaction_id=manual.id,
                confidence_score=Decimal("0.90"),
            ),
            ChangeLog(
                budget_id=budget.id,
                entity_type="transaction",
                entity_id=plain.id,
                action="create",
                after={"amount": "-50.00"},
                user_id=user.id,
            ),
        ]
    )
    await db_session.flush()

    return {
        "budget": budget,
        "account_ids": [checking.id, savings.id, loan.id],
        "category_id": category.id,
        "tag_id": tag.id,
        "view_id": view.id,
        "liability_ids": [managed.id, unmanaged.id],
        "transaction_ids": [plain.id, parent.id, leg_out.id, leg_in.id, manual.id, synced.id],
    }


async def test_delete_budget_cascades_full_graph(api_client, db_session):
    owner = api_client.test_user
    doomed = await _build_full_budget(db_session, owner)
    survivor = await _build_full_budget(db_session, owner)
    budget_id = doomed["budget"].id

    resp = await api_client.delete(f"/api/v1/budgets/{budget_id}")
    assert resp.status_code == 204

    # Budget-scoped tables: nothing left for the deleted budget
    for column in [
        Account.budget_id,
        Payee.budget_id,
        CategoryGroup.budget_id,
        Category.budget_id,
        Transaction.budget_id,
        BudgetAssignment.budget_id,
        BudgetMove.budget_id,
        ScheduledTransaction.budget_id,
        Tag.budget_id,
        Liability.budget_id,
        BudgetView.budget_id,
        ChangeLog.budget_id,
        BudgetMember.budget_id,
    ]:
        assert await _count(db_session, column, budget_id) == 0, str(column)
    assert await _count(db_session, Budget.id, budget_id) == 0

    # Child tables reached only through their parents
    assert await _count(db_session, CategoryTarget.category_id, doomed["category_id"]) == 0
    assert await _count(db_session, BudgetViewCategory.view_id, doomed["view_id"]) == 0
    assert await _count(db_session, category_tags.c.tag_id, doomed["tag_id"]) == 0
    assert await _count(db_session, payee_tags.c.tag_id, doomed["tag_id"]) == 0
    for liability_id in doomed["liability_ids"]:
        assert await _count(db_session, LiabilityBalanceSnapshot.liability_id, liability_id) == 0
    for account_id in doomed["account_ids"]:
        assert await _count(db_session, ReconciliationSnapshot.account_id, account_id) == 0
    for txn_id in doomed["transaction_ids"]:
        assert await _count(db_session, TransactionAttachment.transaction_id, txn_id) == 0
        assert await _count(db_session, TransactionMatch.synced_transaction_id, txn_id) == 0
        assert await _count(db_session, TransactionMatch.manual_transaction_id, txn_id) == 0

    # The sibling budget is untouched
    sid = survivor["budget"].id
    assert await _count(db_session, Budget.id, sid) == 1
    assert await _count(db_session, Account.budget_id, sid) == 3
    assert await _count(db_session, Transaction.budget_id, sid) == 8
    assert await _count(db_session, Liability.budget_id, sid) == 2
    assert await _count(db_session, Tag.budget_id, sid) == 1
    assert await _count(db_session, category_tags.c.tag_id, survivor["tag_id"]) == 1
    assert await _count(db_session, BudgetViewCategory.view_id, survivor["view_id"]) == 1
    assert await _count(db_session, CategoryTarget.category_id, survivor["category_id"]) == 1
