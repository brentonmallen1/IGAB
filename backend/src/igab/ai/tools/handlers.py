"""The tool implementations: shape in, existing service call, shape out.

Every function here is allowed to do exactly three things — read arguments,
call a service, and shape the reply. No queries. See `registry` for why, and
`tests/unit/test_ai_tools.py` for the check that keeps it true.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from igab.ai.tools.context import ToolContext
from igab.ai.tools.shape import DEFAULT_ROW_LIMIT, clip, money, ranked, summarize_if_large
from igab.domain.activity_class import SPENDING_WITH_SAVINGS_CLASSES
from igab.repositories.txn_query import TransactionFilters, UnknownDimension

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
            "savings_moved": money(r["savings_moved"]),
            "savings_held": money(r["savings_held"]),
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
                "savings_moved": money(m.get("savings_moved")),
                "savings_held": money(m.get("savings_held")),
                "savings_rate": m.get("savings_rate"),
            }
            for m in data.get("months", [])[:36]
        ],
    }


#: What a model may put in `cleared`. Anything else is ignored rather than
#: passed through, so a hallucinated state cannot silently return nothing.
CLEARED_STATES = ("pending", "uncleared", "cleared", "reconciled")
DIRECTIONS = ("inflow", "outflow")


def _enum(args: dict, key: str, allowed: tuple[str, ...]) -> str | None:
    value = args.get(key)
    return value if isinstance(value, str) and value in allowed else None


async def _resolve_account(ctx: ToolContext, name: str):
    """Account name to id, case- and space-insensitively.

    Names, not ids: the registry's rule is that a model asked for a UUID
    invents one. An unmatched name returns None and the caller turns that
    into an empty result rather than silently searching everything.
    """
    wanted = name.strip().casefold()
    accounts = await ctx.accounts.get_all(ctx.budget_id, include_closed=True)
    for account in accounts:
        if account.name.casefold() == wanted:
            return account.id
    for account in accounts:
        if wanted in account.name.casefold():
            return account.id
    return None


async def _resolve_payee(ctx: ToolContext, name: str):
    wanted = name.strip().casefold()
    payees = await ctx.payees.get_all(ctx.budget_id)
    for payee in payees:
        if payee.name.casefold() == wanted:
            return payee.id
    for payee in payees:
        if wanted in payee.name.casefold():
            return payee.id
    return None


async def _filters_from_args(ctx: ToolContext, args: dict) -> tuple[TransactionFilters, str | None]:
    """The one place a model's arguments become a filter set.

    Shared by `search_transactions` and `query_transactions` so the two
    cannot come to disagree about what "on the Sapphire Visa, uncleared,
    outflow only" selects — which is the whole reason the rollup and the
    listing were built on one clause underneath.

    The second return value is a note when a name matched nothing: that has
    to reach the model, because an empty result and "there is no such
    account" are different answers and it cannot tell them apart.
    """
    note: str | None = None
    category_ids = None
    name = args.get("category_name")
    if isinstance(name, str) and name.strip():
        resolved = await _resolve_category(ctx, name)
        # An unmatched name means "no such envelope", which must return
        # nothing — not silently widen to the whole budget.
        category_ids = [resolved] if resolved else []
        if not resolved:
            note = f"No envelope matches {name!r}, so nothing was searched."

    account_ids = None
    account_name = args.get("account_name")
    if isinstance(account_name, str) and account_name.strip():
        resolved_account = await _resolve_account(ctx, account_name)
        account_ids = [resolved_account] if resolved_account else []
        if not resolved_account:
            note = f"No account matches {account_name!r}, so nothing was searched."

    payee_ids = None
    payee_name = args.get("payee_name")
    if isinstance(payee_name, str) and payee_name.strip():
        resolved_payee = await _resolve_payee(ctx, payee_name)
        payee_ids = [resolved_payee] if resolved_payee else []
        if not resolved_payee:
            note = f"No payee matches {payee_name!r}, so nothing was searched."

    # An unmatched name selects nothing: `None` means "no filter", so the
    # empty list above is the only way to say "this matches no rows".
    transfer = args.get("is_transfer")

    return (
        TransactionFilters(
            start_date=_opt_date(args, "start_date"),
            end_date=_opt_date(args, "end_date"),
            search=args.get("search") if isinstance(args.get("search"), str) else None,
            category_ids=category_ids,
            account_ids=account_ids,
            payee_ids=payee_ids,
            uncategorized=bool(args.get("uncategorized")),
            unreconciled=bool(args.get("unreconciled")),
            cleared=_enum(args, "cleared", CLEARED_STATES),
            direction=_enum(args, "direction", DIRECTIONS),
            is_transfer=transfer if isinstance(transfer, bool) else None,
            amount_min=_number(args.get("amount_min")),
            amount_max=_number(args.get("amount_max")),
        ),
        note,
    )


async def search_transactions(ctx: ToolContext, args: dict) -> dict:
    """Wraps the register's own listing.

    `scope="leaf"` rather than the default `parent`: split legs are what carry
    categories, so a category-filtered search on the default scope would miss
    every split — which is exactly the bug `spending_insights` has.
    """
    filters, note = await _filters_from_args(ctx, args)

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
        start_date=filters.start_date,
        end_date=filters.end_date,
        search=filters.search,
        category_ids=filters.category_ids,
        account_ids=filters.account_ids,
        payee_ids=filters.payee_ids,
        scope="leaf",
        uncategorized=filters.uncategorized,
        unreconciled=filters.unreconciled,
        cleared=filters.cleared,
        direction=filters.direction,
        is_transfer=filters.is_transfer,
        amount_min=filters.amount_min,
        amount_max=filters.amount_max,
        order="amount" if args.get("order") == "amount" else "date",
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
    if note:
        result["note"] = note
    return result


async def query_transactions(ctx: ToolContext, args: dict) -> dict:
    """A rollup over the same rows `search_transactions` lists.

    The open-ended one: any of the filters, grouped by any dimension, under
    any aggregate. What makes that safe to hand a model is that none of it
    is SQL — `group_by` and `aggregate` are keys into vocabularies
    `txn_query` built, the budget comes from the request, and an unknown key
    is an error naming the legal ones rather than a guess.

    The total is a real GROUP BY, not a sum of the page: a model given the
    sum of the first 200 rows would report it as the answer.
    """
    filters, note = await _filters_from_args(ctx, args)
    group_by = args.get("group_by") or "category"
    aggregate = args.get("aggregate") or "sum"
    try:
        groups, total_groups = await ctx.transactions.grouped_totals(
            ctx.budget_id,
            group_by=group_by,
            aggregate=aggregate,
            filters=filters,
            order=_enum(args, "order", ("value", "group", "rows")) or "value",
            limit=_row_limit(args),
        )
    except UnknownDimension as bad:
        # Back to the model as an answer it can act on, not a stack trace.
        return {"error": str(bad)}

    shaped = [
        {
            "group": row["group"],
            "value": money(row["value"]) if aggregate != "count" else row["value"],
            "rows": row["rows"],
        }
        for row in groups
    ]
    result: dict[str, Any] = {
        "grouped_by": group_by,
        "aggregate": aggregate,
        "groups": shaped,
        "group_count": total_groups,
    }
    if total_groups > len(shaped):
        result["note"] = f"The top {len(shaped)} of {total_groups} groups."
    if note:
        result["note"] = note
    return result


def _row_limit(args: dict) -> int:
    try:
        return max(1, min(100, int(args.get("limit", 25))))
    except (TypeError, ValueError):
        return 25


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


async def get_debt_status(ctx: ToolContext, args: dict) -> dict:
    """Every debt, what it costs, and when it ends.

    Wraps the Liabilities report rather than reading balances itself: payoff
    dates come out of the amortization schedule, and a second arithmetic for
    them would be a second answer to "when am I free of this".

    `terms_complete` is carried per row because a payoff date without terms
    is not a shorter answer, it is a different one — an imported loan arrives
    with no rate at all, and saying nothing beats inventing a date.
    """
    report = await ctx.liabilities.liabilities_report(ctx.budget_id)
    rows = [
        {
            "name": item["name"],
            "type": item["liability_type"],
            "balance": money(item["current_balance"]),
            "interest_rate": float(item["interest_rate"]) if item["interest_rate"] else None,
            "payoff_date": (
                item["live_payoff_date"].isoformat() if item["live_payoff_date"] else None
            ),
            "interest_remaining": (
                money(item["total_interest_remaining"])
                if item["total_interest_remaining"] is not None
                else None
            ),
            "never_pays_off": item["never_pays_off"],
            "terms_complete": item["terms_complete"],
        }
        for item in report.get("items", [])
    ]
    result: dict[str, Any] = {
        "debts": rows,
        "total_balance": money(report.get("total_balance", 0)),
    }
    missing = [str(r["name"]) for r in rows if not r["terms_complete"]]
    if missing:
        # The model must not read a null payoff date as "no debt" or fill the
        # gap itself; naming the rows is what stops both.
        result["note"] = (
            f"No terms set for {', '.join(missing)}, so they have no payoff date "
            f"or interest figure. Everything else here is unaffected."
        )
    return result


def _iso(value: Any) -> Any:
    """A date as a string, and anything already a string untouched."""
    return value.isoformat() if hasattr(value, "isoformat") else value


async def get_net_worth(ctx: ToolContext, args: dict) -> dict:
    """Assets minus debts, at each of the last months' ends."""
    months = _months(args, 12)
    history = await ctx.reports.net_worth_history(ctx.budget_id, months)
    points = [
        {
            "month": _iso(point["date"]),
            "assets": money(point.get("assets", 0)),
            "liabilities": money(point.get("liabilities", 0)),
            "net_worth": money(point.get("net_worth", 0)),
        }
        for point in history
    ]
    return summarize_if_large(
        {"months": points, "latest": points[-1] if points else None},
        keep=("latest",),
        max_chars=ctx.result_max_chars,
    )


