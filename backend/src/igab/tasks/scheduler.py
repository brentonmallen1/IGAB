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


def start_scheduler() -> None:
    scheduler.add_job(
        process_due_scheduled_transactions,
        trigger="cron",
        hour=0,
        minute=5,
        id="process_scheduled_transactions",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
