"""Dev CLI: generate a sample budget for an existing user, bypassing auth.

    PYTHONPATH=src uv run python -m igab.sample_budget --email you@example.com

Wired up as `just sample-budget <email>`.
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from igab.db.models import Budget, User
from igab.db.session import AsyncSessionLocal
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.repositories.target_repo import TargetRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.sample_budget.generator import SampleBudgetGenerator, SampleResult


async def create_sample_budget_for_user(user: User, name: str, session) -> SampleResult:
    budget = Budget(user_id=user.id, name=name)
    session.add(budget)
    await session.flush()
    await session.refresh(budget)
    await seed_system_tags(session, budget.id)

    generator = SampleBudgetGenerator(
        session,
        budget.id,
        account_repo=AccountRepository(session),
        category_group_repo=CategoryGroupRepository(session),
        category_repo=CategoryRepository(session),
        payee_repo=PayeeRepository(session),
        transaction_repo=TransactionRepository(session),
        assignment_repo=BudgetAssignmentRepository(session),
        tag_repo=TagRepository(session),
        target_repo=TargetRepository(session),
        scheduled_repo=ScheduledTransactionRepository(session),
        reconciliation_repo=ReconciliationRepository(session),
        liability_repo=LiabilityRepository(session),
    )
    return await generator.generate()


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Generate a sample budget")
    parser.add_argument("--email", required=True, help="Email of the owning user")
    parser.add_argument("--name", default="Sample Budget", help="Name for the new budget")
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == args.email))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"No user with email {args.email}", file=sys.stderr)
            return 1

        existing = await session.execute(
            select(Budget).where(Budget.user_id == user.id, Budget.name == args.name)
        )
        if existing.scalar_one_or_none() is not None:
            print(f"Budget '{args.name}' already exists — pick another --name", file=sys.stderr)
            return 1

        counts = await create_sample_budget_for_user(user, args.name, session)
        await session.commit()

    print(f"Created '{args.name}':")
    for field_name, value in vars(counts).items():
        print(f"  {field_name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
