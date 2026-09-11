"""The tool implementations: shape in, existing service call, shape out.

Every function here is allowed to do exactly three things — read arguments,
call a service, and shape the reply. No queries. See `registry` for why, and
`tests/unit/test_ai_tools.py` for the check that keeps it true.
"""

from collections import defaultdict
from datetime import date
from typing import Any

from igab.ai.tools.context import ToolContext
from igab.ai.tools.shape import DEFAULT_ROW_LIMIT, clip, money, ranked, summarize_if_large
from igab.domain.activity_class import SPENDING_WITH_SAVINGS_CLASSES

#: Ceiling on any `months` argument, matching the reports router's own bound.
MAX_MONTHS = 600


def _months(args: dict, default: int = 12) -> int:
    raw = args.get("months", default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(MAX_MONTHS, value))


def _date(args: dict, key: str, fallback: date) -> date:
    """A date argument, falling back when the model wrote something else.

    Small models answer "last month" here. Falling back beats raising: the
    resolved value is recorded on the call, so a wrong range is visible in the
    transparency view rather than turning into an error the user cannot read.
    """
    parsed = _opt_date(args, key)
    return parsed if parsed is not None else fallback


def _opt_date(args: dict, key: str) -> date | None:
    raw = args.get(key)
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


async def get_budget_month(ctx: ToolContext, args: dict) -> dict:
    """The month grid.

    Two calls, not one: the summary carries the figures but neither the
    envelope's name nor whether money can be assigned into it, and the
    categories carry both. This is the same join the month endpoint does.
    """
    month = _date(args, "month", ctx.today).replace(day=1)
    summary = await ctx.budgets.get_budget_summary(ctx.budget_id, month)
    pairs = await ctx.categories.get_all_with_group_names(ctx.budget_id)
    meta: dict[Any, dict[str, Any]] = {
        cat.id: {
            "name": cat.name,
            "group": group,
            "is_assignable": bool(getattr(cat, "is_assignable", True)),
        }
        for cat, group in pairs
    }

    # Grouped, and only the unusual flags spelled out. A flat row per
    # envelope repeating its group name and two booleans was ~150 characters
    # each, and a budget with 188 envelopes tripped the size fallback — the
    # model was told "too large, ask narrower" and said there were too many
    # categories to list. Half the characters say the same thing.
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for balance in summary.category_balances:
        info = meta.get(balance.category_id)
        if info is None:
            continue
        # Income envelopes: the grid deliberately shows no assigned/available
        # figure for these, because the number is a lifetime accumulation
        # rather than a month's budget. A tool that reported it would show
        # something the user has never seen in the app.
        system = balance.in_system_group
        row: dict[str, Any] = {
            "category": info["name"],
            "assigned": None if system else money(balance.assigned),
            "activity": money(balance.activity),
            "available": None if system else money(balance.available),
        }
        if not info["is_assignable"]:
            row["not_assignable"] = True
        if (not system) and balance.available < 0:
            row["overspent"] = True
        groups[info["group"]].append(row)

    return summarize_if_large(
        {
            "month": month.isoformat(),
            "ready_to_assign": money(summary.to_be_assigned),
            "total_assigned": money(summary.total_assigned),
            "total_activity": money(summary.total_activity),
            "total_overspent": money(summary.total_overspent),
            "overspent_count": summary.overspent_count,
            "note": (
                "Envelopes are listed under their group. An envelope marked "
                "not_assignable cannot receive money; one marked overspent "
                "has a negative available."
            ),
            "groups": [{"group": name, "categories": rows} for name, rows in groups.items()],
        },
        keep=("month", "ready_to_assign", "total_overspent", "overspent_count"),
        max_chars=ctx.result_max_chars,
    )


async def list_categories(ctx: ToolContext, args: dict) -> dict:
    pairs = await ctx.categories.get_all_with_group_names(ctx.budget_id)
    rows = [
        {
            "name": cat.name,
            "group": group,
            "is_assignable": bool(getattr(cat, "is_assignable", True)),
        }
        for cat, group in pairs
    ]
    return clip(rows, limit=200)


