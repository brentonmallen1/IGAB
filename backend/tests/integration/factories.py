"""Builders for integration test data plus an assembled real-service bundle.

Factories insert rows directly through the session (flush, no commit) so setup
stays fast and independent of the code under test. Tests exercising behavior
should go through the services in `make_services`.
"""

import itertools
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    Account,
    Budget,
    BudgetAssignment,
    BudgetMember,
    Category,
    CategoryGroup,
    Liability,
    LiabilityBalanceSnapshot,
    Payee,
    ScheduledTransaction,
    SimpleFINConnection,
    Tag,
    Transaction,
    User,
)
from igab.repositories.account_repo import AccountRepository
from igab.repositories.attachment_repo import AttachmentRepository
from igab.repositories.budget_move_repo import BudgetMoveRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.simplefin_repo import SimpleFINRepository
from igab.repositories.transaction_match_repo import TransactionMatchRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.account_type_service import (
    apply_type,
    ensure_account_types_seeded,
    resolve_type,
)
from igab.services.budget_service import BudgetService
from igab.services.reconciliation_service import ReconciliationService
from igab.services.transaction_matching_service import TransactionMatchingService
from igab.services.transaction_service import TransactionService

_seq = itertools.count(1)


def _name(prefix: str) -> str:
    return f"{prefix} {next(_seq)}"


async def create_user(
    session: AsyncSession, email: str | None = None, *, is_admin: bool = False
) -> User:
    user = User(
        email=email or f"user{next(_seq)}@test.local",
        password_hash="x" * 60,  # never verified in integration tests
        is_admin=is_admin,
    )
    session.add(user)
    await session.flush()
    return user


async def create_budget(session: AsyncSession, user: User, name: str | None = None) -> Budget:
    budget = Budget(user_id=user.id, name=name or _name("Budget"))
    session.add(budget)
    await session.flush()
    # Membership is the authorization source of truth; the creator is always
    # an owner (mirrors what the API and the migration backfill both do).
    session.add(BudgetMember(budget_id=budget.id, user_id=user.id, role="owner"))
    await session.flush()
    # Accounts can't exist without their budget's type registry
    await ensure_account_types_seeded(session, budget.id)
    return budget


async def add_budget_member(
    session: AsyncSession, budget: Budget, user: User, role: str = "member"
) -> BudgetMember:
    member = BudgetMember(budget_id=budget.id, user_id=user.id, role=role)
    session.add(member)
    await session.flush()
    return member


async def create_account(
    session: AsyncSession,
    budget: Budget,
    name: str | None = None,
    *,
    account_type: str = "checking",
    on_budget: bool = True,
    simplefin_account_id: str | None = None,
) -> Account:
    type_row = await resolve_type(session, budget.id, account_type)
    account = Account(
        budget_id=budget.id,
        name=name or _name("Account"),
        simplefin_account_id=simplefin_account_id,
        **apply_type(type_row, on_budget),
    )
    session.add(account)
    await session.flush()
    return account


async def create_category_group(
    session: AsyncSession,
    budget: Budget,
    name: str | None = None,
    *,
    is_system: bool = False,
) -> CategoryGroup:
    group = CategoryGroup(budget_id=budget.id, name=name or _name("Group"), is_system=is_system)
    session.add(group)
    await session.flush()
    return group


async def create_category(
    session: AsyncSession,
    budget: Budget,
    group: CategoryGroup,
    name: str | None = None,
) -> Category:
    category = Category(
        budget_id=budget.id, category_group_id=group.id, name=name or _name("Category")
    )
    session.add(category)
    await session.flush()
    return category


async def create_payee(
    session: AsyncSession,
    budget: Budget,
    name: str | None = None,
    *,
    default_category_id: uuid.UUID | None = None,
    match_pattern: str | None = None,
    transfer_account_id: uuid.UUID | None = None,
) -> Payee:
    payee = Payee(
        budget_id=budget.id,
        name=name or _name("Payee"),
        default_category_id=default_category_id,
        match_pattern=match_pattern,
        transfer_account_id=transfer_account_id,
    )
    session.add(payee)
    await session.flush()
    return payee


