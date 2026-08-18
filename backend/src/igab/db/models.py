import uuid
from datetime import date, datetime, time
from datetime import date as _PyDate  # un-shadowable alias for class-body annotations
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ─── Users ────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    budgets: Mapped[list["Budget"]] = relationship(back_populates="user")


# ─── Budgets ──────────────────────────────────────────────────────────────────


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_budget_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    number_format: Mapped[str] = mapped_column(String(20), default="comma_dot", nullable=False)
    date_format: Mapped[str] = mapped_column(String(10), default="mdy", nullable=False)
    time_format: Mapped[str] = mapped_column(String(5), default="12h", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="budgets")
    accounts: Mapped[list["Account"]] = relationship(back_populates="budget", passive_deletes=True)
    category_groups: Mapped[list["CategoryGroup"]] = relationship(
        back_populates="budget", passive_deletes=True
    )
    categories: Mapped[list["Category"]] = relationship(
        back_populates="budget", passive_deletes=True
    )
    payees: Mapped[list["Payee"]] = relationship(back_populates="budget", passive_deletes=True)
    views: Mapped[list["BudgetView"]] = relationship(back_populates="budget", passive_deletes=True)


# ─── Accounts ─────────────────────────────────────────────────────────────────


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("budget_id", "name", name="uq_account_budget_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    on_budget: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # For tracking (off-budget) accounts: 'asset' or 'liability'. Null for on-budget.
    classification: Mapped[str | None] = mapped_column(String(20))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    simplefin_account_id: Mapped[str | None] = mapped_column(String(255))
    simplefin_account_name: Mapped[str | None] = mapped_column(String(255))
    simplefin_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_sync_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_simplefin_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    simplefin_balance: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reconciled_balance: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    budget: Mapped["Budget"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account", foreign_keys="Transaction.account_id"
    )
    linked_category: Mapped["Category | None"] = relationship(
        back_populates="linked_account", foreign_keys="Category.linked_account_id"
    )


# ─── Payees ───────────────────────────────────────────────────────────────────


class Payee(Base):
    __tablename__ = "payees"
    __table_args__ = (UniqueConstraint("budget_id", "name", name="uq_payee_budget_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    transfer_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    mapping_samples: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Regex applied to incoming raw payee names; a match assigns the transaction
    # to this payee before fuzzy matching runs.
    match_pattern: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    budget: Mapped["Budget"] = relationship(back_populates="payees")
    default_category: Mapped["Category | None"] = relationship(foreign_keys=[default_category_id])
    transfer_account: Mapped["Account | None"] = relationship(foreign_keys=[transfer_account_id])
    tags: Mapped[list["Tag"]] = relationship(secondary="payee_tags", back_populates="payees")


# ─── Category Groups ──────────────────────────────────────────────────────────


class CategoryGroup(Base):
    __tablename__ = "category_groups"
    __table_args__ = (UniqueConstraint("budget_id", "name", name="uq_category_group_budget_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    budget: Mapped["Budget"] = relationship(back_populates="category_groups")
    categories: Mapped[list["Category"]] = relationship(
        back_populates="group", order_by="Category.sort_order"
    )


# ─── Categories ───────────────────────────────────────────────────────────────


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("category_group_id", "name", name="uq_category_group_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    category_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("category_groups.id", ondelete="CASCADE"), nullable=False
    )
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Display-only annotation shown after the name (e.g. a funding reminder
    # like "$457/mo") — keeps decorations out of the name itself so AI
    # category matching and search see clean names.
    subtitle: Mapped[str | None] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # For CC payment categories — links to the credit card account
    linked_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    # For liability payment categories — this category's outflows feed the
    # liability's payment history. Mutually exclusive with linked_account_id
    # (service-layer enforced, not a DB constraint).
    linked_liability_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("liabilities.id", ondelete="SET NULL")
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    group: Mapped["CategoryGroup"] = relationship(back_populates="categories")
    budget: Mapped["Budget"] = relationship(back_populates="categories")
    linked_account: Mapped["Account | None"] = relationship(
        back_populates="linked_category", foreign_keys=[linked_account_id]
    )
    linked_liability: Mapped["Liability | None"] = relationship(
        back_populates="linked_category", foreign_keys=[linked_liability_id]
    )
    assignments: Mapped[list["BudgetAssignment"]] = relationship(back_populates="category")
    target: Mapped["CategoryTarget | None"] = relationship(back_populates="category", uselist=False)
    tags: Mapped[list["Tag"]] = relationship(secondary="category_tags", back_populates="categories")


# ─── Category Targets ─────────────────────────────────────────────────────────


class CategoryTarget(Base):
    __tablename__ = "category_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    repeat_frequency: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    category: Mapped["Category"] = relationship(back_populates="target")


# ─── Transactions ─────────────────────────────────────────────────────────────


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        # DB-level dedup backstop: at most one LIVE row per bank/import identity.
        # Soft-deleted rows are excluded so links can be re-made after deletes.
        Index(
            "uq_transactions_account_sync_id",
            "account_id",
            "sync_id",
            unique=True,
            postgresql_where=text("sync_id IS NOT NULL AND NOT is_deleted"),
        ),
        Index(
            "uq_transactions_account_import_id",
            "account_id",
            "import_id",
            unique=True,
            postgresql_where=text("import_id IS NOT NULL AND NOT is_deleted"),
        ),
        # Nearby-payee suggestions scan only located rows
        Index(
            "ix_transactions_budget_location",
            "budget_id",
            postgresql_where=text("latitude IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)  # type: ignore[reportGeneralTypeIssues]
    # When bank data overwrites `date` (posting, match linking), the prior
    # user-entered date is preserved here for display as provenance metadata.
    # _PyDate alias: the `date` name is shadowed by the column above.
    entered_date: Mapped[_PyDate | None] = mapped_column(Date, nullable=True)
    # The bank's posted date for synced/matched rows. `date` stays the user's
    # ledger date (budget months follow it); this is display-only provenance.
    bank_posted_date: Mapped[_PyDate | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    payee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payees.id", ondelete="SET NULL")
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    memo: Mapped[str | None] = mapped_column(Text)
    cleared: Mapped[str] = mapped_column(String(20), default="uncleared", nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Where the transaction was entered (mobile quick-add, opt-in). Coordinates
    # are not money: float64 error at Earth scale is far below GPS accuracy,
    # and they never enter any amount computation.
    latitude: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    # Paired transfer link
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL")
    )
    # Split parent
    parent_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE")
    )
    is_split: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Import deduplication (CSV/YNAB file imports)
    import_id: Mapped[str | None] = mapped_column(String(255))
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    import_description: Mapped[str | None] = mapped_column(Text)
    # Bank sync deduplication (SimpleFIN, future: Plaid, etc.)
    sync_id: Mapped[str | None] = mapped_column(String(255))
    sync_source: Mapped[str | None] = mapped_column(String(50))
    # AI provenance: 'ai_receipt' | 'ai_nl'. NULL for manual/import/sync rows
    # (those are already distinguishable via import_id / sync_source).
    created_via: Mapped[str | None] = mapped_column(String(20))
    scheduled_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # SimpleFIN match link
    linked_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL")
    )
    link_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    has_sync_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    account: Mapped["Account"] = relationship(
        back_populates="transactions", foreign_keys=[account_id]
    )
    payee: Mapped["Payee | None"] = relationship(foreign_keys=[payee_id])
    category: Mapped["Category | None"] = relationship(foreign_keys=[category_id])
    # Transfer partner
    transfer: Mapped["Transaction | None"] = relationship(
        foreign_keys=[transfer_id], remote_side="Transaction.id"
    )
    # Split children
    splits: Mapped[list["Transaction"]] = relationship(
        foreign_keys=[parent_transaction_id], back_populates="parent"
    )
    parent: Mapped["Transaction | None"] = relationship(
        foreign_keys=[parent_transaction_id], back_populates="splits", remote_side="Transaction.id"
    )
    # SimpleFIN link partner
    linked_transaction: Mapped["Transaction | None"] = relationship(
        foreign_keys=[linked_transaction_id], remote_side="Transaction.id"
    )
    # Attachments (receipts, etc.)
    attachments: Mapped[list["TransactionAttachment"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )


# ─── Budget Assignments ───────────────────────────────────────────────────────


class BudgetAssignment(Base):
    __tablename__ = "budget_assignments"
    __table_args__ = (
        UniqueConstraint("category_id", "month", name="uq_assignment_category_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    assigned: Mapped[Decimal] = mapped_column(Numeric(19, 4), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    category: Mapped["Category"] = relationship(back_populates="assignments")


class BudgetMove(Base):
    """Audit trail of envelope-to-envelope money moves (NULL side = TBA)."""

    __tablename__ = "budget_moves"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    from_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    to_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Change Log (undo/audit) ──────────────────────────────────────────────────


class ChangeLog(Base):
    """Audit log of user-visible mutations, with enough state to undo them.

    `before`/`after` are full JSONB snapshots of the entity's restorable
    fields (create: after only; delete: before only). `batch_id` groups the
    rows of one compound operation — a transfer pair, a split, a merge, an
    import, a bulk action — which is always undone as a unit. `undone_at`
    marks a change as reverted; undo never appends new rows.
    """

    __tablename__ = "change_log"
    __table_args__ = (
        Index("ix_change_log_budget_created", "budget_id", "created_at"),
        Index("ix_change_log_batch", "batch_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    # created_at is the transaction timestamp — identical for every row in a
    # request — so this identity column is the only total order, needed to
    # undo a batch's changes in exact reverse order.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    # transaction | payee | category | category_group | assignment
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # create | update | delete | approve | import | merge
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # manual | import | ai | system
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Category Balance Snapshots (derived cache) ───────────────────────────────


class CategoryMonthSnapshot(Base):
    """Per-(category, month) balance cache derived from transactions and
    assignments — materializes BudgetService's carryover simulation.

    Rows exist only for months where the category has assignments or activity.
    `available` is the raw end-of-month value: it may be negative in that
    month, and readers floor it at zero when carrying it into later months.
    Rows are never updated in place — a rebuild replaces the whole budget's
    rows, and validity is signalled solely by the budget's BudgetSnapshotMeta
    row (invalidated by igab.db.invalidation on any relevant write).
    """

    __tablename__ = "category_month_snapshots"
    __table_args__ = (
        UniqueConstraint("category_id", "month", name="uq_snapshot_category_month"),
        Index("ix_snapshot_budget_month", "budget_id", "month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    assigned: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    activity: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    available: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BudgetSnapshotMeta(Base):
    """Presence of a row means the budget's category snapshots are valid."""

    __tablename__ = "budget_snapshot_meta"

    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), primary_key=True
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Scheduled Transactions ───────────────────────────────────────────────────


class ScheduledTransaction(Base):
    __tablename__ = "scheduled_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    payee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payees.id", ondelete="SET NULL")
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    memo: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    second_day_of_month: Mapped[int | None] = mapped_column(Integer)
    auto_create: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    days_before_reminder: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    transfer_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    last_created_date: Mapped[date | None] = mapped_column(Date)
    next_occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ─── Reconciliation Snapshots ─────────────────────────────────────────────────


class ReconciliationSnapshot(Base):
    __tablename__ = "reconciliation_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    reconciled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    statement_balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    cleared_balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), default=0)
    adjustment_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Budget Views ─────────────────────────────────────────────────────────────


class BudgetView(Base):
    __tablename__ = "budget_views"
    __table_args__ = (UniqueConstraint("budget_id", "name", name="uq_budget_view_budget_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    budget: Mapped["Budget"] = relationship(back_populates="views")
    category_selections: Mapped[list["BudgetViewCategory"]] = relationship(
        back_populates="view", cascade="all, delete-orphan"
    )


class BudgetViewCategory(Base):
    __tablename__ = "budget_view_categories"
    __table_args__ = (UniqueConstraint("view_id", "category_id", name="uq_view_category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    view_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_views.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )

    view: Mapped["BudgetView"] = relationship(back_populates="category_selections")
    category: Mapped["Category"] = relationship()


# ─── App Settings ────────────────────────────────────────────────────────────


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ─── SimpleFIN Connections ────────────────────────────────────────────────────


class SimpleFINConnection(Base):
    __tablename__ = "simplefin_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    access_url_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requests_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_request_date: Mapped[date | None] = mapped_column(Date)
    sync_interval_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    daily_sync_time: Mapped[time | None] = mapped_column(Time)
    global_requests_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    account_requests_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    last_sync_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()


# ─── Import Batches ───────────────────────────────────────────────────────────


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_file_name: Mapped[str | None] = mapped_column(String(255))
    transactions_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transactions_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


# ─── Transaction Matches ──────────────────────────────────────────────────────


class TransactionMatch(Base):
    __tablename__ = "transaction_matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    synced_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    manual_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    synced_transaction: Mapped["Transaction"] = relationship(foreign_keys=[synced_transaction_id])
    manual_transaction: Mapped["Transaction"] = relationship(foreign_keys=[manual_transaction_id])


# ─── Transaction Attachments ─────────────────────────────────────────────────


class TransactionAttachment(Base):
    __tablename__ = "transaction_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    # Path relative to ATTACHMENTS_DIR, recorded at upload time. The on-disk
    # location encodes the transaction date, so it must not be re-derived from
    # txn.date on read — the date may have been edited after upload.
    storage_path: Mapped[str | None] = mapped_column(String(500))
    # sha256 of the bytes as UPLOADED, not as stored — the stored copy is a
    # re-encoded WebP, so hashing it would never match a resubmission of the
    # original file. Detects the same receipt being submitted twice, which on a
    # budgeting app is a double-count, not just clutter. Nullable: rows created
    # before this column existed have no hash and simply never match.
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transaction: Mapped["Transaction"] = relationship(
        back_populates="attachments", foreign_keys=[transaction_id]
    )


# ─── AI Jobs ─────────────────────────────────────────────────────────────────


class AIJob(Base):
    """Persistent queue + permanent audit log for AI-assisted entry.

    Review semantics live on the created transaction (approved=False), not on
    job status: 'done' means the job produced its output. A receipt job that
    exhausts retries still creates a $0 stub transaction with the image
    attached, then lands in 'error' with transaction_id set.
    """

    __tablename__ = "ai_jobs"
    __table_args__ = (
        Index("ix_ai_jobs_budget_status", "budget_id", "status"),
        # Worker pickup scans only claimable rows
        Index(
            "ix_ai_jobs_queue",
            "available_at",
            postgresql_where=text("status = 'queued'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # 'receipt' | 'nl_parse'
    status: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False
    )  # 'queued' | 'processing' | 'done' | 'error'
    # Inputs: {account_id, original_filename, content_type, staged_path,
    # text, client_today}. staged_path is relative to ATTACHMENTS_DIR so
    # queued jobs survive restarts and volume remounts.
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Validated extraction output incl. line_items + suggested_split
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    # Which model processed this job (for audit and reprocessing decisions)
    model: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Retry backoff gate: the worker only claims jobs whose available_at has passed
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL")
    )
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transaction_attachments.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    transaction: Mapped["Transaction | None"] = relationship(foreign_keys=[transaction_id])
    attachment: Mapped["TransactionAttachment | None"] = relationship(foreign_keys=[attachment_id])


# ─── Tags ────────────────────────────────────────────────────────────────────


category_tags = Table(
    "category_tags",
    Base.metadata,
    Column(
        "category_id",
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

payee_tags = Table(
    "payee_tags",
    Base.metadata,
    Column(
        "payee_id",
        UUID(as_uuid=True),
        ForeignKey("payees.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("budget_id", "name", name="uq_tag_budget_name"),
        UniqueConstraint("budget_id", "system_key", name="uq_tag_budget_system_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    system_key: Mapped[str | None] = mapped_column(String(30), nullable=True)
    color_slot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    budget: Mapped["Budget"] = relationship()
    categories: Mapped[list["Category"]] = relationship(
        secondary=category_tags, back_populates="tags"
    )
    payees: Mapped[list["Payee"]] = relationship(secondary=payee_tags, back_populates="tags")


# ─── Liabilities ─────────────────────────────────────────────────────────────


class Liability(Base):
    """A first-class liability, independent of whether a full Account exists.

    linked_account_id set  ⇒ "managed": balance and payment history derive
    from that account's ledger.
    linked_account_id null ⇒ "unmanaged": balance is manual_balance; payments
    come from a linked budget category (Category.linked_liability_id) or manual
    balance snapshots.
    """

    __tablename__ = "liabilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 'mortgage'|'auto'|'student'|'personal'|'credit_card'|'medical'|'other'
    liability_type: Mapped[str] = mapped_column(String(30), nullable=False)
    linked_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), unique=True
    )
    # Authoritative only when linked_account_id IS NULL
    manual_balance: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    # Annual percent, e.g. 6.2500
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    # Contractual payment — drives the baseline schedule
    minimum_payment: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    compounding: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    origination_date: Mapped[_PyDate | None] = mapped_column(Date)
    original_principal: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    budget: Mapped["Budget"] = relationship()
    linked_account: Mapped["Account | None"] = relationship(foreign_keys=[linked_account_id])
    linked_category: Mapped["Category | None"] = relationship(
        back_populates="linked_liability", foreign_keys="Category.linked_liability_id"
    )
    snapshots: Mapped[list["LiabilityBalanceSnapshot"]] = relationship(
        back_populates="liability", passive_deletes=True, order_by="LiabilityBalanceSnapshot.date"
    )


class LiabilityBalanceSnapshot(Base):
    """Manual balance point for an unmanaged liability — one per day at most."""

    __tablename__ = "liability_balance_snapshots"
    __table_args__ = (UniqueConstraint("liability_id", "date", name="uq_liability_snapshot_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    liability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("liabilities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)  # type: ignore[reportGeneralTypeIssues]
    balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    liability: Mapped["Liability"] = relationship(back_populates="snapshots")