async def list_accounts(ctx: ToolContext, args: dict) -> dict:
    accounts = await ctx.accounts.get_all(ctx.budget_id)
    rows = [
        {
            "name": a.name,
            "type": a.account_type,
            "on_budget": bool(getattr(a, "on_budget", True)),
            "closed": bool(getattr(a, "is_closed", False)),
        }
        for a in accounts
    ]
    return clip(rows, limit=100)


async def get_data_range(ctx: ToolContext, args: dict) -> dict:
    result = await ctx.reports.available_range(ctx.budget_id)
    earliest = result.get("earliest_month")
    return {
        "earliest_month": earliest.isoformat() if isinstance(earliest, date) else None,
        "months_available": result.get("months_available", 0),
    }


async def spending_by_category(ctx: ToolContext, args: dict) -> dict:
    start = _date(args, "start_date", ctx.today.replace(day=1))
    end = _date(args, "end_date", ctx.today)
    # The default answer is day-to-day spending only. Saying so matters: a
    # mortgage principal payment is real money out that this deliberately
    # excludes, and a model that does not know will under-report.
    include_savings = bool(args.get("include_savings"))
    classes = list(SPENDING_WITH_SAVINGS_CLASSES) if include_savings else None
    rows, total = await ctx.reports.spending_by_category(
        ctx.budget_id, start, end, include_classes=classes
    )
    shaped = [
        {"category": r["name"], "group": r["group_name"], "total": money(r["total"])} for r in rows
    ]
    result = clip(shaped, total_amount=total)
    result["start_date"] = start.isoformat()
    result["end_date"] = end.isoformat()
    result["covers"] = (
        "spending, savings and debt principal" if include_savings else "day-to-day spending only"
    )
    return result


async def budget_vs_actual(ctx: ToolContext, args: dict) -> dict:
    start = _date(args, "start_date", ctx.today.replace(day=1))
    end = _date(args, "end_date", ctx.today)
    data = await ctx.reports.budget_vs_actual(ctx.budget_id, start, end)
    rows = [
        {
            "category": c["category_name"],
            "group": c["category_group_name"],
            "assigned": money(c["assigned"]),
            "spent": money(c["spent"]),
            "variance": money(c["variance"]),
        }
        for c in data["categories"]
    ]
    result = clip(rows)
    result["total_assigned"] = money(data["total_assigned"])
    result["total_spent"] = money(data["total_spent"])
    result["start_date"] = start.isoformat()
    result["end_date"] = end.isoformat()
    return result


async def income_vs_expense(ctx: ToolContext, args: dict) -> dict:
    rows = await ctx.reports.income_vs_expense(ctx.budget_id, _months(args))
    shaped = [
        {
            "month": r["month"].isoformat() if isinstance(r["month"], date) else str(r["month"]),
            "income": money(r["income"]),
            "expenses": money(r["expenses"]),
            "savings": money(r["savings"]),
            "net": money(r["net"]),
        }
        for r in rows
    ]
    return clip(shaped, limit=36)


async def savings_rate(ctx: ToolContext, args: dict) -> dict:
    data = await ctx.reports.savings_rate(ctx.budget_id, _months(args))
    summary = data.get("summary", {})
    return {
        "summary": {k: money(v) for k, v in summary.items()},
        "months": [
            {
                "month": m["month"].isoformat()
                if isinstance(m.get("month"), date)
                else str(m.get("month")),
                "income": money(m.get("income")),
                "savings": money(m.get("savings")),
                "savings_rate": m.get("savings_rate"),
            }
            for m in data.get("months", [])[:36]
        ],
    }


