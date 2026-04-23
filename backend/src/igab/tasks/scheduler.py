from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


async def process_due_scheduled_transactions() -> None:
    from sqlalchemy import select

    from igab.db.models import Budget
    from igab.db.session import AsyncSessionLocal
    from igab.repositories.account_repo import AccountRepository
    from igab.repositories.category_repo import CategoryRepository
    from igab.repositories.payee_repo import PayeeRepository
    from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
    from igab.repositories.transaction_repo import TransactionRepository
    from igab.services.scheduled_transaction_service import ScheduledTransactionService
    from igab.services.transaction_service import TransactionService

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(Budget).where(Budget.is_deleted == False)  # noqa: E712
            )
            budgets = list(result.scalars().all())

            txn_svc = TransactionService(
                session,
                TransactionRepository(session),
                AccountRepository(session),
                CategoryRepository(session),
                PayeeRepository(session),
            )
            sched_svc = ScheduledTransactionService(
                ScheduledTransactionRepository(session), txn_svc
            )

            for budget in budgets:
                await sched_svc.process_due(budget.id)

            await session.commit()
        except Exception:
            await session.rollback()


async def process_auto_simplefin_sync() -> None:
    """Hourly job: sync any SimpleFIN connections whose daily_sync_time matches the current hour."""
    from sqlalchemy import select

    from igab.db.models import Budget, SimpleFINConnection
    from igab.db.session import AsyncSessionLocal
    from igab.repositories.account_repo import AccountRepository
    from igab.repositories.category_repo import CategoryRepository
    from igab.repositories.payee_repo import PayeeRepository
    from igab.repositories.simplefin_repo import SimpleFINRepository
    from igab.repositories.transaction_match_repo import TransactionMatchRepository
    from igab.repositories.transaction_repo import TransactionRepository
    from igab.services.simplefin_service import SimpleFINService
    from igab.services.transaction_matching_service import TransactionMatchingService
    from igab.services.transaction_service import TransactionService

    current_hour = datetime.now(UTC).hour

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(SimpleFINConnection).where(
                    SimpleFINConnection.sync_enabled == True,  # noqa: E712
                    SimpleFINConnection.daily_sync_time.isnot(None),
                )
            )
            connections = list(result.scalars().all())

            for conn in connections:
                if conn.daily_sync_time is None:
                    continue
                if conn.daily_sync_time.hour != current_hour:
                    continue

                # Find all budgets for this user
                budgets_result = await session.execute(
                    select(Budget).where(Budget.is_deleted == False)  # noqa: E712
                )
                budgets = list(budgets_result.scalars().all())

                txn_repo = TransactionRepository(session)
                account_repo = AccountRepository(session)
                payee_repo = PayeeRepository(session)
                category_repo = CategoryRepository(session)

                txn_svc = TransactionService(
                    session, txn_repo, account_repo, category_repo, payee_repo
                )
                match_repo = TransactionMatchRepository(session)
                matching_svc = TransactionMatchingService(session, txn_repo, match_repo, payee_repo)
                svc = SimpleFINService(
                    session,
                    SimpleFINRepository(session),
                    account_repo,
                    txn_repo,
                    txn_svc,
                    matching_svc,
                )

                for budget in budgets:
                    await svc.sync(conn.id, budget.id, sync_type="global")

            await session.commit()
        except Exception:
            await session.rollback()


def start_scheduler() -> None:
    scheduler.add_job(
        process_due_scheduled_transactions,
        trigger="cron",
        hour=0,
        minute=5,
        id="process_scheduled_transactions",
        replace_existing=True,
    )
    scheduler.add_job(
        process_auto_simplefin_sync,
        trigger="cron",
        minute=0,
        id="auto_simplefin_sync",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
