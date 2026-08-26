import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import User
from igab.db.session import get_session
from igab.domain.exceptions import AuthenticationError
from igab.guide.service import GuideService
from igab.repositories.account_repo import AccountRepository
from igab.repositories.account_type_repo import AccountTypeRepository
from igab.repositories.ai_job_repo import AIJobRepository
from igab.repositories.attachment_repo import AttachmentRepository
from igab.repositories.budget_filter_repo import BudgetFilterRepository
from igab.repositories.budget_view_repo import BudgetViewRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.change_log_repo import ChangeLogRepository
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.repositories.settings_repo import SettingsRepository
from igab.repositories.simplefin_repo import SimpleFINRepository
from igab.repositories.snapshot_repo import SnapshotRepository
from igab.repositories.tag_repo import TagRepository
from igab.repositories.target_repo import TargetRepository
from igab.repositories.transaction_match_repo import TransactionMatchRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.user_repo import UserRepository
from igab.services.ai_service import AIService
from igab.services.assign_service import AssignService
from igab.services.attachment_service import AttachmentService
from igab.services.auth_service import AuthService
from igab.services.budget_service import BudgetService
from igab.services.category_service import CategoryService
from igab.services.change_log import ChangeRecorder
from igab.services.liability_service import LiabilityService
from igab.services.reconciliation_service import ReconciliationService
from igab.services.report_service import ReportService
from igab.services.scheduled_transaction_service import ScheduledTransactionService
from igab.services.settings_service import SettingsService
from igab.services.simplefin_service import SimpleFINService
from igab.services.target_service import TargetService
from igab.services.transaction_matching_service import (
    TransactionMatchingService,
    build_transaction_matching_service,
)
from igab.services.transaction_service import TransactionService, build_transaction_service
from igab.services.undo_service import UndoService

bearer_scheme = HTTPBearer()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_user_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def get_settings_repo(session: SessionDep) -> SettingsRepository:
    return SettingsRepository(session)


def get_settings_service(
    repo: Annotated[SettingsRepository, Depends(get_settings_repo)],
) -> SettingsService:
    return SettingsService(repo)


def get_report_service(session: SessionDep) -> ReportService:
    return ReportService(session)


def get_target_repo(session: SessionDep) -> TargetRepository:
    return TargetRepository(session)


def get_target_service(
    repo: Annotated[TargetRepository, Depends(get_target_repo)],
) -> TargetService:
    return TargetService(repo)


def get_ai_service(
    session: SessionDep,
    settings_svc: Annotated[SettingsService, Depends(get_settings_service)],
) -> AIService:
    return AIService(session, settings_svc)


def get_account_repo(session: SessionDep) -> AccountRepository:
    return AccountRepository(session)


def get_account_type_repo(session: SessionDep) -> AccountTypeRepository:
    return AccountTypeRepository(session)


def get_attachment_repo(session: SessionDep) -> AttachmentRepository:
    return AttachmentRepository(session)


def get_ai_job_repo(session: SessionDep) -> AIJobRepository:
    return AIJobRepository(session)


def get_attachment_service(
    repo: Annotated[AttachmentRepository, Depends(get_attachment_repo)],
) -> AttachmentService:
    return AttachmentService(repo)


def get_budget_view_repo(session: SessionDep) -> BudgetViewRepository:
    return BudgetViewRepository(session)


def get_budget_filter_repo(session: SessionDep) -> BudgetFilterRepository:
    return BudgetFilterRepository(session)


def get_transaction_repo(session: SessionDep) -> TransactionRepository:
    return TransactionRepository(session)


def get_category_repo(session: SessionDep) -> CategoryRepository:
    return CategoryRepository(session)


def get_category_group_repo(session: SessionDep) -> CategoryGroupRepository:
    return CategoryGroupRepository(session)


def get_assignment_repo(session: SessionDep) -> BudgetAssignmentRepository:
    return BudgetAssignmentRepository(session)


def get_payee_repo(session: SessionDep) -> PayeeRepository:
    return PayeeRepository(session)


def get_tag_repo(session: SessionDep) -> TagRepository:
    return TagRepository(session)


