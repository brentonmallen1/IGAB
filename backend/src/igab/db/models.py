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
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    query_expression,
    relationship,
)


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
    # Gates user management and global-surface writes (settings, backups).
    # sync_admin keeps the ADMIN_EMAIL user flagged at every boot.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    filters: Mapped[list["BudgetFilter"]] = relationship(
        back_populates="budget", passive_deletes=True
    )


class BudgetMember(Base):
    """Who can use a budget, and at what level.

    Authorization source of truth: every *Access guard in dependencies.py
    resolves through this table. Budget.user_id remains the creator-of-record
    (it anchors uq_budget_user_name and cascade semantics) but grants no
    access by itself — creation inserts an 'owner' row here.

    Roles: 'owner' (delete budget, manage members) and 'member' (full
    day-to-day use). A budget always has at least one owner — the API refuses
    to remove the last one.
    """

    __tablename__ = "budget_members"
    __table_args__ = (Index("ix_budget_members_user", "user_id"),)

    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # 'owner' | 'member'
    role: Mapped[str] = mapped_column(String(10), default="member", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Accounts ─────────────────────────────────────────────────────────────────


class AccountType(Base):
    """Per-budget registry of account types.

    Built-in rows (is_system=True) are seeded for every budget from
    igab.domain.account_types; users add custom rows. The row is the source of
    truth for label, asset/liability classification, and default budget
    participation. accounts.account_type (the row's key) and
    accounts.classification are denormalized mirrors kept join-free for
    sidebar/report queries — igab.services.account_type_service is their only
    writer.
    """

    __tablename__ = "account_types"
    __table_args__ = (UniqueConstraint("budget_id", "key", name="uq_account_type_budget_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    # 'asset' | 'liability'
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    default_on_budget: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # User-facing explanation of what the type means and implies
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("budget_id", "name", name="uq_account_budget_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # FK default (NO ACTION) checks at statement end, so a budget delete may
    # cascade to accounts and account_types in either order; RESTRICT would
    # fail mid-cascade. Custom-type deletion is guarded at the API layer.
    account_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_types.id"), nullable=False, index=True
    )
    # Mirror of the type row's key — kept join-free for queries and the API
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    on_budget: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Mirror of the type row's classification ('asset' | 'liability') — set for
    # every account, on-budget included. NOT NULL since b8c3e5a71f42: a null
    # here reads as UNKNOWN in SQL, which makes both `= 'liability'` and its
    # negation decline, silently disabling every rule that branches on it.
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
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
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    transfer_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), index=True
    )
    # Raw bank names that should map to this payee, as a list — a bank name
    # may itself contain a comma ("… MALLEN, BRENTON"), which is why this is
    # not a delimited string. Trimmed, unique ignoring case; see
    # igab.domain.payee_names.dedupe_samples.
    mapping_samples: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
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
    __table_args__ = (
        UniqueConstraint("budget_id", "name", name="uq_category_group_budget_name"),
        UniqueConstraint("budget_id", "system_key", name="uq_category_group_budget_system_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: A group the app seeds and protects by key, the way system tags are —
    #: `wishlist` is the only one. NOT `is_system`: that flag means the Income
    #: arrangement (not assignable, outside To Be Assigned). A keyed group is
    #: an ordinary envelope group the user cannot rename or delete, only hide.
    system_key: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    budget: Mapped["Budget"] = relationship(back_populates="category_groups")
    categories: Mapped[list["Category"]] = relationship(
        back_populates="group", order_by="[Category.sort_order, Category.name]"
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
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
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
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), index=True
    )
    # For liability payment categories — this category's outflows feed the
    # liability's payment history. Mutually exclusive with linked_account_id
    # (service-layer enforced, not a DB constraint).
    linked_liability_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("liabilities.id", ondelete="SET NULL"), index=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    #: May money be budgeted or moved into this envelope? Not a column, and
    #: none could be: it reads the *group's* is_system and is_hidden, which
    #: change without this row being touched. Populated only by
    #: `CategoryRepository.with_eligibility`; left alone it reads None.
    is_assignable: Mapped[bool] = query_expression()
    #: May a transaction leg be filed here? Differs from is_assignable on
    #: system groups — income is filed into one — and on linked categories.
    is_categorizable: Mapped[bool] = query_expression()

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
        # Serves the register's per-account date-ordered scans; its leading
        # account_id also covers the FK's referential-integrity checks
        Index("ix_transactions_account_date", "account_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)  # type: ignore[reportGeneralTypeIssues]
    # When bank data overwrites `date` (posting, match linking), the prior
    # user-entered date is preserved here for display as provenance metadata.
    # _PyDate alias: the `date` name is shadowed by the column above.
    entered_date: Mapped[_PyDate | None] = mapped_column(Date, nullable=True)
    # When the bank's posted amount overwrites `amount` — a pending row
    # posting, or an accepted amount-change review — the prior amount is
    # preserved here once. The same provenance pattern as entered_date, and
    # what lets the bank-record tooltip say "amount updated from X".
    entered_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    # The bank's posted date for synced/matched rows. `date` stays the user's
    # ledger date (budget months follow it); this is display-only provenance.
    bank_posted_date: Mapped[_PyDate | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    # The bank's own amount and payee string, kept verbatim as provenance.
    # `amount` and `payee_id` are the user's ledger values and may be edited
    # or (on the pending→posted path) overwritten by the bank; these are not.
    bank_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    bank_payee: Mapped[str | None] = mapped_column(Text, nullable=True)
    payee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payees.id", ondelete="SET NULL"), index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    # The category this row was filed in before that category was deleted, kept
    # as provenance the way `entered_date` and `bank_payee` are.
    #
    # DISPLAY AND UNDO ONLY — provenance, never a category. Nothing may
    # aggregate, filter or count on these: clearing `category_id` is precisely
    # the statement that this row is uncategorized, and a reader that treats
    # prior_* as a category recreates the bug they exist to replace (a
    # transaction that renders as filed, is counted as filed, and points at a
    # category no longer in the budget).
    #
    # Both, not just the name: the id is the identity — delete "Groceries",
    # recreate it, delete it again, and the two are distinct — while the name
    # is frozen here because the soft-deleted row it came from can be renamed
    # (retroactively rewriting history) or hard-deleted with the budget.
    prior_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    prior_category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), index=True
    )
    # Split parent
    parent_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    is_split: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Import deduplication (CSV/YNAB file imports)
    import_id: Mapped[str | None] = mapped_column(String(255))
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    import_description: Mapped[str | None] = mapped_column(Text)
    # Bank sync deduplication (SimpleFIN, future: Plaid, etc.)
    sync_id: Mapped[str | None] = mapped_column(String(255))
    sync_source: Mapped[str | None] = mapped_column(String(50))
    # Where the row came from: 'manual' | 'import' | 'sync' | 'scheduled' |
    # 'ai_receipt' | 'ai_nl'. Set by TransactionService.create (and the bulk
    # importers), never accepted from a client. NULL means "unknown" — rows
    # written before this was stamped. It cannot be backfilled: a hand-typed
    # row the bank later matched carries sync_source too, and would be
    # misfiled as a sync row. This is what lets the register show that a row
    # the bank matched was entered by the user first.
    created_via: Mapped[str | None] = mapped_column(String(20))
    # The schedule this row was entered from (Enter now, or the scheduler's
    # auto-create). Served, so the row can say so; nothing else reads it.
    scheduled_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # SimpleFIN match link
    linked_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), index=True
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

    #: Does the user still have to file this row? **Not a column** — no value is
    #: stored, and none could be: the answer depends on the counterpart
    #: account's `on_budget`, which changes without this row being touched.
    #:
    #: It exists so the rule has exactly one implementation. The register used
    #: to re-derive it in TypeScript, and the two spent months disagreeing —
    #: a badge counting 3 above a list drawing 930. The rule is
    #: `NEEDS_CATEGORY` (repositories/txn_filters.py) and nothing else may
    #: restate it; clients read this field.
    #:
    #: Populated only by queries that ask, via
    #: `TransactionRepository.with_computed`. Left alone it reads `None`,
    #: which `TransactionResponse` rejects — a path that forgets fails loudly
    #: instead of quietly reporting everything as filed.
    needs_category: Mapped[bool] = query_expression()

    #: The account on the other side of this transfer, or None for a plain
    #: transaction. The rule is `COUNTERPART_ACCOUNT_ID`
    #: (repositories/txn_filters.py): the linked partner's account when the
    #: link exists, else the account the transfer payee names — the client
    #: cannot compute this (a linked leg's payee can be null or wrong, and the
    #: partner row may not be loaded), so the server serves it.
    #:
    #: Not a column: it is derived state (transfer_id + payee), and a stored
    #: copy would go stale the moment either side is retargeted.
    #: Populated by `TransactionRepository.with_computed`, alongside
    #: needs_category. Unlike needs_category, None is a legal value here, so a
    #: path that forgets the loader degrades to "not a transfer" instead of
    #: raising — tests/integration/test_transfer_counterpart.py sweeps every
    #: serializing path for exactly that.
    counterpart_account_id: Mapped[uuid.UUID | None] = query_expression()

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
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
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
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    from_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    to_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True
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
    # Who made the change — NULL for system/AI/scheduler actors. SET NULL on
    # user deletion so history outlives accounts.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
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
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    payee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payees.id", ondelete="SET NULL"), index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    memo: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    second_day_of_month: Mapped[int | None] = mapped_column(Integer)
    auto_create: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    days_before_reminder: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    transfer_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), index=True
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
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reconciled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    statement_balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    cleared_balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), default=0)
    adjustment_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), index=True
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Budget Filters ───────────────────────────────────────────────────────────
#
# A saved subset of categories to narrow the budget grid to. Called "views"
# until it became clear that is all it does: it cannot regroup, reorder or hide.
# The name is now reserved for the feature that does.


