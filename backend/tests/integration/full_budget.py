"""One budget that touches every table in its own entity graph.

Shared because more than one test needs the same thing: the delete test proves
the graph goes away, and the snapshot round-trip proves it survives a trip
through a file. Both are worthless against a budget that only populates the
tables someone remembered.

``test_budget_scope.py`` decides which tables exist; ``budget_rows.row_counts``
counts them; this builds them. The pairing is the point — when a new table
lands, the guard names it and the count fails at zero, instead of everything
passing while the table is quietly missed.

Fictional data only: this repository is public (CLAUDE.md).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    AccountType,
    AIJob,
    Budget,
    BudgetFilter,
    BudgetFilterCategory,
    BudgetMove,
    BudgetSnapshotMeta,
    BudgetView,
    BudgetViewGroup,
    BudgetViewPlacement,
    CategoryMonthSnapshot,
    CategoryTarget,
    ChangeLog,
    GuideBinding,
    GuideState,
    ImportBatch,
    ReconciliationSnapshot,
    TransactionAttachment,
    TransactionMatch,
    User,
    WishlistItem,
    WishlistProject,
    category_tags,
    payee_tags,
)
from igab.repositories.tag_repo import seed_system_tags

from .factories import (
    add_budget_member,
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
    create_user,
)

TODAY = date.today()
MONTH = TODAY.replace(day=1)


@dataclass
class FullBudget:
    """Handles into a built budget, for the assertions that need a specific
    row rather than a count."""

    budget: Budget
    owner: User
    member: User
    account_ids: list[UUID] = field(default_factory=list)
    category_id: UUID | None = None
    group_id: UUID | None = None
    payee_id: UUID | None = None
    tag_id: UUID | None = None
    filter_id: UUID | None = None
    view_id: UUID | None = None
    liability_ids: list[UUID] = field(default_factory=list)
    transaction_ids: list[UUID] = field(default_factory=list)
    scheduled_id: UUID | None = None
    import_batch_id: UUID | None = None
    custom_account_type_id: UUID | None = None

    @property
    def id(self) -> UUID:
        return self.budget.id


async def mark_snapshot_cache_valid(session: AsyncSession, budget_id: UUID) -> None:
    """Give the budget its ``budget_snapshot_meta`` row — the one table the
    fixture cannot fill for itself.

    ``igab.db.invalidation`` deletes **every** meta row, for every budget, on
    any write touching a transaction, assignment or category. Presence of the
    row is the sole "this cache is valid" signal, so building a second budget
    wipes the first one's. Call this after every other write is done, which is
    also when production writes it: at the end of a rebuild.
    """
    session.add(BudgetSnapshotMeta(budget_id=budget_id))
    await session.flush()


async def build_full_budget(session: AsyncSession, owner: User) -> FullBudget:
    """Populate every table a budget owns, directly or through a parent."""
    budget = await create_budget(session, owner)
    # create_budget seeds the account-type registry but not the system tags;
    # every real creation path seeds both, and a fixture that skips them
    # cannot tell "the importer seeded these" from "the copy grew rows".
    await seed_system_tags(session, budget.id)

    # A second member: authorization rows are budget-owned, and a restore that
    # loses them locks someone out of their own budget.
    member = await create_user(session)
    await add_budget_member(session, budget, member)

    # A custom account type — the system rows are seeded for every budget, so
    # only a custom one proves the registry itself travels.
    custom_type = AccountType(
        budget_id=budget.id,
        key="crypto_wallet",
        label="Crypto Wallet",
        classification="asset",
        default_on_budget=False,
        is_system=False,
        sort_order=90,
    )
    session.add(custom_type)
    await session.flush()

    group = await create_category_group(session, budget)
    category = await create_category(session, budget, group)
    payee = await create_payee(session, budget, default_category_id=category.id)
    checking = await create_account(session, budget)
    savings = await create_account(session, budget, account_type="savings")
    loan = await create_account(session, budget, account_type="loan", on_budget=False)

    plain = await create_transaction(
        session, budget, checking, "-50.00", TODAY, category=category, payee=payee
    )
    parent = await create_transaction(session, budget, checking, "-90.00", TODAY, is_split=True)
    await create_transaction(
        session, budget, checking, "-40.00", TODAY,
        category=category, parent_transaction_id=parent.id,
    )
    await create_transaction(
        session, budget, checking, "-50.00", TODAY,
        category=category, parent_transaction_id=parent.id,
    )
    leg_out = await create_transaction(session, budget, checking, "-200.00", TODAY)
    leg_in = await create_transaction(
        session, budget, savings, "200.00", TODAY, transfer_id=leg_out.id
    )
    leg_out.transfer_id = leg_in.id
    manual = await create_transaction(session, budget, checking, "-15.00", TODAY)
    synced = await create_transaction(
        session, budget, checking, "-15.00", TODAY,
        sync_id=f"sync-{budget.id}", sync_source="simplefin",
    )
    synced.linked_transaction_id = manual.id

    await create_budget_assignment(session, budget, category, MONTH, "100.00")
    scheduled = await create_scheduled_transaction(
        session, budget, checking, "-20.00", "monthly", TODAY + timedelta(days=10),
        category=category, payee=payee,
    )

    # The two id columns with no foreign key to declare them. Both are carried
    # on a real transaction so a copy that forgets to remap them is visible in
    # the round-trip rather than only in budget_scope's declarations.
    batch = ImportBatch(
        budget_id=budget.id,
        source="csv",
        source_file_name="statement.csv",
        transactions_imported=1,
    )
    session.add(batch)
    await session.flush()
    imported = await create_transaction(
        session, budget, checking, "-31.75", TODAY, category=category
    )
    imported.import_batch_id = batch.id
    from_schedule = await create_transaction(
        session, budget, checking, "-20.00", TODAY, category=category
    )
    from_schedule.scheduled_transaction_id = scheduled.id

    managed = await create_liability(session, budget, linked_account_id=loan.id)
    unmanaged = await create_liability(session, budget, manual_balance=Decimal("500.00"))
    await create_liability_snapshot(session, unmanaged, TODAY, Decimal("500.00"))

    tag = await create_tag(session, budget)
    await session.execute(category_tags.insert().values(category_id=category.id, tag_id=tag.id))
    await session.execute(payee_tags.insert().values(payee_id=payee.id, tag_id=tag.id))

    saved_filter = BudgetFilter(budget_id=budget.id, name="Filter")
    session.add(saved_filter)
    view = BudgetView(budget_id=budget.id, name="View")
    session.add(view)
    await session.flush()
    view_group = BudgetViewGroup(view_id=view.id, name="Need")
    session.add(view_group)
    project = WishlistProject(budget_id=budget.id, name="Kitchen", category_id=category.id)
    session.add(project)
    attachment = TransactionAttachment(
        transaction_id=plain.id,
        filename="r.webp",
        original_filename="r.jpg",
        content_type="image/webp",
        file_size=123,
    )
    session.add(attachment)
    await session.flush()

    session.add_all(
        [
            BudgetFilterCategory(filter_id=saved_filter.id, category_id=category.id),
            BudgetViewPlacement(view_id=view.id, category_id=category.id, group_id=view_group.id),
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
                user_id=owner.id,
            ),
            WishlistItem(
                budget_id=budget.id,
                project_id=project.id,
                name="Range hood",
                cost=Decimal("340.00"),
                category_id=category.id,
                priority=1,
            ),
            AIJob(
                budget_id=budget.id,
                kind="categorize",
                payload={"transaction_id": str(plain.id)},
                transaction_id=plain.id,
                attachment_id=attachment.id,
            ),
            GuideState(budget_id=budget.id, key="roadmap_position", value={"step": 2}),
            # One binding per mode: the precedence rules in guide/bindings.py
            # only mean anything if all four survive a copy.
            GuideBinding(
                budget_id=budget.id,
                concept_key="emergency_fund",
                mode="manual",
                entity_type="category",
                entity_id=category.id,
            ),
            GuideBinding(
                budget_id=budget.id,
                concept_key="retirement",
                mode="external",
                amount=Decimal("1200.00"),
                as_of=TODAY,
            ),
            GuideBinding(budget_id=budget.id, concept_key="will", mode="dismissed"),
            GuideBinding(
                budget_id=budget.id, concept_key="insurance", mode="answer", answer=True
            ),
            # A derived cache, but a budget-owned row like any other: a delete
            # must take it, and a restore must not leave a stale one
            # describing a budget that no longer looks like that.
            CategoryMonthSnapshot(
                budget_id=budget.id,
                category_id=category.id,
                month=MONTH,
                assigned=Decimal("100.00"),
                activity=Decimal("-140.00"),
                available=Decimal("-40.00"),
            ),
        ]
    )
    await session.flush()

    # A soft-deleted row of every soft-deleting kind. Undo restores these, so
    # a snapshot that quietly drops them loses history the app promises.
    deleted_account = await create_account(
        session, budget, "Closed Card", account_type="credit_card"
    )
    deleted_account.is_deleted = True
    deleted_group = await create_category_group(session, budget, "Retired Group")
    deleted_group.is_deleted = True
    deleted_category = await create_category(session, budget, deleted_group, "Retired")
    deleted_category.is_deleted = True
    deleted_payee = await create_payee(session, budget, "Old Payee")
    deleted_payee.is_deleted = True
    deleted_txn = await create_transaction(
        session, budget, checking, "-9.99", TODAY, is_deleted=True
    )
    deleted_scheduled = await create_scheduled_transaction(
        session, budget, checking, "-5.00", "monthly", TODAY + timedelta(days=20)
    )
    deleted_scheduled.is_deleted = True
    deleted_tag = await create_tag(session, budget, "Retired Tag")
    deleted_tag.is_deleted = True
    deleted_liability = await create_liability(session, budget, manual_balance=Decimal("10.00"))
    deleted_liability.is_deleted = True
    deleted_filter = BudgetFilter(budget_id=budget.id, name="Old Filter", is_deleted=True)
    deleted_view = BudgetView(budget_id=budget.id, name="Old View", is_deleted=True)
    session.add_all([deleted_filter, deleted_view])
    await session.flush()

    return FullBudget(
        budget=budget,
        owner=owner,
        member=member,
        account_ids=[checking.id, savings.id, loan.id, deleted_account.id],
        category_id=category.id,
        group_id=group.id,
        payee_id=payee.id,
        tag_id=tag.id,
        filter_id=saved_filter.id,
        view_id=view.id,
        liability_ids=[managed.id, unmanaged.id, deleted_liability.id],
        transaction_ids=[
            plain.id, parent.id, leg_out.id, leg_in.id, manual.id, synced.id,
            imported.id, from_schedule.id, deleted_txn.id,
        ],
        scheduled_id=scheduled.id,
        import_batch_id=batch.id,
        custom_account_type_id=custom_type.id,
    )