async def list_scheduled(ctx: ToolContext, args: dict) -> dict:
    """What is due next, soonest first.

    `next_occurrence_date` is stored on the row, so this is a read rather
    than a second implementation of the recurrence rules in domain/schedule.
    """
    try:
        within = max(1, min(365, int(args.get("days_ahead", 30))))
    except (TypeError, ValueError):
        within = 30
    horizon = ctx.today + timedelta(days=within)

    rows = await ctx.scheduled.get_all(ctx.budget_id)
    payee_names = {p.id: p.name for p in await ctx.payees.get_all(ctx.budget_id)}
    category_names = {
        cat.id: cat.name for cat, _ in await ctx.categories.get_all_with_group_names(ctx.budget_id)
    }
    account_rows = await ctx.accounts.get_all(ctx.budget_id, include_closed=True)
    accounts = {a.id: a.name for a in account_rows}

    due = sorted(
        (r for r in rows if r.next_occurrence_date <= horizon),
        key=lambda r: r.next_occurrence_date,
    )
    shaped = [
        {
            "date": r.next_occurrence_date.isoformat(),
            "payee": payee_names.get(r.payee_id),
            "amount": money(r.amount),
            "account": accounts.get(r.account_id),
            "category": category_names.get(r.category_id),
            "frequency": r.frequency,
        }
        for r in due
    ]
    total = sum((r.amount for r in due), Decimal(0))
    return clip(shaped, total_rows=len(shaped), total_amount=total)


