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

# The vocabularies, imported so the schemas a model reads ARE the keys the
# query accepts. This is not the SQL this package is forbidden to write —
# it is two dicts of names — and importing them is what stops the enum here
# drifting from the dimensions txn_query can actually group by.
from igab.repositories.txn_query import AGGREGATES, GROUPABLE


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

_ROW_ORDER = {
    "type": "string",
    "enum": ["date", "amount"],
    "description": "Sort rows by date (default) or by size.",
}

#: The filter vocabulary, shared by the listing and the rollup so a model
#: does not have to learn two of them — and so a filter added to one cannot
#: quietly be missing from the other. Flat and scalar throughout: small
#: models fill enums and strings reliably and arrays of objects badly.
_FILTERS: dict[str, dict] = {
    "search": {"type": "string", "description": "Text in payee or memo."},
    "category_name": {"type": "string", "description": "Exact-ish envelope name."},
    "account_name": {"type": "string", "description": "Exact-ish account name."},
    "payee_name": {"type": "string", "description": "Exact-ish payee name."},
    "start_date": _START,
    "end_date": _END,
    "amount_min": {"type": "number"},
    "amount_max": {"type": "number"},
    "direction": {
        "type": "string",
        "enum": ["inflow", "outflow"],
        "description": "Money in or money out. Omit for both.",
    },
    "cleared": {
        "type": "string",
        "enum": list(handlers.CLEARED_STATES),
        "description": "Only rows in this state.",
    },
    "unreconciled": {
        "type": "boolean",
        "description": "Everything a reconcile has yet to sign off.",
    },
    "uncategorized": {
        "type": "boolean",
        "description": "Only rows still needing an envelope.",
    },
    "is_transfer": {
        "type": "boolean",
        "description": "True for transfers only, false to exclude them.",
    },
}


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
        description=(
            "Income, expenses, savings and debt principal per month. 'savings' is saved: "
            "money moved into savings ('savings_moved') plus the balance held in Savings "
            "envelopes that count while money is in the budget ('savings_held'). 'net' "
            "subtracts only the moved part."
        ),
        parameters=_obj({"months": _MONTHS}),
        handler=handlers.income_vs_expense,
        delegates_to="ReportService.income_vs_expense",
    ),
    ToolSpec(
        name="savings_rate",
        description=(
            "What share of income was kept, per month and overall. Saved = money moved into "
            "savings ('savings_moved') plus what Savings envelopes that count while money is in "
            "the budget came to hold "
            "('savings_held'); the rate divides that total by income."
        ),
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
        parameters=_obj({**_FILTERS, "order": _ROW_ORDER}),
        handler=handlers.search_transactions,
        delegates_to="TransactionRepository.list_for_budget",
    ),
    ToolSpec(
        name="query_transactions",
        description=(
            "Totals over transactions, grouped. Use this instead of "
            "search_transactions whenever the question is about an amount rather "
            "than which rows: spend per month, per envelope, per payee, per "
            "account, by day of week. Every filter search_transactions takes "
            "applies here too, so 'average grocery spend by month, card only' is "
            "one call. Totals are exact over the whole match, not the page."
        ),
        parameters=_obj(
            {
                **_FILTERS,
                "group_by": {
                    "type": "string",
                    "enum": sorted(GROUPABLE),
                    "description": "What to total by. Defaults to category.",
                },
                "aggregate": {
                    "type": "string",
                    "enum": sorted(AGGREGATES),
                    "description": (
                        "sum totals the amounts, count counts rows, avg is the "
                        "mean row. Defaults to sum."
                    ),
                },
                "order": {
                    "type": "string",
                    "enum": ["value", "group", "rows"],
                    "description": "Sort groups by their total, their name, or how many rows.",
                },
                "limit": {
                    "type": "integer",
                    "description": "How many groups to return, 1-100. Defaults to 25.",
                },
            }
        ),
        handler=handlers.query_transactions,
        delegates_to="TransactionRepository.grouped_totals",
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
        name="get_debt_status",
        description=(
            "Every debt: balance, rate, payoff date, and interest still to pay. "
            "Use this for anything about loans, cards as debt, or being debt-free. "
            "A debt with no terms set has no payoff date, and the reply says which."
        ),
        parameters=_obj({}),
        handler=handlers.get_debt_status,
        delegates_to="LiabilityService.liabilities_report",
    ),
    ToolSpec(
        name="get_net_worth",
        description=(
            "Assets minus debts at each of the last months' ends. Use this for "
            "net worth, whether it is going up, and what it is made of."
        ),
        parameters=_obj({"months": _MONTHS}),
        handler=handlers.get_net_worth,
        delegates_to="ReportService.net_worth_history",
    ),
    ToolSpec(
        name="list_scheduled",
        description=(
            "Scheduled transactions coming up, soonest first, with what they come "
            "to. Use this for 'what is due', 'what is coming out this week', or "
            "anything about committed money that has not been paid yet."
        ),
        parameters=_obj(
            {
                "days_ahead": {
                    "type": "integer",
                    "description": "How far ahead to look, 1-365. Defaults to 30.",
                }
            }
        ),
        handler=handlers.list_scheduled,
        delegates_to="ScheduledTransactionRepository.get_all",
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