def get_simplefin_repo(session: SessionDep) -> SimpleFINRepository:
    return SimpleFINRepository(session)


def get_reconciliation_repo(session: SessionDep) -> ReconciliationRepository:
    return ReconciliationRepository(session)


def get_scheduled_transaction_repo(session: SessionDep) -> ScheduledTransactionRepository:
    return ScheduledTransactionRepository(session)


def get_auth_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> AuthService:
    return AuthService(user_repo)


def get_budget_move_repo(session: SessionDep):
    from igab.repositories.budget_move_repo import BudgetMoveRepository

    return BudgetMoveRepository(session)


def get_snapshot_repo(session: SessionDep) -> SnapshotRepository:
    return SnapshotRepository(session)


def get_change_recorder(session: SessionDep, current_user: "CurrentUser") -> ChangeRecorder:
    recorder = ChangeRecorder(session)
    recorder.actor_user_id = current_user.id
    return recorder


def get_change_log_repo(session: SessionDep) -> ChangeLogRepository:
    return ChangeLogRepository(session)


def get_undo_service(session: SessionDep) -> UndoService:
    return UndoService(session)


def get_budget_service(
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    category_group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
    assignment_repo: Annotated[BudgetAssignmentRepository, Depends(get_assignment_repo)],
    transaction_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    snapshot_repo: Annotated[SnapshotRepository, Depends(get_snapshot_repo)],
    current_user: "CurrentUser",
    move_repo=Depends(get_budget_move_repo),
) -> BudgetService:
    service = BudgetService(
        account_repo,
        category_repo,
        category_group_repo,
        assignment_repo,
        transaction_repo,
        move_repo=move_repo,
        snapshot_repo=snapshot_repo,
    )
    # Attribute the request's change-log rows to the caller. The service
    # constructs its own recorder internally, so stamp it here — the one
    # layer where CurrentUser exists. (Worker/scheduler code builds services
    # directly, never through this factory, and stays actor-less.)
    service.changes.actor_user_id = current_user.id
    return service


def get_category_service(
    session: SessionDep,
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    transaction_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    assignment_repo: Annotated[BudgetAssignmentRepository, Depends(get_assignment_repo)],
    current_user: "CurrentUser",
) -> CategoryService:
    service = CategoryService(
        session, category_repo, group_repo, budget_service, transaction_repo, assignment_repo
    )
    # Same actor stamping as get_budget_service — see there.
    service.changes.actor_user_id = current_user.id
    return service


def get_liability_repo(session: SessionDep) -> LiabilityRepository:
    return LiabilityRepository(session)


