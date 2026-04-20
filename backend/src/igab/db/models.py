import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
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
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="budgets")
    accounts: Mapped[list["Account"]] = relationship(back_populates="budget")
    category_groups: Mapped[list["CategoryGroup"]] = relationship(back_populates="budget")
    categories: Mapped[list["Category"]] = relationship(back_populates="budget")
    payees: Mapped[list["Payee"]] = relationship(back_populates="budget")
    views: Mapped[list["BudgetView"]] = relationship(back_populates="budget")


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
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    simplefin_account_id: Mapped[str | None] = mapped_column(String(255))
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
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    budget: Mapped["Budget"] = relationship(back_populates="payees")
    default_category: Mapped["Category | None"] = relationship(
        foreign_keys=[default_category_id]
    )
    transfer_account: Mapped["Account | None"] = relationship(
        foreign_keys=[transfer_account_id]
    )


# ─── Category Groups ──────────────────────────────────────────────────────────


class CategoryGroup(Base):
    __tablename__ = "category_groups"
    __table_args__ = (
        UniqueConstraint("budget_id", "name", name="uq_category_group_budget_name"),
    )

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
    __table_args__ = (
        UniqueConstraint("category_group_id", "name", name="uq_category_group_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    category_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("category_groups.id", ondelete="CASCADE"), nullable=False
    )
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # For CC payment categories — links to the credit card account
    linked_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
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
    assignments: Mapped[list["BudgetAssignment"]] = relationship(back_populates="category")
    target: Mapped["CategoryTarget | None"] = relationship(
        back_populates="category", uselist=False
    )


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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
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
    # Paired transfer link
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL")
    )
    # Split parent
    parent_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE")
    )
    is_split: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Import deduplication
    import_id: Mapped[str | None] = mapped_column(String(255))
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    scheduled_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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


# ─── Budget Assignments ───────────────────────────────────────────────────────


class BudgetAssignment(Base):
    __tablename__ = "budget_assignments"
    __table_args__ = (UniqueConstraint("category_id", "month", name="uq_assignment_category_month"),)

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
    __table_args__ = (
        UniqueConstraint("budget_id", "name", name="uq_budget_view_budget_name"),
    )

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
    __table_args__ = (
        UniqueConstraint("view_id", "category_id", name="uq_view_category"),
    )

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
