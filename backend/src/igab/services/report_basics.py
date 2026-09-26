"""The basic reports: spending over time for a chosen scope, income by
source, what the essentials reserve is measured against, and the months the
Overview's Means trend is drawn from.

Split from report_service.py, which is over the file-length budget and may
only shrink. These read the same predicates it does — `spending_trends`
goes through `ReportService._spending_query` so a line here and a bar there
cannot total differently — and nothing here decides money the budget page
does not already show.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, CategoryGroup, Payee, Transaction
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    ACTIVITY_REASON,
    CLASS_LABEL,
    COST_OF_LIVING_CLASSES,
    INCOME_ROW,
    REASON_LABEL,
    REASON_PRIORITY,
    TRACKED_COUNTERPART_ACCOUNT,
    TRACKED_TRANSFER,
    ActivityClass,
    ActivityReason,
    NecessityTier,
    apply_class_joins,
    basis_is_chosen,
    class_magnitude,
)
from igab.domain.dates import (
    ReportWindow,
    complete_month_window,
    complete_months_within,
    month_start,
    month_starts,
    report_window,
)
from igab.domain.money import quantize_cents
from igab.domain.money_moves import flows
from igab.domain.savings import HELD_REASON, HELD_REASON_LABEL
from igab.domain.spending import UNCATEGORIZED, spent
from igab.domain.subscriptions import Basis, service_cost
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import (
    CLASS_TOTAL_ROW,
    LEAF,
    NOT_DELETED,
    ON_BUDGET_ACCOUNT,
    PAYEE_OF_RECORD,
    POSTED,
    category_tagged,
    join_split_parent,
)
from igab.services.report_day import reader_today
from igab.services.savings_held import held_by_envelope

if TYPE_CHECKING:
    from igab.services.report_service import ReportService

#: What a payee-less row is called wherever rows are grouped by payee — Income
#: by Source, the Subscriptions report's payees and the savings-rate dialog's
#: income sources. `_NO_PAYEE_KEY` is the group key those rows share, which no
#: payee id can collide with.
NO_PAYEE = "No payee"
_NO_PAYEE_KEY = "__none__"


def _payee_key(payee_id: uuid.UUID | None) -> str:
    return str(payee_id) if payee_id else _NO_PAYEE_KEY


async def budget_window(
    session: AsyncSession, budget_id: uuid.UUID, months: int, today: date
) -> ReportWindow:
    """What "the last `months` months" means for this budget on the reader's
    `today`: that many complete months, never reaching before the budget's
    first transaction, and the running month beside them (`ReportWindow`).

    `domain.dates.report_window` is the arithmetic and says why the running
    month is never one of the N; this supplies where the history starts,
    which only the database knows. Every report with a month window reads it
    — the averaging ones through `history_window`, the series ones directly.
    """
    earliest = await TransactionRepository(session).earliest_date(budget_id)
    return report_window(today, months, earliest)


async def history_window(
    session: AsyncSession, budget_id: uuid.UUID, months: int, today: date
) -> tuple[date, date]:
    """The complete months of `budget_window` as (first day, last day): the
    window of every report that averages per month. Empty (start after end)
    when the history starts this month.

    Income by Source, Cost of Living, Discretionary, Subscriptions and the
    Essentials table called the arithmetic without the history, so "All
    time" — which counts the running month the window leaves out — asked for
    one month before the first transaction, and every average divided by a
    month nobody recorded: three complete months of history, averaged over
    four, read a quarter low.
    """
    window = await budget_window(session, budget_id, months, today)
    return window.start, window.complete_end


async def spending_trends(
    svc: ReportService,
    budget_id: uuid.UUID,
    start_date: date,
    end_date: date,
    category_ids: list[uuid.UUID] | None = None,
    account_ids: list[uuid.UUID] | None = None,
    include_classes: Sequence[ActivityClass] | None = None,
    today: date | None = None,
) -> dict:
    """Spending per category per month over the window: `_spending_rows`, so
    net of refunds with an Uncategorized series (id None), the same spending
    the Breakdown and Income vs Expenses report.

    `category_ids` is the resolved scope — explicit picks, a saved
    filter's effective set, a tag's members — already merged by the
    route. Months with nothing spent are zero, never missing, so every
    series is the same length as `months`.

    **The average divides by complete months only**: `avg_monthly` divides
    by the months the range holds whole and that are over
    (`complete_months_within`), `months_averaged` of them; the running month
    is drawn, named as `running_month` so the page calls it "so far", and
    never averaged. It divided the window's total by every month drawn, so on
    the default "this year" range a few days of the new month counted as a
    month of spending, and on the 3rd of a month the "Average / month" sat a
    third of a month low.
    """
    today = reader_today(today)
    months = month_starts(start_date.replace(day=1), end_date)
    index = {m: i for i, m in enumerate(months)}
    found = await svc._spending_rows(
        budget_id, start_date, end_date, category_ids, account_ids, include_classes
    )

    series: dict[uuid.UUID | None, dict] = {}
    for r in found.counted:
        entry = series.setdefault(
            r.id,
            {
                "id": r.id,
                "name": r.name or UNCATEGORIZED,
                "group_id": r.group_id,
                "group_name": r.group_name or UNCATEGORIZED,
                "monthly": [[] for _ in months],
            },
        )
        entry["monthly"][index[r.date.replace(day=1)]].append(r.amount)
    for e in series.values():
        e["monthly"] = [quantize_cents(spent(amounts)) for amounts in e["monthly"]]
        e["total"] = sum(e["monthly"], Decimal("0"))
    ordered = sorted(series.values(), key=lambda e: e["total"], reverse=True)
    monthly_totals = [
        sum((e["monthly"][i] for e in ordered), Decimal("0")) for i in range(len(months))
    ]
    averaged = [index[m] for m in complete_months_within(start_date, end_date, today)]
    running = month_start(today)
    return {
        "months": months,
        "series": ordered,
        "monthly_totals": monthly_totals,
        "total": sum(monthly_totals, Decimal("0")),
        "avg_monthly": (
            quantize_cents(sum((monthly_totals[i] for i in averaged), Decimal("0")) / len(averaged))
            if averaged
            else None
        ),
        "months_averaged": len(averaged),
        "running_month": running if running in index else None,
        "class_excluded": class_excluded_note(found.excluded, scoped=bool(category_ids)) or [],
        "counted_classes": found.classes,
    }


async def income_by_source(
    session: AsyncSession, budget_id: uuid.UUID, months: int = 12, today: date | None = None
) -> dict:
    """Income per payee per month: what the classifier reads as income.

    **The sign does not decide; the class does.** This filtered
    `Transaction.amount > 0` in SQL and then kept only INCOME rows in Python,
    but the classifier's income rule is "(amount > 0 AND uncategorized) OR the
    category is in a system group" — so a NEGATIVE row filed to an inflow
    category is income too: a clawed-back paycheque is negative income, not
    spending. Dropping it made this report's total exceed the income figure
    Income vs Expenses and the Cash Flow Sankey serve for the same window,
    which is the one thing three views of the same money must not do.

    Transfers, refunds into envelopes and investment returns are other classes
    and stay out — the same partition every cash-flow report uses. The row
    rule is `INCOME_ROW`, which both Sankey modes read too; budgeted mode
    summed positive split parents by sign until it did.
    """
    # N complete months of this budget's history, like every averaging report.
    start_date, end_date = await history_window(session, budget_id, months, reader_today(today))
    month_list = month_starts(start_date, end_date)
    index = {m: i for i, m in enumerate(month_list)}
    # By payee of record: these are leaf rows, and a split paycheck's legs
    # carry no payee of their own, so the raw column filed the pay under
    # "No payee" beside the same employer's unsplit deposits.
    q = (
        join_split_parent(
            select(
                PAYEE_OF_RECORD.label("payee_id"),
                Payee.name.label("payee_name"),
                Transaction.date,
                Transaction.amount,
            )
        )
        .outerjoin(Payee, Payee.id == PAYEE_OF_RECORD)
        .where(
            Transaction.budget_id == budget_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            ON_BUDGET_ACCOUNT,
            # In SQL rather than a Python skip: the sign pre-filter used to cut
            # the row set down first, and without it that skip would fetch
            # every on-budget cash-flow row in the window to discard most.
            INCOME_ROW,
        )
    )
    rows = (await session.execute(apply_class_joins(q))).all()
    sources: dict[str, dict] = {}
    for r in rows:
        key = _payee_key(r.payee_id)
        entry = sources.setdefault(
            key,
            {
                "payee_id": r.payee_id,
                "payee_name": r.payee_name or NO_PAYEE,
                "monthly": [Decimal("0")] * len(month_list),
                "total": Decimal("0"),
                "count": 0,
            },
        )
        entry["monthly"][index[r.date.replace(day=1)]] += r.amount
        entry["total"] += r.amount
        entry["count"] += 1
    ordered = sorted(sources.values(), key=lambda e: e["total"], reverse=True)
    for e in ordered:
        e["monthly"] = [quantize_cents(v) for v in e["monthly"]]
        e["total"] = quantize_cents(e["total"])
    monthly_totals = [
        quantize_cents(sum((e["monthly"][i] for e in ordered), Decimal("0")))
        for i in range(len(month_list))
    ]
    total = quantize_cents(sum(monthly_totals, Decimal("0")))
    return {
        "months": month_list,
        "sources": ordered,
        "monthly_totals": monthly_totals,
        "total": total,
        # Served, because Cost of Living's Take-home quotes it and the page
        # divided for itself — by a window that included the running month,
        # 5,500 beside Take-home's 6,000 for the same steady pay.
        "avg_monthly": quantize_cents(total / len(month_list)) if month_list else Decimal("0"),
        "months_averaged": len(month_list),
    }


#: The classes a savings rate's numerator can hold: saving, and — with the Savings
#: Rate tab's "include debt payments" — debt principal.
_CONTRIBUTOR_CLASSES = (ActivityClass.SAVINGS, ActivityClass.DEBT_PRINCIPAL)


async def savings_contributors(
    session: AsyncSession,
    budget_id: uuid.UUID,
    start_date: date,
    end_date: date,
    today: date | None = None,
) -> dict:
    """What a savings rate over a window was made of — the rate cards' dialog.

    **Same rows, same rule, so the parts sum to the card.** The rows are
    `CLASS_TOTAL_ROW`, the predicate the Overview card's frame and the Savings
    Rate tab's monthly totals read; each total is `class_magnitude` of the
    class's signed sum, as those cards compute it; and each contributor is
    that same flip applied to its own share of the rows. Nothing is truncated,
    so every list sums to its total to the cent — including a withdrawal from
    tracked savings back into the budget, which is a SAVINGS-class inflow and
    appears as a negative contributor rather than being dropped.

    **Named by where the money went.** A row whose transfer lands in a tracked
    account is grouped under that account, whatever rule classed it; any other
    row under its category. A category tagged Savings that transfers into a
    brokerage is therefore the brokerage: "where did the savings go" is
    answered by a destination, and naming the envelope instead would split one
    brokerage across as many rows as there are ways to reach it. The served
    `reason` is the rule that decided the group's rows — where rows of one
    destination were decided by different rules, the first in
    `REASON_PRIORITY`, the classifier's own order.

    **Through today** — the reader's, as the rate cards read it. The Overview
    card's frame is read up to today whatever range was picked, and the Savings
    Rate tab's window ends today, so a future-dated row is in neither and is not
    in this either.

    **Held rows.** Saved is moved plus held (`domain.savings`), so each
    kept-here Savings envelope whose balance changed over the window is a
    contributor of its own — `reason` `HELD_REASON`, `total` its held change,
    `count` its register rows in the window (assignments are not rows). Zero
    changes are omitted. A kept-here envelope's outflow to a tracked account
    still appears under that account: the pair nets, +300 there and −300 held.

    Income is grouped by payee, as Income by Source groups it.
    """
    end = min(end_date, reader_today(today))
    held = {
        cid: pair
        for cid, pair in (await held_by_envelope(session, budget_id, start_date, end)).items()
        if quantize_cents(pair[1]) != 0
    }
    held_counts = await TransactionRepository(session).count_categories_between(
        budget_id, list(held), start_date, end
    )
    wanted = [ActivityClass.INCOME.value, *(c.value for c in _CONTRIBUTOR_CLASSES)]
    q = (
        join_split_parent(
            select(
                Transaction.amount,
                ACTIVITY_CLASS.label("cls"),
                ACTIVITY_REASON.label("reason"),
                TRACKED_TRANSFER.label("tracked_transfer"),
                TRACKED_COUNTERPART_ACCOUNT.id.label("account_id"),
                TRACKED_COUNTERPART_ACCOUNT.name.label("account_name"),
                Transaction.category_id,
                Category.name.label("category_name"),
                # By payee of record, as Income by Source groups it.
                PAYEE_OF_RECORD.label("payee_id"),
                Payee.name.label("payee_name"),
            )
        )
        .outerjoin(Category, Category.id == Transaction.category_id)
        .outerjoin(Payee, Payee.id == PAYEE_OF_RECORD)
        .where(
            Transaction.budget_id == budget_id,
            CLASS_TOTAL_ROW,
            Transaction.date >= start_date,
            Transaction.date <= end,
            ACTIVITY_CLASS.in_(wanted),
        )
    )
    rows = (await session.execute(apply_class_joins(q))).all()

    signed: dict[str, Decimal] = {}
    groups: dict[str, dict[tuple[str, uuid.UUID], dict]] = {
        c.value: {} for c in _CONTRIBUTOR_CLASSES
    }
    sources: dict[str, dict] = {}
    for r in rows:
        signed[r.cls] = signed.get(r.cls, Decimal("0")) + r.amount
        if r.cls == ActivityClass.INCOME.value:
            source = sources.setdefault(
                _payee_key(r.payee_id),
                {
                    "payee_id": r.payee_id,
                    "payee_name": r.payee_name or NO_PAYEE,
                    "total": Decimal("0"),
                    "count": 0,
                },
            )
            source["total"] += r.amount
            source["count"] += 1
            continue
        if r.tracked_transfer:
            kind, key_id, name = "account", r.account_id, r.account_name
        else:
            kind, key_id, name = "category", r.category_id, r.category_name
        if key_id is None:
            # Unreachable by the rules: a SAVINGS or DEBT_PRINCIPAL row that is
            # not a tracked transfer was classed by its category's tag. Raised
            # rather than grouped under a blank name, which would still sum.
            raise ValueError(f"a {r.cls} row with no destination and no category")
        group = groups[r.cls].setdefault(
            (kind, key_id),
            {
                "kind": kind,
                "id": key_id,
                "name": name,
                "reasons": set(),
                "signed": Decimal("0"),
                "count": 0,
            },
        )
        group["reasons"].add(ActivityReason(r.reason))
        group["signed"] += r.amount
        group["count"] += 1

    def _by_magnitude(entries: list[dict], name: str = "name") -> list[dict]:
        return sorted(entries, key=lambda e: (-abs(e["total"]), e[name]))

    def _contributors(cls: ActivityClass) -> list[dict]:
        out = []
        for g in groups[cls.value].values():
            reason = min(g["reasons"], key=REASON_PRIORITY.index)
            out.append(
                {
                    "kind": g["kind"],
                    "id": g["id"],
                    "name": g["name"],
                    "reason": reason.value,
                    "reason_label": REASON_LABEL[reason],
                    "total": quantize_cents(class_magnitude({cls.value: g["signed"]}, cls)),
                    "count": g["count"],
                }
            )
        return _by_magnitude(out)

    moved = quantize_cents(class_magnitude(signed, ActivityClass.SAVINGS))
    held_rows = [
        {
            "kind": "category",
            "id": cid,
            "name": name,
            "reason": HELD_REASON,
            "reason_label": HELD_REASON_LABEL,
            "total": quantize_cents(amount),
            "count": held_counts.get(cid, 0),
        }
        for cid, (name, amount) in held.items()
    ]
    savings_held = sum((quantize_cents(amount) for _, amount in held.values()), Decimal("0"))
    return {
        "start_date": start_date,
        "end_date": end,
        "income": quantize_cents(signed.get(ActivityClass.INCOME.value, Decimal("0"))),
        "savings": moved + savings_held,
        "savings_moved": moved,
        "savings_held": savings_held,
        "debt_principal": quantize_cents(class_magnitude(signed, ActivityClass.DEBT_PRINCIPAL)),
        "savings_contributors": _by_magnitude(_contributors(ActivityClass.SAVINGS) + held_rows),
        "debt_contributors": _contributors(ActivityClass.DEBT_PRINCIPAL),
        "income_sources": _by_magnitude(
            [{**s, "total": quantize_cents(s["total"])} for s in sources.values()], "payee_name"
        ),
    }


#: How many complete months the Overview's Means trend reads, whatever range
#: the Overview itself is showing.
MEANS_TREND_MONTHS = 12


async def means_months(svc: ReportService, budget_id: uuid.UUID, today: date) -> list[dict]:
    """Income and outflows for each of the last `MEANS_TREND_MONTHS` complete
    months, oldest first — what the Overview's Means trend is drawn from.

    **The card's composition, month by month.** Each month's class buckets go
    through `money_moves.flows`, the row-sum half of the `figures` reading
    `dashboard_metrics` gives the Your Means card: outflows are
    `cost_of_living` (spending plus debt principal), income is the INCOME
    class, and savings — moved or held — are neither, so no held figure is
    read. A trend that counted a class the card does not would draw bars
    the card beside it contradicts.

    **Complete months only, never before the history.** A month in progress
    reads as a surplus every morning of it — the pay landed on the 1st, the
    bills have not — so the running month is out (`complete_month_window`).
    The window starts no earlier than the budget's first row: a month before
    anything was recorded is not a month of zero income, and a budget with
    no rows at all has no months. Inside the window a month with no activity
    is served as zeros, so the axis has no gaps.

    Independent of the Overview's selected range on purpose: the trend is
    "the last year", and a one-month range would leave it a single bar.
    """
    if await svc.txns.earliest_date(budget_id) is None:
        return []
    start, end = await history_window(svc.session, budget_id, MEANS_TREND_MONTHS, today)
    by_month = await svc._monthly_class_totals(budget_id, start, end)
    rows = []
    for month in month_starts(start, end):
        f = flows(by_month.get(month, {}))
        rows.append(
            {
                "month": month,
                "income": quantize_cents(f.income),
                "outflows": quantize_cents(f.cost_of_living),
            }
        )
    return rows


class SubscriptionServiceRow(TypedDict):
    """One service — a payee inside a Subscription-tagged category — and what
    it costs a year (`domain.subscriptions.service_cost`)."""

    payee_id: str | None
    payee_name: str
    basis: str
    annual: Decimal
    monthly: Decimal
    interval_days: int
    cadence: str
    cadence_assumed: bool
    latest_charge: Decimal
    first_charge_date: date
    last_charge_date: date
    charges_in_year: int
    refunded_in_year: Decimal


class SubscriptionRow(TypedDict):
    category_id: str
    category_name: str
    group_name: str
    #: The sum of its services' Annual; Monthly is that ÷ 12.
    annual: Decimal
    monthly: Decimal
    #: Net charges per month of the chosen range, for the chart. The range
    #: decides only this: Annual reads its own year whatever the picker says.
    monthly_amounts: list[Decimal]
    total: Decimal
    last_charge_date: date
    #: The services inside the envelope, costliest first. The category is the
    #: headline because the tag is on categories; the services are how you
    #: find which one grew — and which one stopped.
    services: list[SubscriptionServiceRow]


def _net_by_month(
    rows: Iterable[tuple[date, Decimal]], month_list: Sequence[date]
) -> list[Decimal]:
    """Net cost per month of `month_list`: charges less refunds, positive."""
    by_month: dict[date, Decimal] = {}
    for d, amount in rows:
        key = d.replace(day=1)
        by_month[key] = by_month.get(key, Decimal(0)) - amount
    return [by_month.get(m, Decimal(0)) for m in month_list]


async def subscriptions_report(
    session: AsyncSession, budget_id: uuid.UUID, months: int = 12, today: date | None = None
) -> dict:
    """Recurring charges: every posted row filed to a category tagged
    Subscription, grouped BY CATEGORY, with the services (payees) inside.

    The tag is on categories (repositories/tag_repo.py
    CATEGORY_ONLY_SYSTEM_KEYS), so the envelope is the line and the payees are
    the detail — "which service grew" is the next question after "which
    envelope grew".

    **What a service costs is `domain.subscriptions.service_cost`**, over the
    last 12 complete months whatever the range picker says: Annual is what
    that year charged, net of refunds; only a service younger than the year,
    or one whose price changed, is projected from its latest charge; one that
    `has_stopped` is listed and counts in nothing. Every service's whole
    history is read, because its age and cadence are not properties of any
    window. The range decides only the chart.

    Annual adds up: category = its services, summary = its categories. Each
    level's Monthly is its own Annual ÷ 12, so a Monthly column may differ
    from its rows' sum by rounding cents, never more.
    """
    from igab.repositories.tag_repo import TagRepository

    today = reader_today(today)
    year_start, year_end = complete_month_window(today, 12)

    empty = {
        "subscriptions": [],
        "summary": {
            "total_monthly": Decimal("0"),
            "total_annual": Decimal("0"),
            "charged_categories": 0,
            "tagged_categories": 0,
            "new_this_month": 0,
            "projected_services": 0,
            "stopped_services": 0,
        },
        "months": [],
        "monthly_totals": [],
        "year_start": year_start,
        "year_end": year_end,
    }

    tag_repo = TagRepository(session)
    tagged = await tag_repo.get_category_ids_by_system_keys(budget_id, ["subscription"])
    if not tagged:
        return empty

    # The chart's axis: N COMPLETE months, the meaning every month-windowed
    # report gives `months` (`history_window`).
    start_date, end_date = await history_window(session, budget_id, months, today)
    month_list = month_starts(start_date, end_date)

    # Every signed row, not only outflows: refunds net (the reports around
    # this one report net, and a refunded charge was never a cost). No lower
    # date bound — see the docstring. A service is its payee of record: a
    # charge split across two envelopes carries the service on the parent
    # only, and the raw column filed both legs under "No payee".
    q = (
        join_split_parent(
            select(
                Transaction.category_id,
                Category.name.label("category_name"),
                CategoryGroup.name.label("group_name"),
                PAYEE_OF_RECORD.label("payee_id"),
                Payee.name.label("payee_name"),
                Transaction.date,
                Transaction.amount,
            )
        )
        .join(Category, Category.id == Transaction.category_id)
        .join(CategoryGroup, CategoryGroup.id == Category.category_group_id)
        .outerjoin(Payee, Payee.id == PAYEE_OF_RECORD)
        .where(
            Transaction.budget_id == budget_id,
            category_tagged("subscription"),
            NOT_DELETED,
            POSTED,
            Transaction.date <= today,
            LEAF,
            ON_BUDGET_ACCOUNT,
        )
    )
    rows = (await session.execute(q)).all()

    # category -> payee key -> signed rows; the names ride along.
    by_category: dict[str, dict[str, list[tuple[date, Decimal]]]] = {}
    category_names: dict[str, tuple[str, str]] = {}
    payee_names: dict[str, str] = {}
    for r in rows:
        cid = str(r.category_id)
        key = _payee_key(r.payee_id)
        by_category.setdefault(cid, {}).setdefault(key, []).append((r.date, Decimal(r.amount)))
        category_names[cid] = (r.category_name, r.group_name)
        payee_names[key] = r.payee_name or NO_PAYEE

    subscriptions: list[SubscriptionRow] = []
    new_this_month = projected = stopped = 0
    for cid, by_payee in by_category.items():
        services: list[SubscriptionServiceRow] = []
        shown_rows: list[tuple[date, Decimal]] = []
        for key, payee_rows in by_payee.items():
            cost = service_cost(payee_rows, year_start=year_start, year_end=year_end, today=today)
            if cost is None:
                continue
            # A service that stopped before both the chart and the year began
            # is history, not a subscription: listing every cancelled service
            # ever would bury the live ones.
            if cost.basis is Basis.STOPPED and cost.last_charge_date < min(start_date, year_start):
                continue
            new_this_month += cost.new_this_month
            projected += cost.is_projected
            stopped += cost.basis is Basis.STOPPED
            shown_rows.extend(payee_rows)
            services.append(
                {
                    "payee_id": None if key == _NO_PAYEE_KEY else key,
                    "payee_name": payee_names[key],
                    "basis": cost.basis.value,
                    "annual": cost.annual,
                    "monthly": cost.monthly,
                    "interval_days": cost.interval_days,
                    "cadence": cost.cadence.value,
                    "cadence_assumed": cost.cadence_assumed,
                    "latest_charge": cost.latest_charge,
                    "first_charge_date": cost.first_charge_date,
                    "last_charge_date": cost.last_charge_date,
                    "charges_in_year": cost.charges_in_year,
                    "refunded_in_year": cost.refunded_in_year,
                }
            )
        if not services:
            continue
        # Live first, costliest first; stopped ones sink to the bottom.
        services.sort(key=lambda s: (s["basis"] == Basis.STOPPED, -s["annual"], s["payee_name"]))
        in_range = [(d, a) for d, a in shown_rows if start_date <= d <= end_date]
        monthly_amounts = _net_by_month(in_range, month_list)
        annual = sum((s["annual"] for s in services), Decimal(0))
        name, group = category_names[cid]
        subscriptions.append(
            {
                "category_id": cid,
                "category_name": name,
                "group_name": group,
                "annual": annual,
                "monthly": quantize_cents(annual / 12),
                "monthly_amounts": monthly_amounts,
                "total": sum(monthly_amounts, Decimal(0)),
                "last_charge_date": max(s["last_charge_date"] for s in services),
                "services": services,
            }
        )

    subscriptions.sort(key=lambda s: (-s["annual"], -s["total"], s["category_name"]))
    total_annual = sum((s["annual"] for s in subscriptions), Decimal(0))
    return {
        "subscriptions": subscriptions,
        "summary": {
            "total_annual": total_annual,
            "total_monthly": quantize_cents(total_annual / 12),
            # "Active" was a count of categories with any charge in the range,
            # stopped services and all, under a label that read as services.
            # Now it says what it counts: N of M tagged categories charged.
            "charged_categories": sum(
                1 for s in subscriptions if any(v["basis"] != Basis.STOPPED for v in s["services"])
            ),
            "tagged_categories": len(tagged),
            "new_this_month": new_this_month,
            "projected_services": projected,
            "stopped_services": stopped,
        },
        "months": month_list,
        # Every listed category's month, summed: what a stacked chart that
        # draws ten categories and an Other band must stand at.
        "monthly_totals": [
            sum((s["monthly_amounts"][i] for s in subscriptions), Decimal(0))
            for i in range(len(month_list))
        ],
        "year_start": year_start,
        "year_end": year_end,
    }


class CostSeries(TypedDict):
    """A cost over the window's complete months: per month, in all, and the
    monthly average — `_as_costs`."""

    monthly_amounts: list[Decimal]
    total: Decimal
    avg_monthly: Decimal


def _as_costs(signed: Iterable[tuple[date, Decimal]], month_list: Sequence[date]) -> CostSeries:
    """Signed ledger sums, each dated in its month, as the series a cost
    report draws: flipped positive, bucketed into the window's months, and
    averaged over every one of them.

    Outflows are negative in the ledger and a cost reads positive, so each sum
    is flipped — and a month whose refunds beat its spending stays negative
    rather than being clamped, because that is what happened. A sum dated in
    no month of the window is ignored. Every month in the window is complete
    (`complete_month_window`), so the average divides by all of them.

    One implementation for Cost of Living's groups and Discretionary's lines,
    groups and headline. The two reports sit side by side and answer halves of
    one question; bucketing, summing or averaging two ways would make their
    figures disagree about the same month.
    """
    index = {m: i for i, m in enumerate(month_list)}
    amounts = [Decimal("0")] * len(month_list)
    for month, total in signed:
        slot = index.get(date(month.year, month.month, 1))
        if slot is not None:
            amounts[slot] += -Decimal(total)
    whole = sum(amounts, Decimal("0"))
    n = len(month_list)
    return {
        "monthly_amounts": amounts,
        "total": quantize_cents(whole),
        "avg_monthly": quantize_cents(whole / n) if n else Decimal("0"),
    }


class CostOfLivingGroup(CostSeries):
    group_name: str
    #: This group's share of the cost-of-living total, 0-100. Not of income —
    #: the shares have to add to 100 or the bar reads as arithmetic nobody
    #: can check.
    share: Decimal
    #: The categories behind this bar, so it can be opened. Empty on the
    #: Uncategorized bucket, which is drilled by "no category" rather than by
    #: a list of ids — an empty list would filter nothing and list the lot.
    category_ids: list[str]


#: The classes worth naming when a report leaves them out. A row that fell to
#: TRANSFER_INTERNAL is not an absence anyone is looking for; a mortgage
#: payment is.
#:
#: OPENING_BALANCE is not either. A starting balance is not activity in the
#: category it may be filed to, and the note's remedy — "Include savings &
#: debt payments" — could never add it back, so naming it would point at a
#: control that does nothing.
EXPLAINED_EXCLUSIONS: frozenset[str] = frozenset(
    {
        ActivityClass.SAVINGS.value,
        ActivityClass.DEBT_PRINCIPAL.value,
        ActivityClass.DEBT_INTEREST.value,
    }
)


def class_excluded_note(excluded_rows: list, *, scoped: bool) -> list[dict] | None:
    """Activity a report scoped in but will not count, summarised by class.

    Only when the user has *pointed at* categories, because that is when
    absence misleads: "I selected Car Payment and it isn't here" reads as a
    bug, not as a definition. An unfiltered report stays calm; its info panel
    covers the general rule.

    Pointing takes more than one form. Pareto and the day-patterns chart mean
    an explicit selection or an active view. The essentials family means the
    Essential tag: tagging a category IS pointing at it, and it was the case
    that misled — ten categories tagged, two in the report, and nothing on the
    page saying why. Callers decide what pointing means; the summary is one
    implementation.

    Rows need `.cls`, `.id` and `.amount`. Shared by report_service (Pareto,
    day patterns) and by the essentials reports below, which is why it lives
    here rather than on either.
    """
    if not scoped or not excluded_rows:
        return None

    by_class: dict[str, dict] = {}
    for r in excluded_rows:
        if r.cls not in EXPLAINED_EXCLUSIONS:
            continue
        slot = by_class.setdefault(r.cls, {"categories": set(), "total": Decimal("0")})
        slot["categories"].add(r.id)
        slot["total"] += abs(r.amount)
    if not by_class:
        return None

    return sorted(
        (
            {
                "activity_class": cls,
                "label": CLASS_LABEL[ActivityClass(cls)],
                "categories": len(v["categories"]),
                # Storage is 4dp; the note is user-facing copy, so cents.
                "total": quantize_cents(v["total"]),
            }
            for cls, v in by_class.items()
        ),
        key=lambda v: v["total"],
        reverse=True,
    )


#: What the null-group bucket is called: `domain.spending.UNCATEGORIZED`, the
#: one spelling every spending report's Uncategorized line uses. The client
#: tests it to decide that a drill-down means "no category at all" rather than
#: "these ids".
UNCATEGORIZED_GROUP = UNCATEGORIZED


async def cost_of_living(
    session: AsyncSession, budget_id: uuid.UUID, months: int = 12, today: date | None = None
) -> dict:
    """What it costs to keep the lights on, by category group, in two tiers.

    The groups roll up the WIDE tier, `NecessityTier.COST_OF_LIVING`:
    categories tagged Essential or Cost of living, plus debt payments by
    class. The lean tier, Essentials, is measured over the same window, and
    the difference is the non-essential gap — committed spending a lean month
    could shed. Tier membership is `tier_scope`'s rule, so this report and the
    Essentials report cannot disagree about what Essentials holds. The groups
    are the ones a budget already has, the shape a household thinks in —
    Housing, Utilities, Groceries.

    **As paid, never spread.** A twelve-month average of complete months
    already spreads a yearly bill by construction, so the budget's
    spread-sinking-funds setting (`services/essentials.py`) does not apply here.

    `basis` says how the wide tier was decided: the tags, or everything.
    "all" means nothing is tagged yet, and the caller must say so rather than
    present a figure that equals plain burn rate.
    """
    from igab.repositories.transaction_repo import TransactionRepository

    # N COMPLETE months: the window the Essentials report reads, so this
    # report's Essentials figure is that report's average rather than one
    # month off it. This took N calendar months through today and averaged the
    # N−1 complete ones, which agreed with Essentials only when spending was
    # flat: rent of 3,000 a month plus a 1,200 premium twelve months back read
    # 3,000 here and 3,100 there.
    today = reader_today(today)
    start_date, end_date = await history_window(session, budget_id, months, today)
    month_list = month_starts(start_date, end_date)

    repo = TransactionRepository(session)
    # The WIDE tier drives the groups, and the lean tier is measured over the
    # SAME window so the gap between them is a difference of two figures across
    # the same days. Three different windows in this family used to be the only
    # visible difference between Cost of Living and Essentials — a calendar
    # artifact wearing the gap's clothes.
    rows, basis = await repo.essential_spend_by_category_month(
        budget_id, start_date, end_date, tier=NecessityTier.COST_OF_LIVING
    )
    excluded, _ = await repo.essential_excluded_by_class(
        budget_id, start_date, end_date, tier=NecessityTier.COST_OF_LIVING
    )
    essentials_signed, lean_basis = await repo.essential_spend(
        budget_id, start_date, end_date, tier=NecessityTier.ESSENTIAL
    )
    # Each tier picks its fallback on its own, so tagging only Cost of living
    # left Essentials on "all": the whole burn rate, larger than the tier it
    # sits inside, reading "could not be cut". Unchosen, it is unknown.
    essentials_known = basis_is_chosen(lean_basis)

    # Every month in the window is complete, so every average divides by all
    # of them.
    n = len(month_list)

    #: Rows carry a null group where an essential PAYEE tagged a transaction
    #: with no category. They are real spending and must not vanish.
    #:
    #: Their category ids ride along so a bar can be opened. A single
    #: uncategorized row can dominate this chart — a $30,000 YNAB closing
    #: adjustment on an account someone had imported on-budget did exactly
    #: that — and the report had no drill-down at all, so the only honest
    #: reading of an unexplainable block was "this report is broken".
    by_group: dict[str, list[tuple[date, Decimal]]] = {}
    ids_by_group: dict[str, set[str]] = {}
    for row in rows:
        name = row.group_name or UNCATEGORIZED_GROUP
        by_group.setdefault(name, []).append((row.month, row.total))
        seen = ids_by_group.setdefault(name, set())
        if row.category_id is not None:
            seen.add(str(row.category_id))

    groups: list[CostOfLivingGroup] = [
        {
            **_as_costs(signed, month_list),
            "group_name": name,
            "share": Decimal("0"),
            "category_ids": sorted(ids_by_group.get(name, set())),
        }
        for name, signed in by_group.items()
    ]
    cost_of_living_total = sum((g["total"] for g in groups), Decimal("0"))
    for g in groups:
        g["share"] = (
            quantize_cents(g["total"] / cost_of_living_total * 100)
            if cost_of_living_total
            else Decimal("0")
        )
    groups.sort(key=lambda g: g["total"], reverse=True)

    # Take-home is Income by Source's own served average over the same
    # window, not a second division of its monthly totals here.
    income = await income_by_source(session, budget_id, months, today)
    avg_income = income["avg_monthly"]
    avg_cost_of_living = quantize_cents(cost_of_living_total / n) if n else Decimal("0")
    # Discretionary over the same window, the Discretionary report's own rows
    # (`DISCRETIONARY_ROW`), so the verdict can lay take-home out whole:
    # committed, discretionary, and what was left over. None untagged, as that
    # report serves it — "outside Cost of living" would be everything.
    disc_rows, disc_basis = await repo.discretionary_by_category_month(
        budget_id, start_date, end_date
    )
    avg_discretionary: Decimal | None = None
    if basis_is_chosen(disc_basis):
        avg_discretionary = _as_costs(((r.month, r.total) for r in disc_rows), month_list)[
            "avg_monthly"
        ]
    avg_essentials: Decimal | None = None
    if essentials_known:
        # Outflows are negative in the ledger; a cost reads positive here, the
        # same way the group buckets above flip theirs.
        avg_essentials = quantize_cents(-essentials_signed / n) if n else Decimal("0")

    return {
        "months": month_list,
        #: The exact window the figures cover, so a drill-down opened from a
        #: bar asks for the same days. The client used to have no way to know
        #: it — and re-deriving "twelve months back, from the first of that
        #: month, to today" on the other side is the same rule written twice.
        "window_start": start_date,
        "window_end": end_date,
        #: How many months the averages divide by: every month in the window,
        #: all of them complete.
        "months_averaged": n,
        "groups": groups,
        #: The three figures the report's cards print, and the only ones it
        #: needs: the gap between the tiers and the two ratios against
        #: take-home are arithmetic on these, with no input the client is
        #: missing, so by the boundary rule they are composed once in
        #: `frontend/src/components/reports/charts/necessityView.ts`. They
        #: were served here, read by no backend path, beside a third ratio of
        #: the same shape that already lived on the client.
        "avg_monthly_cost_of_living": avg_cost_of_living,
        "avg_monthly_essentials": avg_essentials,
        "avg_monthly_income": avg_income,
        "avg_monthly_discretionary": avg_discretionary,
        "basis": basis,
        #: False when nothing is tagged, so the page can say the figure is
        #: every category rather than a chosen few.
        "tagged": basis_is_chosen(basis),
        #: What was in scope and not counted. Tagging a category IS pointing at
        #: it, so this fires whenever the basis is a tag or a Guide binding —
        #: the case the note was written for is exactly "I tagged ten and two
        #: showed up".
        "class_excluded": class_excluded_note(excluded, scoped=basis_is_chosen(basis)) or [],
        #: The classes the figures above DO count, so a drill-down opened from
        #: a bar totals what the bar says. Without it a click on Housing lists
        #: the savings transfers too.
        "counted_classes": [c.value for c in COST_OF_LIVING_CLASSES],
        #: The tier the groups roll up. Debt principal joins it by class, per
        #: row, so a bar's categories and classes are not enough: the drill
        #: sends this and lists the tier's own rows.
        "necessity_tier": NecessityTier.COST_OF_LIVING.value,
    }


class DiscretionaryLine(TypedDict):
    category_id: str
    category_name: str
    total: Decimal
    avg_monthly: Decimal


class DiscretionaryGroup(TypedDict):
    #: None on the Uncategorized line: rows with no category at all, opened by
    #: "no category" rather than by a list of ids.
    group_id: str | None
    group_name: str
    total: Decimal
    avg_monthly: Decimal
    #: Empty on the Uncategorized line, which is one line of its own.
    categories: list[DiscretionaryLine]


def _by_total(item: DiscretionaryLine | DiscretionaryGroup) -> Decimal:
    return item["total"]


async def discretionary(
    svc: ReportService, budget_id: uuid.UUID, months: int = 12, today: date | None = None
) -> dict:
    """Spending outside Cost of living, by category within its group.

    The rows are `DISCRETIONARY_ROW` — SPENDING-class rows in no category
    tagged Essential or Cost of living, net of refunds — over the window the
    Cost of Living report reads, so the two tabs speak about the same months.
    Uncategorized spending is its own line: it is discretionary until someone
    files it, and dropping it would hide exactly the rows most worth opening.

    **Nothing is served on basis "all".** Untagged, every category is
    "outside Cost of living", and the figure would be the whole burn rate
    under a name that says a choice was made. The page explains what to tag
    instead; `tagged` says which case this is, and every figure is None.

    `spending_total` is the SPENDING class over the same window — the
    Income vs Expenses report's Expenses, summed — which this is a part of by
    construction (see `DISCRETIONARY_ROW`). The share between them is the
    page's arithmetic: two served figures and no missing input.
    """
    start_date, end_date = await history_window(svc.session, budget_id, months, reader_today(today))
    month_list = month_starts(start_date, end_date)
    rows, basis = await svc.txns.discretionary_by_category_month(budget_id, start_date, end_date)
    tagged = basis_is_chosen(basis)
    served: dict = {
        "months": month_list,
        # The exact window, so a drill-down asks for the same days.
        "window_start": start_date,
        "window_end": end_date,
        "months_averaged": len(month_list),
        "basis": basis,
        "tagged": tagged,
    }
    if not tagged:
        return {
            **served,
            "total": None,
            "avg_monthly": None,
            "monthly_totals": [],
            "spending_total": None,
            "cost_of_living_total": None,
            "groups": [],
        }

    by_group: dict[uuid.UUID | None, dict] = {}
    for row in rows:
        signed = (row.month, row.total)
        group = by_group.setdefault(
            row.group_id,
            {"name": row.group_name or UNCATEGORIZED_GROUP, "signed": [], "lines": {}},
        )
        group["signed"].append(signed)
        if row.category_id is not None:
            line = group["lines"].setdefault(
                row.category_id, {"name": row.category_name, "signed": []}
            )
            line["signed"].append(signed)

    groups: list[DiscretionaryGroup] = []
    for group_id, group in by_group.items():
        series = _as_costs(group["signed"], month_list)
        lines: list[DiscretionaryLine] = []
        for category_id, line in group["lines"].items():
            line_series = _as_costs(line["signed"], month_list)
            lines.append(
                {
                    "category_id": str(category_id),
                    "category_name": line["name"],
                    "total": line_series["total"],
                    "avg_monthly": line_series["avg_monthly"],
                }
            )
        groups.append(
            {
                "group_id": str(group_id) if group_id is not None else None,
                "group_name": group["name"],
                "total": series["total"],
                "avg_monthly": series["avg_monthly"],
                "categories": sorted(lines, key=_by_total, reverse=True),
            }
        )
    groups.sort(key=_by_total, reverse=True)

    whole = _as_costs(((r.month, r.total) for r in rows), month_list)
    by_month = await svc._monthly_class_totals(budget_id, start_date, end_date)
    spending = sum((flows(by_month.get(m, {})).spending for m in month_list), Decimal("0"))
    # The wide tier over the same window — Cost of Living's own figure — so
    # the page can say how the two tiers and spending fit: Cost of living +
    # Discretionary is all spending plus the debt payments Cost of living
    # counts by class, which Discretionary (spending only) never can.
    col_signed, _ = await svc.txns.essential_spend(
        budget_id, start_date, end_date, tier=NecessityTier.COST_OF_LIVING
    )
    return {
        **served,
        "total": whole["total"],
        "avg_monthly": whole["avg_monthly"],
        "monthly_totals": [quantize_cents(a) for a in whole["monthly_amounts"]],
        "spending_total": quantize_cents(spending),
        "cost_of_living_total": quantize_cents(Decimal("0") - col_signed),
        "groups": groups,
    }


async def wishlist_discipline(session: AsyncSession, budget_id: uuid.UUID) -> dict:
    """Cooling-off outcomes across the whole wishlist, open and closed.

    All time, deliberately: the point is the habit, and a habit measured over
    the last twelve months forgets the wish you talked yourself out of two
    years ago. The arithmetic is guide/wishlist.discipline — pure, and tested
    a case at a time.
    """
    from igab.db.models import WishlistItem
    from igab.guide.wishlist import DisciplineInput, added_on, discipline

    rows = (
        (
            await session.execute(
                select(WishlistItem).where(
                    WishlistItem.budget_id == budget_id,
                    WishlistItem.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    stats = discipline(
        DisciplineInput(
            status=w.status,
            cost=Decimal(w.cost or 0),
            created_at=added_on(w.added_on, w.created_at),
            cooling_until=w.cooling_until,
            done_at=w.done_at,
            dropped_at=w.dropped_at,
        )
        for w in rows
    )
    return {
        "cooled_then_bought": stats.cooled_then_bought,
        "cooled_then_dropped": stats.cooled_then_dropped,
        "bought_early": stats.bought_early,
        "dropped_early": stats.dropped_early,
        "still_open": stats.still_open,
        "resisted_total": stats.resisted_total,
        "resisted_count": stats.resisted_count,
        "bought_total": stats.bought_total,
        "open_total": stats.open_total,
        "avg_days_to_buy": stats.avg_days_to_buy,
        "avg_wish_cost": stats.avg_wish_cost,
        "unplaced": stats.unplaced,
    }