async def create_transaction(
    session: AsyncSession,
    budget: Budget,
    account: Account,
    amount: str | Decimal,
    txn_date: date,
    *,
    category: Category | None = None,
    payee: Payee | None = None,
    cleared: str = "cleared",
    approved: bool = True,
    memo: str | None = None,
    is_split: bool = False,
    parent_transaction_id: uuid.UUID | None = None,
    transfer_id: uuid.UUID | None = None,
    import_id: str | None = None,
    sync_id: str | None = None,
    sync_source: str | None = None,
    created_via: str | None = None,
    is_deleted: bool = False,
    latitude: float | None = None,
    longitude: float | None = None,
    bank_posted_date: date | None = None,
    bank_amount: Decimal | str | None = None,
    bank_payee: str | None = None,
    entered_date: date | None = None,
) -> Transaction:
    txn = Transaction(
        budget_id=budget.id,
        account_id=account.id,
        date=txn_date,
        amount=Decimal(str(amount)),
        category_id=category.id if category else None,
        payee_id=payee.id if payee else None,
        cleared=cleared,
        approved=approved,
        memo=memo,
        is_split=is_split,
        parent_transaction_id=parent_transaction_id,
        transfer_id=transfer_id,
        import_id=import_id,
        sync_id=sync_id,
        sync_source=sync_source,
        created_via=created_via,
        is_deleted=is_deleted,
        latitude=latitude,
        longitude=longitude,
        bank_posted_date=bank_posted_date,
        bank_amount=Decimal(str(bank_amount)) if bank_amount is not None else None,
        bank_payee=bank_payee,
        entered_date=entered_date,
    )
    session.add(txn)
    await session.flush()
    return txn


async def create_transfer(
    session: AsyncSession,
    budget: Budget,
    from_account: Account,
    to_account: Account,
    amount: str | Decimal,
    txn_date: date,
    *,
    category: Category | None = None,
    cleared: str = "cleared",
) -> tuple[Transaction, Transaction]:
    """Both legs of a transfer, mutually linked — the shape a payment into a
    loan account really has. `category` goes on the from-leg (a YNAB
    spending transfer to a tracked account). Returns (from_leg, to_leg)."""
    from_leg = await create_transaction(
        session,
        budget,
        from_account,
        -Decimal(str(amount)),
        txn_date,
        category=category,
        cleared=cleared,
    )
    to_leg = await create_transaction(
        session,
        budget,
        to_account,
        Decimal(str(amount)),
        txn_date,
        cleared=cleared,
        transfer_id=from_leg.id,
    )
    from_leg.transfer_id = to_leg.id
    await session.flush()
    return from_leg, to_leg