async def search_transactions(ctx: ToolContext, args: dict) -> dict:
    """Wraps the register's own listing.

    `scope="leaf"` rather than the default `parent`: split legs are what carry
    categories, so a category-filtered search on the default scope would miss
    every split — which is exactly the bug `spending_insights` has.
    """
    category_ids = None
    name = args.get("category_name")
    if isinstance(name, str) and name.strip():
        resolved = await _resolve_category(ctx, name)
        # An unmatched name means "no such envelope", which must return
        # nothing — not silently widen to the whole budget.
        category_ids = [resolved] if resolved else []

    # Names, not ids: the listing does not eager-load these relationships, and
    # touching them would lazy-load — which raises under async. Two id->name
    # maps from repositories the context already holds is the cheap, correct
    # way to say "Cascade Market" instead of a UUID.
    payee_names = {p.id: p.name for p in await ctx.payees.get_all(ctx.budget_id)}
    category_names = {
        cat.id: cat.name for cat, _ in await ctx.categories.get_all_with_group_names(ctx.budget_id)
    }

    rows, total_count, total_amount = await ctx.transactions.list_for_budget(
        ctx.budget_id,
        start_date=_opt_date(args, "start_date"),
        end_date=_opt_date(args, "end_date"),
        search=args.get("search") if isinstance(args.get("search"), str) else None,
        category_ids=category_ids,
        scope="leaf",
        uncategorized=bool(args.get("uncategorized")),
        amount_min=_number(args.get("amount_min")),
        amount_max=_number(args.get("amount_max")),
        limit=DEFAULT_ROW_LIMIT,
    )
    shaped = [
        {
            "date": t.date.isoformat(),
            "payee": payee_names.get(t.payee_id),
            "amount": money(t.amount),
            "category": category_names.get(t.category_id),
            "memo": t.memo,
        }
        for t in rows
    ]
    result = clip(shaped, total_rows=total_count, total_amount=total_amount)
    if category_ids == []:
        result["note"] = f"No envelope matches {name!r}, so nothing was searched."
    return result


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _resolve_category(ctx: ToolContext, name: str):
    """Name to id, through the matcher the receipt path already uses."""
    from igab.services.category_matching import match_category

    pairs = await ctx.categories.get_all_with_group_names(ctx.budget_id)
    index = match_category(name, [(cat.name, group) for cat, group in pairs])
    return pairs[index][0].id if index is not None else None


async def payee_analysis(ctx: ToolContext, args: dict) -> dict:
    start = _date(args, "start_date", ctx.today.replace(day=1))
    end = _date(args, "end_date", ctx.today)
    rows, total, payee_count, _ = await ctx.reports.payee_analysis(
        ctx.budget_id, start, end, limit=25
    )
    shaped = [
        {
            "payee": r["payee_name"],
            "total": money(r["total"]),
            "count": r["count"],
            "recurring": r.get("is_recurring", False),
        }
        for r in rows
    ]
    # A ranked top-N, not a page, so `clip` would report "25 rows, not
    # truncated". The total spans every payee and so does the count, which is
    # why this one may state it.
    return ranked(shaped, measure="amount spent", total_amount=total, total_rows=payee_count)


async def large_transactions(ctx: ToolContext, args: dict) -> dict:
    start = _date(args, "start_date", ctx.today.replace(day=1))
    end = _date(args, "end_date", ctx.today)
    rows = await ctx.reports.large_transactions(ctx.budget_id, start, end, limit=25)
    shaped = [
        {
            "date": r["date"].isoformat() if isinstance(r["date"], date) else str(r["date"]),
            "payee": r["payee_name"],
            "amount": money(r["amount"]),
            "category": r["category_name"],
        }
        for r in rows
    ]
    return ranked(shaped, measure="size")


async def guide_checkup(ctx: ToolContext, args: dict) -> dict:
    """The app's own health review.

    `stamp` stays at its default False: stamping writes "when did you last run
    your checkup", and a question the user asked the chat is not them running
    their health report.
    """
    data = await ctx.guide.checkup(ctx.budget_id)
    if not data.get("enabled", False):
        # Off means off. Reporting empty findings as "nothing wrong" would
        # invent a clean bill of health nobody issued.
        return {
            "enabled": False,
            "note": (
                "The financial checkup is switched off in this budget, so there "
                "is nothing to report. Do not treat this as a clean bill of health."
            ),
        }
    return summarize_if_large(
        {
            "enabled": True,
            "as_of": str(data.get("as_of")),
            "metrics": [
                {
                    "label": m.get("label"),
                    "value": money(m.get("value")),
                    "target": money(m.get("target")),
                    "detail": m.get("detail"),
                }
                for m in data.get("metrics", [])
            ],
            "findings": [
                {"title": f.get("title"), "detail": f.get("detail"), "kind": f.get("kind")}
                for f in data.get("findings", [])
            ],
        },
        keep=("enabled", "as_of", "findings"),
        max_chars=ctx.result_max_chars,
    )