class BudgetFilter(Base):
    __tablename__ = "budget_filters"
    __table_args__ = (
        # Unique among LIVE filters only — same soft-delete name-burn as
        # budget_views, fixed the same way.
        Index(
            "uq_budget_filter_budget_name_live",
            "budget_id",
            "name",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
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

    budget: Mapped["Budget"] = relationship(back_populates="filters")
    category_selections: Mapped[list["BudgetFilterCategory"]] = relationship(
        back_populates="filter_", cascade="all, delete-orphan"
    )


class BudgetFilterCategory(Base):
    __tablename__ = "budget_filter_categories"
    __table_args__ = (UniqueConstraint("filter_id", "category_id", name="uq_filter_category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    filter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_filters.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filter_: Mapped["BudgetFilter"] = relationship(back_populates="category_selections")
    category: Mapped["Category"] = relationship()


# ─── Budget Views ─────────────────────────────────────────────────────────────
#
# A different way to look at the same categories. Unlike a BudgetFilter, which
# narrows the set, a view REGROUPS it: the same categories arranged under groups
# the user invents, so "Emergency Fund / Savings / True Expenses / Monthly Bills"
# can also be read as "Need / Want / Save" without cloning the budget.
#
# The default arrangement stays in category_groups. A view never edits it.


# ─── Guide (education & planning) ─────────────────────────────────────────────


class GuideBinding(Base):
    """What the user says counts as a given roadmap concept.

    The Guide asks questions the budget can usually answer for itself — how
    much emergency fund is there, is any debt above 10%. Detection guesses,
    and this table records the user overruling or extending that guess. Rows
    are per budget rather than per user: a shared household budget has one
    emergency fund, and a partner should not see a different roadmap.

    `mode` says how a row participates, in resolution order:

    ``manual``     these specific entities are what counts; detection stops.
    ``external``   money that exists but is not in IGAB — another bank, a
                   workplace 401(k). Additive to any manual rows, because half
                   here and half elsewhere is the ordinary case. `amount` is
                   optional: "I have this covered" is a complete answer, and
                   demanding a figure invites an invented one.
    ``dismissed``  do not track this concept at all. Distinct from external —
                   "stop asking" is not "I have done it".
    ``answer``     a yes/no fact nothing in the budget can supply, such as
                   whether an employer matches contributions.
    ``auto``       reserved; automatic detection stores nothing, so a concept
                   with no rows is automatic by definition.

    Self-reported amounts never leave the Guide. They must not reach net
    worth, the savings-rate report, or any other total — IGAB's ledger is
    derived from transactions, and an unverified number that can move a
    reported balance is how the reports stop being trustworthy.
    """

    __tablename__ = "guide_bindings"
    __table_args__ = (
        UniqueConstraint(
            "budget_id",
            "concept_key",
            "entity_type",
            "entity_id",
            name="uq_guide_binding_concept_entity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Concept slug from igab.guide.concepts — e.g. 'emergency_fund'.
    concept_key: Mapped[str] = mapped_column(String(40), nullable=False)
    #: 'manual' | 'external' | 'dismissed' | 'answer'
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    #: 'category' | 'account' | 'liability'. Null for external/dismissed/answer.
    entity_type: Mapped[str | None] = mapped_column(String(20))
    #: Deliberately not a foreign key: it points at three different tables
    #: depending on entity_type. Deleted entities are filtered on read rather
    #: than cascaded, so unbinding is never a side effect of tidying up.
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: For mode='answer' only.
    answer: Mapped[bool | None] = mapped_column(Boolean)
    #: For mode='external' only. Self-reported; see the class docstring.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    #: When the user told us. IGAB cannot refresh a self-reported figure the
    #: way it refreshes a balance, so the age of the claim is part of it.
    as_of: Mapped[_PyDate | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GuideState(Base):
    """Per-budget Guide state that is not a binding: step progress and prefs.

    A key-value table with a JSONB payload, following ChangeLog.before/after
    and AIJob.payload for flexible shapes. Kept separate from AppSetting, which
    is global, admin-write-gated and allowlisted — none of which suits per
    budget user preference.

    Keys in use:
      ``prefs``               {"personalization": bool, "checkup": bool}
      ``step:<stage_id>``     {"state": "done" | "skipped"}
    """

    __tablename__ = "guide_state"
    __table_args__ = (UniqueConstraint("budget_id", "key", name="uq_guide_state_budget_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WishlistProject(Base):
    """A group of wishes — "we want to do X, so we need a, b, c".

    Optionally names the envelope its items draw on; an item with a category
    of its own overrides it. No stored status: a project is complete when no
    item in it is open, derived on read so there is nothing to drift.
    """

    __tablename__ = "wishlist_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WishlistItem(Base):
    """A wish: something to buy or do, and the envelope that funds it.

    The wishlist lives inside the budget, not beside it. A wish's money is an
    envelope's money — by default a category of its own in the Wishlist group
    (`owns_envelope`), or any existing category, or none yet — and the
    wishlist adds intent (why the envelope exists, when it was last
    affirmed), priority and a cooling-off period. `cost` is the wish's own
    figure; for an own envelope the wishlist also writes a savings goal from
    it, and the budget page may move that goal afterwards — "what it costs"
    and "what I will set aside" are allowed to differ.

    Linking a purchase to a transaction is deliberately absent: spending from
    an own envelope IS the purchase. Self-reported Guide money never enters
    reach.
    """

    __tablename__ = "wishlist_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wishlist_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[Decimal] = mapped_column(Numeric(19, 4), default=0, nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    #: The wishlist created this wish's category. Governs the offer to delete
    #: the envelope with the wish, and the cost → savings-goal write.
    owns_envelope: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: 'open' | 'done' | 'dropped'
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    cooling_until: Mapped[date | None] = mapped_column(Date)
    last_affirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BudgetView(Base):
    __tablename__ = "budget_views"
    __table_args__ = (
        # Unique among LIVE views only: deletes are soft, and a full constraint
        # burned every deleted view's name forever — "already exists" against a
        # list showing nothing.
        Index(
            "uq_budget_view_budget_name_live",
            "budget_id",
            "name",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Leave categories this view has not placed out of it entirely, instead of
    #: collecting them under "Unassigned". Off by default: a category added
    #: after the view was built should surface rather than disappear, and the
    #: user opts into the tidier behaviour once they know the view is complete.
    hide_unassigned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    groups: Mapped[list["BudgetViewGroup"]] = relationship(
        back_populates="view",
        cascade="all, delete-orphan",
        order_by="BudgetViewGroup.sort_order",
    )
    placements: Mapped[list["BudgetViewPlacement"]] = relationship(
        back_populates="view", cascade="all, delete-orphan"
    )


class BudgetViewGroup(Base):
    """A group that exists only inside one view."""

    __tablename__ = "budget_view_groups"
    __table_args__ = (UniqueConstraint("view_id", "name", name="uq_budget_view_group_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    view_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_views.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    view: Mapped["BudgetView"] = relationship(back_populates="groups")
    placements: Mapped[list["BudgetViewPlacement"]] = relationship(back_populates="group")


class BudgetViewPlacement(Base):
    """Where one category sits in one view.

    A category with no placement is not an error: it falls into an "Unassigned"
    bucket the client renders last. That is deliberate — a category added after
    a view was built must never silently vanish from it.

    `is_hidden` covers the explicit ask to leave categories out of a view's
    arithmetic without deleting anything.
    """

    __tablename__ = "budget_view_placements"
    __table_args__ = (UniqueConstraint("view_id", "category_id", name="uq_budget_view_placement"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    view_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_views.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: NULL means placed in the view but not in any of its groups — it shows
    #: under "Unassigned" alongside categories with no placement at all.
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_view_groups.id", ondelete="SET NULL"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    view: Mapped["BudgetView"] = relationship(back_populates="placements")
    group: Mapped["BudgetViewGroup | None"] = relationship(back_populates="placements")
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
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
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
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
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
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manual_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), index=True
    )
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transaction_attachments.id", ondelete="SET NULL"),
        index=True,
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
    # The composite PK only covers the leading category_id
    Index("ix_category_tags_tag_id", "tag_id"),
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
    Index("ix_payee_tags_tag_id", "tag_id"),
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
    # Authoritative only when linked_account_id IS NULL — the same rule as
    # manual_balance below. A managed liability's kind comes from its account's
    # type, which is why a companion stores none at all.
    # Unmanaged vocabulary: 'mortgage'|'auto'|'student'|'personal'|
    # 'credit_card'|'medical'|'other'
    liability_type: Mapped[str | None] = mapped_column(String(30))
    linked_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), unique=True
    )
    # Authoritative only when linked_account_id IS NULL
    manual_balance: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    # Annual percent, e.g. 6.2500. Null = not known yet: a companion liability
    # created alongside its account starts with no terms, and zero is not a
    # stand-in — at zero the schedule reports never_pays_off. Both term columns
    # move together; LiabilityService.terms_complete is the single gate.
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    # Contractual payment — drives the baseline schedule. Null as above.
    minimum_payment: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    compounding: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    origination_date: Mapped[_PyDate | None] = mapped_column(Date)
    original_principal: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    # Promotional financing ("0% until X"): interest_rate applies only after
    # promo_end_date. promo_deferred_interest marks retailer deals that charge
    # interest RETROACTIVELY when the balance isn't cleared by the deadline.
    promo_end_date: Mapped[_PyDate | None] = mapped_column(Date)
    promo_deferred_interest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Explicit contractual term, when known (overrides the implied estimate)
    term_months: Mapped[int | None] = mapped_column(Integer)
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
