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