async def cash_projection(ctx: ToolContext, args: dict) -> dict:
    """Where the balance goes next, and whether it crosses zero.

    `goes_negative_date` is the whole point of the tool and is served first
    class rather than left for a model to find by scanning the points: "will
    I run out" is the question, and a null answer means no, not unknown.
    """
    try:
        horizon = max(7, min(365, int(args.get("horizon_days", 90))))
    except (TypeError, ValueError):
        horizon = 90
    report = await ctx.reports.cash_projection(ctx.budget_id, horizon)
    goes_negative = report.get("goes_negative_date")
    return summarize_if_large(
        {
            "horizon_days": horizon,
            "start_balance": money(report.get("start_balance", 0)),
            "goes_negative_date": _iso(goes_negative) if goes_negative else None,
            "upcoming": [
                {
                    "date": _iso(event.get("date")),
                    "payee": event.get("payee_name") or event.get("description"),
                    "amount": money(event.get("amount", 0)),
                }
                for event in report.get("events", [])
            ],
        },
        keep=("goes_negative_date", "start_balance", "horizon_days"),
        max_chars=ctx.result_max_chars,
    )


async def burn_rate(ctx: ToolContext, args: dict) -> dict:
    """Spending pace per month: the trailing 30 days against the 60 before
    them, per 30 days — as of the user's today, like the chart they see."""
    months = _months(args, 12)
    rows = await ctx.reports.burn_rate(ctx.budget_id, months, today=ctx.today)
    points = [
        {
            "month": _iso(row["date"]),
            "rolling_30": money(row["rolling_30"]),
            "prior_60": money(row["prior_60"]),
        }
        for row in rows
    ]
    return summarize_if_large(
        {"months": points, "latest": points[-1] if points else None},
        keep=("latest",),
        max_chars=ctx.result_max_chars,
    )


async def spending_anomalies(ctx: ToolContext, args: dict) -> dict:
    """Category-months well off their own baseline, worst first.

    The threshold and the baseline rule belong to `report_stats.anomaly_rows`
    and are not re-decided here — a tool with its own idea of "unusual" would
    disagree with the report the user can open beside it.
    """
    months = _months(args, 12)
    report = await ctx.reports.anomalies_report(ctx.budget_id, months)
    rows = [
        {
            "category": row["category_name"],
            "month": _iso(row["month"]),
            "spent": money(row["actual"]),
            "usual": money(row["baseline_mean"]),
            "direction": row["direction"],
            "month_still_running": row["partial_month"],
        }
        for row in report.get("anomalies", [])
    ]
    return clip(rows, total_rows=len(rows))
