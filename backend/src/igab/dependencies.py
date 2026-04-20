from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import User
from igab.db.session import get_session
from igab.domain.exceptions import AuthenticationError
from igab.repositories.account_repo import AccountRepository
from igab.repositories.budget_view_repo import BudgetViewRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.repositories.settings_repo import SettingsRepository
from igab.repositories.simplefin_repo import SimpleFINRepository
from igab.repositories.target_repo import TargetRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.user_repo import UserRepository
from igab.services.ai_service import AIService
from igab.services.auth_service import AuthService
from igab.services.budget_service import BudgetService
from igab.services.reconciliation_service import ReconciliationService
from igab.services.report_service import ReportService
from igab.services.scheduled_transaction_service import ScheduledTransactionService
from igab.services.settings_service import SettingsService
from igab.services.simplefin_service import SimpleFINService
from igab.services.target_service import TargetService
from igab.services.transaction_service import TransactionService

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


def get_budget_view_repo(session: SessionDep) -> BudgetViewRepository:
    return BudgetViewRepository(session)


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


def get_budget_service(
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    category_group_repo: Annotated[CategoryGroupRepository, Depends(get_category_group_repo)],
    assignment_repo: Annotated[BudgetAssignmentRepository, Depends(get_assignment_repo)],
    transaction_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> BudgetService:
    return BudgetService(account_repo, category_repo, category_group_repo, assignment_repo, transaction_repo)


def get_transaction_service(
    session: SessionDep,
    transaction_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
) -> TransactionService:
    return TransactionService(session, transaction_repo, account_repo, category_repo, payee_repo)


def get_simplefin_service(
    session: SessionDep,
    repo: Annotated[SimpleFINRepository, Depends(get_simplefin_repo)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> SimpleFINService:
    return SimpleFINService(session, repo, account_repo, txn_repo, txn_service)


def get_reconciliation_service(
    session: SessionDep,
    repo: Annotated[ReconciliationRepository, Depends(get_reconciliation_repo)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
    transaction_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> ReconciliationService:
    return ReconciliationService(session, repo, account_repo, payee_repo, transaction_repo)


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
