"""What a tool is allowed to touch.

Built once per chat turn and handed to every handler. It carries the budget the
request is scoped to — never a model-supplied one — and the already-constructed
services, so a handler is a call and a shape, not a wiring exercise.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from igab.ai.tools.shape import TOOL_RESULT_MAX_CHARS

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from igab.guide.service import GuideService
    from igab.repositories.account_repo import AccountRepository
    from igab.repositories.category_repo import CategoryRepository
    from igab.repositories.payee_repo import PayeeRepository
    from igab.repositories.transaction_repo import TransactionRepository
    from igab.services.budget_service import BudgetService
    from igab.services.report_service import ReportService


@dataclass
class ToolContext:
    """The budget, the clock, and the services a handler may delegate to."""

    budget_id: uuid.UUID
    #: The browser's date. Report methods use the server clock internally, but
    #: anything this layer resolves itself ("last month") must use the user's.
    today: date
    session: "AsyncSession"
    reports: "ReportService"
    budgets: "BudgetService"
    guide: "GuideService"
    categories: "CategoryRepository"
    accounts: "AccountRepository"
    transactions: "TransactionRepository"
    payees: "PayeeRepository"
    #: How large one result may be before it is summarized, sized from the
    #: context window this turn was given.
    result_max_chars: int = TOOL_RESULT_MAX_CHARS


async def build_tool_context(session, budget_id: uuid.UUID, today: date) -> ToolContext:
    """Build the services a tool may delegate to.

    Constructed directly rather than through the request's dependency graph,
    because the streaming path builds this against its own session — and now
    because the MCP endpoint has no request dependency graph at all.

    One builder for both doors. Two would be two lists of repositories to
    keep in step, and the one that fell behind would be the one where a tool
    quietly stopped working.
    """
    from igab.guide.service import GuideService
    from igab.repositories.account_repo import AccountRepository
    from igab.repositories.category_repo import (
        BudgetAssignmentRepository,
        CategoryGroupRepository,
        CategoryRepository,
    )
    from igab.repositories.payee_repo import PayeeRepository
    from igab.repositories.snapshot_repo import SnapshotRepository
    from igab.repositories.transaction_repo import TransactionRepository
    from igab.services.budget_service import BudgetService
    from igab.services.report_service import ReportService

    category_repo = CategoryRepository(session)
    account_repo = AccountRepository(session)
    transaction_repo = TransactionRepository(session)
    return ToolContext(
        budget_id=budget_id,
        today=today,
        session=session,
        reports=ReportService(session),
        budgets=BudgetService(
            account_repo,
            category_repo,
            CategoryGroupRepository(session),
            BudgetAssignmentRepository(session),
            transaction_repo,
            snapshot_repo=SnapshotRepository(session),
        ),
        guide=GuideService(session),
        categories=category_repo,
        accounts=account_repo,
        transactions=transaction_repo,
        payees=PayeeRepository(session),
    )