def get_liability_service(
    liability_repo: Annotated[LiabilityRepository, Depends(get_liability_repo)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    transaction_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> LiabilityService:
    return LiabilityService(liability_repo, account_repo, category_repo, transaction_repo)


def get_guide_service(
    session: SessionDep,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    target_service: Annotated[TargetService, Depends(get_target_service)],
    report_service: Annotated[ReportService, Depends(get_report_service)],
    liability_service: Annotated[LiabilityService, Depends(get_liability_service)],
) -> GuideService:
    return GuideService(
        session,
        budget_service=budget_service,
        target_service=target_service,
        report_service=report_service,
        liability_service=liability_service,
    )


def get_assign_service(
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    target_repo: Annotated[TargetRepository, Depends(get_target_repo)],
    target_service: Annotated[TargetService, Depends(get_target_service)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    category_group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
) -> AssignService:
    return AssignService(
        budget_service,
        target_repo,
        target_service,
        category_repo,
        category_group_repo,
    )


def get_transaction_match_repo(session: SessionDep) -> TransactionMatchRepository:
    return TransactionMatchRepository(session)


def get_transaction_service(session: SessionDep, current_user: "CurrentUser") -> TransactionService:
    service = build_transaction_service(session)
    # Same actor stamping as get_budget_service — see there.
    service.changes.actor_user_id = current_user.id
    return service


def get_transaction_matching_service(
    session: SessionDep,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionMatchingService:
    return build_transaction_matching_service(session, txn_service)


def get_simplefin_service(
    session: SessionDep,
    repo: Annotated[SimpleFINRepository, Depends(get_simplefin_repo)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    matching_service: Annotated[
        TransactionMatchingService, Depends(get_transaction_matching_service)
    ],
) -> SimpleFINService:
    return SimpleFINService(session, repo, account_repo, txn_repo, txn_service, matching_service)


def get_reconciliation_service(
    session: SessionDep,
    repo: Annotated[ReconciliationRepository, Depends(get_reconciliation_repo)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
    transaction_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    transaction_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> ReconciliationService:
    return ReconciliationService(
        session, repo, account_repo, payee_repo, transaction_repo, transaction_service
    )


def get_scheduled_transaction_service(
    repo: Annotated[ScheduledTransactionRepository, Depends(get_scheduled_transaction_repo)],
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> ScheduledTransactionService:
    return ScheduledTransactionService(repo, txn_service)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    try:
        return await auth_service.get_current_user(credentials.credentials)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


CurrentUser = Annotated[User, Depends(get_current_user)]


# ─── Resource-membership scoping ──────────────────────────────────────────────
# Every budget/account/transaction-scoped endpoint must verify the resource
# belongs to a budget the authenticated user is a MEMBER of (budget_members —
# the authorization source of truth; Budget.user_id is only creator-of-record).
# 404 (not 403) so foreign ids don't leak existence. Binds budget_id/
# account_id/transaction_id from path or query.


def _is_member(budget_id_col, user_id: uuid.UUID):
    """Correlated EXISTS predicate: `user_id` is a member of the budget the
    given column refers to. Composes into any guard query without a join."""
    from sqlalchemy import select

    from igab.db.models import BudgetMember

    return (
        select(BudgetMember.budget_id)
        .where(BudgetMember.budget_id == budget_id_col, BudgetMember.user_id == user_id)
        .exists()
    )


async def require_budget_access(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> uuid.UUID:
    from sqlalchemy import select

    from igab.db.models import BudgetMember

    # A membership row implies the budget exists (FK) — one query does both.
    result = await session.execute(
        select(BudgetMember.budget_id).where(
            BudgetMember.budget_id == budget_id,
            BudgetMember.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return budget_id


async def require_budget_owner(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> uuid.UUID:
    """Owner-gated operations: delete budget, manage members. Non-members get
    the usual 404; members without the owner role get 403 — they already know
    the budget exists, so the clearer error wins."""
    from sqlalchemy import select

    from igab.db.models import BudgetMember

    result = await session.execute(
        select(BudgetMember.role).where(
            BudgetMember.budget_id == budget_id,
            BudgetMember.user_id == current_user.id,
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the budget owner can do this",
        )
    return budget_id


async def get_admin_user(current_user: CurrentUser) -> "User":
    """Admin-gated global surfaces (user management, settings writes, backups).
    403, not 404 — admin-ness is not a secret."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required"
        )
    return current_user


async def require_account_access(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> uuid.UUID:
    from sqlalchemy import select

    from igab.db.models import Account

    result = await session.execute(
        select(Account.id).where(
            Account.id == account_id, _is_member(Account.budget_id, current_user.id)
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account_id


async def require_transaction_access(
    transaction_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> uuid.UUID:
    from sqlalchemy import select

    from igab.db.models import Transaction

    result = await session.execute(
        select(Transaction.id).where(
            Transaction.id == transaction_id, _is_member(Transaction.budget_id, current_user.id)
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction_id


async def require_connection_access(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> uuid.UUID:
    from sqlalchemy import select

    from igab.db.models import SimpleFINConnection

    result = await session.execute(
        select(SimpleFINConnection.id).where(
            SimpleFINConnection.id == connection_id,
            SimpleFINConnection.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return connection_id


async def require_attachment_access(
    attachment_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> uuid.UUID:
    from sqlalchemy import select

    from igab.db.models import Transaction, TransactionAttachment

    result = await session.execute(
        select(TransactionAttachment.id)
        .join(Transaction, TransactionAttachment.transaction_id == Transaction.id)
        .where(
            TransactionAttachment.id == attachment_id,
            _is_member(Transaction.budget_id, current_user.id),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return attachment_id


async def _require_budget_child(
    session: AsyncSession,
    model,
    id_value: uuid.UUID,
    user_id: uuid.UUID,
    label: str,
    *,
    live_only: bool = False,
) -> uuid.UUID:
    """Membership check for models carrying a budget_id column.

    `live_only` adds `NOT is_deleted` for soft-deleting models: a guard that
    passes soft-deleted ids lets the route's own loader (which does filter)
    come back empty — a 500 from `model_validate(None)` instead of a 404.
    """
    from sqlalchemy import select

    clauses = [model.id == id_value, _is_member(model.budget_id, user_id)]
    if live_only:
        clauses.append(model.is_deleted == False)  # noqa: E712
    result = await session.execute(select(model.id).where(*clauses))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return id_value


async def require_payee_access(
    payee_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> uuid.UUID:
    from igab.db.models import Payee

    return await _require_budget_child(session, Payee, payee_id, current_user.id, "Payee")


async def require_category_access(
    category_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> uuid.UUID:
    from igab.db.models import Category

    # live_only: a deleted category must 404 everywhere, not just on the routes
    # whose repository happens to filter. `PATCH /categories/{id}/assignment`
    # went through `get_or_create` and answered 204 on a deleted category,
    # writing an assignment nothing would ever show.
    return await _require_budget_child(
        session, Category, category_id, current_user.id, "Category", live_only=True
    )


async def require_category_group_access(
    group_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> uuid.UUID:
    from igab.db.models import CategoryGroup

    return await _require_budget_child(
        session, CategoryGroup, group_id, current_user.id, "Category group"
    )


async def require_view_access(
    view_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> uuid.UUID:
    from igab.db.models import BudgetView

    return await _require_budget_child(
        session, BudgetView, view_id, current_user.id, "View", live_only=True
    )


async def require_filter_access(
    filter_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> uuid.UUID:
    from igab.db.models import BudgetFilter

    return await _require_budget_child(
        session, BudgetFilter, filter_id, current_user.id, "Filter", live_only=True
    )


async def require_scheduled_access(
    id: uuid.UUID,  # noqa: A002 — must match the `{id}` path param on scheduled routes
    current_user: CurrentUser,
    session: SessionDep,
) -> uuid.UUID:
    from igab.db.models import ScheduledTransaction

    return await _require_budget_child(
        session, ScheduledTransaction, id, current_user.id, "Scheduled transaction"
    )


async def require_match_access(
    match_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> uuid.UUID:
    from sqlalchemy import select

    from igab.db.models import Transaction, TransactionMatch

    result = await session.execute(
        select(TransactionMatch.id)
        .join(Transaction, TransactionMatch.synced_transaction_id == Transaction.id)
        .where(TransactionMatch.id == match_id, _is_member(Transaction.budget_id, current_user.id))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    return match_id


async def require_tag_access(
    tag_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> uuid.UUID:
    from igab.db.models import Tag

    return await _require_budget_child(session, Tag, tag_id, current_user.id, "Tag")


BudgetAccess = Annotated[uuid.UUID, Depends(require_budget_access)]
BudgetOwnerAccess = Annotated[uuid.UUID, Depends(require_budget_owner)]
AdminUser = Annotated["User", Depends(get_admin_user)]
AccountAccess = Annotated[uuid.UUID, Depends(require_account_access)]
TransactionAccess = Annotated[uuid.UUID, Depends(require_transaction_access)]
ConnectionAccess = Annotated[uuid.UUID, Depends(require_connection_access)]
AttachmentAccess = Annotated[uuid.UUID, Depends(require_attachment_access)]
PayeeAccess = Annotated[uuid.UUID, Depends(require_payee_access)]
CategoryAccess = Annotated[uuid.UUID, Depends(require_category_access)]
CategoryGroupAccess = Annotated[uuid.UUID, Depends(require_category_group_access)]
FilterAccess = Annotated[uuid.UUID, Depends(require_filter_access)]
ViewAccess = Annotated[uuid.UUID, Depends(require_view_access)]
ScheduledAccess = Annotated[uuid.UUID, Depends(require_scheduled_access)]
MatchAccess = Annotated[uuid.UUID, Depends(require_match_access)]
TagAccess = Annotated[uuid.UUID, Depends(require_tag_access)]
