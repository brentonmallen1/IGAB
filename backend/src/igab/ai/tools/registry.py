"""What the chat may look up, and how each lookup is declared.

**Every tool is a thin adapter over a service this app already has.** None of
them writes SQL. That is not a style preference: the money rules here are
subtle — carryover, credit-card set-asides, `is_assignable`, posted-vs-pending,
split legs — and a second implementation of any of them will drift and make the
chat contradict the grid two inches to its left. `AIService.spending_insights`
already demonstrated the failure, hand-rolling a query that silently dropped
every split transaction.

`tests/unit/test_ai_tools.py` enforces it by reading this package's source and
failing on `select(`, `session.execute` or a models import.

Two constraints on the schemas, both from what small local models actually do:

- **Flat and scalar.** 7-8B models fill string/number/enum reliably and
  arrays-of-objects unreliably.
- **No UUID arguments, ever.** A model asked for a category id will invent one.
  Tools take names and resolve them through the matcher the receipt path
  already uses.

`budget_id` is never a parameter. It comes from the request, so the model
cannot name a budget it should not see.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from igab.ai.tools import handlers
from igab.ai.tools.context import ToolContext


@dataclass(frozen=True)
class ToolSpec:
    """One thing the chat can look up."""

    name: str
    description: str
    #: JSON Schema for the arguments, sent verbatim as Ollama's
    #: `tools[].function.parameters`.
    parameters: dict
    handler: Callable[[ToolContext, dict], Awaitable[dict]]
    #: The service method this delegates to, recorded on every call so the
    #: transparency view can show it went through the shared implementation.
    delegates_to: str = ""
    #: Rough cost, for the description a user reads. "slow" tools say so.
    slow: bool = False
    required: tuple[str, ...] = field(default_factory=tuple)


def _obj(properties: dict, required: tuple[str, ...] = ()) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = list(required)
    return schema


_MONTHS = {
    "type": "integer",
    "description": "How many months back to look. Clamped to the data available.",
}
_START = {"type": "string", "description": "Start date, YYYY-MM-DD."}
_END = {"type": "string", "description": "End date, YYYY-MM-DD."}


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_budget_month",
        description=(
            "The budget grid for one month: every envelope with what was assigned, "
            "what was spent, what is available, and whether money can be moved into "
            "it. Use this for anything about a specific month's envelopes."
        ),
        parameters=_obj(
            {"month": {"type": "string", "description": "Any date in the month, YYYY-MM-DD."}}
        ),
        handler=handlers.get_budget_month,
        delegates_to="BudgetService.get_budget_summary + CategoryRepository.get_all",
    ),
    ToolSpec(
        name="list_categories",
        description="Every envelope and the group it sits in. Cheap; use it to find exact names.",
        parameters=_obj({}),
        handler=handlers.list_categories,
        delegates_to="CategoryRepository.get_all_with_group_names",
    ),
    ToolSpec(
        name="list_accounts",
        description="Every account, its type, and its current balance.",
        parameters=_obj({}),
        handler=handlers.list_accounts,
        delegates_to="AccountRepository.get_all",
    ),
    ToolSpec(
        name="get_data_range",
        description=(
            "How far back this budget's data goes. Call this first when the user "
            "asks about a long period, so you do not claim months that do not exist."
        ),
        parameters=_obj({}),
        handler=handlers.get_data_range,
        delegates_to="ReportService.available_range",
    ),
    ToolSpec(
        name="spending_by_category",
        description=(
            "Total spent per envelope between two dates, largest first. By default "
            "this covers day-to-day spending only; set include_savings to also count "
            "money moved to savings and debt principal."
        ),
        parameters=_obj(
            {
                "start_date": _START,
                "end_date": _END,
                "include_savings": {
                    "type": "boolean",
                    "description": "Include savings contributions and debt principal.",
                },
            },
            ("start_date", "end_date"),
        ),
        handler=handlers.spending_by_category,
        delegates_to="ReportService.spending_by_category",
        required=("start_date", "end_date"),
    ),
    ToolSpec(
        name="budget_vs_actual",
        description=(
            "Assigned versus spent per envelope over a date range, with the variance. "
            "Use this for 'am I over budget' questions."
        ),
        parameters=_obj({"start_date": _START, "end_date": _END}, ("start_date", "end_date")),
        handler=handlers.budget_vs_actual,
        delegates_to="ReportService.budget_vs_actual",
        required=("start_date", "end_date"),
    ),
    ToolSpec(
        name="income_vs_expense",
        description="Income, expenses, savings and debt principal per month.",
        parameters=_obj({"months": _MONTHS}),
        handler=handlers.income_vs_expense,
        delegates_to="ReportService.income_vs_expense",
    ),
    ToolSpec(
        name="savings_rate",
        description="What share of income was kept, per month and overall.",
        parameters=_obj({"months": _MONTHS}),
        handler=handlers.savings_rate,
        delegates_to="ReportService.savings_rate",
    ),
    ToolSpec(
        name="search_transactions",
        description=(
            "Find transactions. Every filter is optional; combine them. Returns a "
            "capped page of rows plus the true count and total across the whole match."
        ),
        parameters=_obj(
            {
                "search": {"type": "string", "description": "Text in payee or memo."},
                "category_name": {"type": "string", "description": "Exact-ish envelope name."},
                "start_date": _START,
                "end_date": _END,
                "amount_min": {"type": "number"},
                "amount_max": {"type": "number"},
                "uncategorized": {
                    "type": "boolean",
                    "description": "Only rows still needing an envelope.",
                },
            }
        ),
        handler=handlers.search_transactions,
        delegates_to="TransactionRepository.list_for_budget",
    ),
    ToolSpec(
        name="payee_analysis",
        description="Who was paid the most between two dates, with counts and trends.",
        parameters=_obj({"start_date": _START, "end_date": _END}, ("start_date", "end_date")),
        handler=handlers.payee_analysis,
        delegates_to="ReportService.payee_analysis",
        required=("start_date", "end_date"),
    ),
    ToolSpec(
        name="large_transactions",
        description="The biggest transactions between two dates.",
        parameters=_obj({"start_date": _START, "end_date": _END}, ("start_date", "end_date")),
        handler=handlers.large_transactions,
        delegates_to="ReportService.large_transactions",
        required=("start_date", "end_date"),
    ),
    ToolSpec(
        name="guide_checkup",
        description=(
            "The app's own financial health review: every metric against its target "
            "and the findings that fired. Prefer this over judging someone's finances "
            "yourself — it is what the rest of the app tells them, and disagreeing "
            "with it is worse than saying nothing. Slow; call it at most once."
        ),
        parameters=_obj({}),
        handler=handlers.guide_checkup,
        delegates_to="GuideService.checkup",
        slow=True,
    ),
)

BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


def ollama_schema() -> list[dict]:
    """The `tools` array for /api/chat."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in TOOLS
    ]