async def create_budget_assignment(
    session: AsyncSession,
    budget: Budget,
    category: Category,
    month: date,
    assigned: str | Decimal,
) -> BudgetAssignment:
    assignment = BudgetAssignment(
        budget_id=budget.id,
        category_id=category.id,
        month=month,
        assigned=Decimal(str(assigned)),
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def create_scheduled_transaction(
    session: AsyncSession,
    budget: Budget,
    account: Account,
    amount: str | Decimal,
    frequency: str,
    next_occurrence_date: date,
    *,
    payee: Payee | None = None,
    category: Category | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    is_deleted: bool = False,
) -> ScheduledTransaction:
    sched = ScheduledTransaction(
        budget_id=budget.id,
        account_id=account.id,
        amount=Decimal(str(amount)),
        payee_id=payee.id if payee else None,
        category_id=category.id if category else None,
        frequency=frequency,
        start_date=start_date or next_occurrence_date,
        end_date=end_date,
        next_occurrence_date=next_occurrence_date,
        is_deleted=is_deleted,
    )
    session.add(sched)
    await session.flush()
    return sched


async def create_simplefin_connection(session: AsyncSession, user: User) -> SimpleFINConnection:
    conn = SimpleFINConnection(user_id=user.id, access_url_encrypted="test-not-encrypted")
    session.add(conn)
    await session.flush()
    return conn


async def create_tag(
    session: AsyncSession,
    budget: Budget,
    name: str | None = None,
    *,
    system_key: str | None = None,
    color_slot: str | None = None,
) -> Tag:
    tag = Tag(
        budget_id=budget.id,
        name=name or _name("Tag"),
        system_key=system_key,
        color_slot=color_slot,
    )
    session.add(tag)
    await session.flush()
    return tag


async def create_liability(
    session: AsyncSession,
    budget: Budget,
    name: str | None = None,
    *,
    liability_type: str = "personal",
    linked_account_id: uuid.UUID | None = None,
    manual_balance: Decimal | None = None,
    # None on either is the "terms not set" state a companion liability starts
    # in — both are nullable columns.
    interest_rate: Decimal | None = Decimal("6.0000"),
    minimum_payment: Decimal | None = Decimal("250.00"),
    origination_date: date | None = None,
    original_principal: Decimal | None = None,
) -> Liability:
    liability = Liability(
        budget_id=budget.id,
        name=name or _name("Liability"),
        liability_type=liability_type,
        linked_account_id=linked_account_id,
        manual_balance=manual_balance,
        interest_rate=interest_rate,
        minimum_payment=minimum_payment,
        origination_date=origination_date,
        original_principal=original_principal,
    )
    session.add(liability)
    await session.flush()
    return liability


async def create_liability_snapshot(
    session: AsyncSession,
    liability: Liability,
    snapshot_date: date,
    balance: Decimal,
    *,
    source: str = "manual",
) -> LiabilityBalanceSnapshot:
    snapshot = LiabilityBalanceSnapshot(
        liability_id=liability.id, date=snapshot_date, balance=balance, source=source
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


@dataclass
class Services:
    session: AsyncSession
    transaction_repo: TransactionRepository
    account_repo: AccountRepository
    category_repo: CategoryRepository
    category_group_repo: CategoryGroupRepository
    assignment_repo: BudgetAssignmentRepository
    payee_repo: PayeeRepository
    match_repo: TransactionMatchRepository
    attachment_repo: AttachmentRepository
    reconciliation_repo: ReconciliationRepository
    simplefin_repo: SimpleFINRepository
    transactions: TransactionService
    budgets: BudgetService
    reconciliation: ReconciliationService
    matching: TransactionMatchingService


def make_services(session: AsyncSession) -> Services:
    transaction_repo = TransactionRepository(session)
    account_repo = AccountRepository(session)
    category_repo = CategoryRepository(session)
    category_group_repo = CategoryGroupRepository(session)
    assignment_repo = BudgetAssignmentRepository(session)
    payee_repo = PayeeRepository(session)
    match_repo = TransactionMatchRepository(session)
    attachment_repo = AttachmentRepository(session)
    reconciliation_repo = ReconciliationRepository(session)
    simplefin_repo = SimpleFINRepository(session)

    transactions = TransactionService(
        session,
        transaction_repo,
        account_repo,
        category_repo,
        payee_repo,
        attachment_repo=attachment_repo,
        match_repo=match_repo,
    )
    budgets = BudgetService(
        account_repo,
        category_repo,
        category_group_repo,
        assignment_repo,
        transaction_repo,
        move_repo=BudgetMoveRepository(session),
    )
    reconciliation = ReconciliationService(
        session, reconciliation_repo, account_repo, payee_repo, transaction_repo, transactions
    )
    matching = TransactionMatchingService(
        session, transaction_repo, match_repo, payee_repo, transactions
    )

    return Services(
        session=session,
        transaction_repo=transaction_repo,
        account_repo=account_repo,
        category_repo=category_repo,
        category_group_repo=category_group_repo,
        assignment_repo=assignment_repo,
        payee_repo=payee_repo,
        match_repo=match_repo,
        attachment_repo=attachment_repo,
        reconciliation_repo=reconciliation_repo,
        simplefin_repo=simplefin_repo,
        transactions=transactions,
        budgets=budgets,
        reconciliation=reconciliation,
        matching=matching,
    )


def money(value: object) -> Decimal:
    """A money field read back out of a JSON body, as an exact `Decimal`.

    Money crosses the wire as a JSON **number** (`schemas/base.py`), and
    `Decimal(1516.67)` is `Decimal('1516.670000000000072759576141834259...')`
    — the binary expansion, not the number. `Decimal(str(x))` is exact.

    A helper rather than the spelling inline at each assertion, because the
    difference is invisible until it is not: of the assertions this replaced,
    every one but a single 1516.67 passed on values that happened to be
    exactly representable in binary, so the trap was already laid and silent.
    """
    return Decimal(str(value))
