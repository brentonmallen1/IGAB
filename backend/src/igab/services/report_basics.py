"""The basic reports: spending over time for a chosen scope, income by
source, and what the essentials reserve is measured against.

Split from report_service.py, which is over the file-length budget and may
only shrink. These read the same predicates it does — `spending_trends`
goes through `ReportService._spending_query` so a line here and a bar there
cannot total differently — and nothing here decides money the budget page
does not already show.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict

import polars as pl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, CategoryGroup, Payee, Transaction
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    CLASS_LABEL,
    COST_OF_LIVING_CLASSES,
    SPENDING_CLASSES,
    ActivityClass,
    apply_class_joins,
)
from igab.domain.dates import add_months
from igab.domain.money import quantize_cents
from igab.repositories.txn_filters import (
    CASH_FLOW_ROW,
    LEAF,
    NOT_DELETED,
    ON_BUDGET_ACCOUNT,
    POSTED,
    category_tagged,
)

if TYPE_CHECKING:
    from igab.services.report_service import ReportService


def _months_in_range(start_date: date, end_date: date) -> list[date]:
    months = []
    cur = start_date.replace(day=1)
    while cur <= end_date:
        months.append(cur)
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


def _subtract_months(d: date, months: int) -> date:
    """The start of the month `months` before `d`'s.

    Discarding the day is deliberate — every caller here is keying a month
    bucket. `add_months` is the one that preserves it.
    """
    # `replace(day=1)` rather than domain.dates.month_start: `month_start` is
    # a loop variable throughout this module and importing the name shadows it.
    return add_months(d.replace(day=1), -months)


async def spending_trends(
    svc: ReportService,
    budget_id: uuid.UUID,
    start_date: date,
    end_date: date,
    category_ids: list[uuid.UUID] | None = None,
    account_ids: list[uuid.UUID] | None = None,
    include_classes: Sequence[ActivityClass] | None = None,
) -> dict:
    """Spending per category per month over the window.

    `category_ids` is the resolved scope — explicit picks, a saved
    filter's effective set, a tag's members — already merged by the
    route. Months with nothing spent are zero, never missing, so every
    series is the same length as `months`.
    """
    months = _months_in_range(start_date.replace(day=1), end_date)
    index = {m: i for i, m in enumerate(months)}
    q = svc._spending_query(budget_id, start_date, end_date, category_ids, account_ids)
    rows = (await svc.session.execute(q)).all()
    included = {c.value for c in (include_classes or SPENDING_CLASSES)}
    counted = [r for r in rows if r.cls in included]
    other_class = [r for r in rows if r.cls not in included]

    series: dict[uuid.UUID, dict] = {}
    for r in counted:
        entry = series.setdefault(
            r.id,
            {
                "id": r.id,
                "name": r.name,
                "group_id": r.group_id,
                "group_name": r.group_name,
                "monthly": [Decimal("0")] * len(months),
                "total": Decimal("0"),
            },
        )
        magnitude = abs(r.amount)
        entry["monthly"][index[r.date.replace(day=1)]] += magnitude
        entry["total"] += magnitude
    ordered = sorted(series.values(), key=lambda e: e["total"], reverse=True)
    for e in ordered:
        e["monthly"] = [quantize_cents(v) for v in e["monthly"]]
        e["total"] = quantize_cents(e["total"])
    monthly_totals = [
        quantize_cents(sum((e["monthly"][i] for e in ordered), Decimal("0")))
        for i in range(len(months))
    ]
    return {
        "months": months,
        "series": ordered,
        "monthly_totals": monthly_totals,
        "total": quantize_cents(sum(monthly_totals, Decimal("0"))),
        "class_excluded": class_excluded_note(other_class, scoped=bool(category_ids)) or [],
    }


async def income_by_source(session: AsyncSession, budget_id: uuid.UUID, months: int = 12) -> dict:
    """Income per payee per month: on-budget inflows the classifier reads
    as income. Transfers, refunds into envelopes and investment returns
    are other classes and stay out — the same partition every cash-flow
    report uses."""
    today = date.today()
    start_date = _subtract_months(today, months - 1).replace(day=1)
    month_list = _months_in_range(start_date, today)
    index = {m: i for i, m in enumerate(month_list)}
    q = (
        select(
            Transaction.payee_id,
            Payee.name.label("payee_name"),
            Transaction.date,
            Transaction.amount,
            ACTIVITY_CLASS.label("cls"),
        )
        .outerjoin(Payee, Payee.id == Transaction.payee_id)
        .where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            Transaction.amount > 0,
            Transaction.date >= start_date,
            Transaction.date <= today,
            LEAF,
            CASH_FLOW_ROW,
            ON_BUDGET_ACCOUNT,
        )
    )
    rows = (await session.execute(apply_class_joins(q))).all()
    sources: dict[str, dict] = {}
    for r in rows:
        if r.cls != ActivityClass.INCOME.value:
            continue
        key = str(r.payee_id) if r.payee_id else "__none__"
        entry = sources.setdefault(
            key,
            {
                "payee_id": r.payee_id,
                "payee_name": r.payee_name or "No payee",
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
    return {
        "months": month_list,
        "sources": ordered,
        "monthly_totals": monthly_totals,
        "total": quantize_cents(sum(monthly_totals, Decimal("0"))),
    }


async def emergency_fund(
    session: AsyncSession, budget_id: uuid.UUID
) -> tuple[Decimal | None, str | None]:
    """What the Guide reads as the emergency fund, and why.

    Detection plus any self-reported amount, folded by the same rule the
    roadmap uses. The docstring here used to promise "One reader ... so the
    Essentials report and the roadmap quote the same balance" while reading
    only the detection — so a household keeping most of its buffer at another
    institution saw the roadmap say $10,240 and this report say $1,240 for one
    figure. The promise is now kept by calling the same function.
    """
    from igab.guide.bindings import fold_external, resolve
    from igab.guide.detection import GuideDetection
    from igab.guide.repo import GuideRepository

    rows = await GuideRepository(session).bindings(budget_id)
    resolution = resolve("emergency_fund", rows)
    detected: Decimal | None = None
    reason: str | None = None
    if resolution.runs_detection:
        finding = await GuideDetection(session).emergency_fund(
            budget_id, resolution.entities or None
        )
        detected, reason = finding.value, finding.reason
    total = fold_external(detected, resolution.external_amount)
    if total is None:
        return None, None
    if detected is None:
        reason = "you told us what you have set aside"
    return quantize_cents(total), reason


class RecurringSpend(TypedDict):
    """What a recurring line costs, whoever or whatever it is attached to.
    Identical arithmetic for a category and for a payee inside one, so it is
    written once and applied at both levels."""

    monthly_amounts: list[Decimal]
    total: Decimal
    avg_monthly: Decimal
    avg_per_charge: Decimal
    last_charge_date: date | None
    transaction_count: int


class SubscriptionPayeeRow(RecurringSpend):
    payee_id: str | None
    payee_name: str


class SubscriptionRow(RecurringSpend):
    category_id: str
    category_name: str
    group_name: str
    #: The services inside the envelope, biggest first. The category is the
    #: headline because the tag is on categories; the payees are how you find
    #: which one grew.
    payees: list[SubscriptionPayeeRow]


def _recurring_spend(frame: pl.DataFrame, month_list: list[date]) -> RecurringSpend:
    """The per-line arithmetic, for a category or one payee inside it.

    avg_monthly is the TRUE monthly burden: the total spread over the
    months since the FIRST charge, not the average charged month — a
    quarterly $30 subscription costs $10/mo, not $30/mo.
    """
    by_month = frame.group_by("month").agg(pl.col("amount").sum().alias("monthly_total"))
    monthly_amounts: list[Decimal] = []
    for m in month_list:
        row = by_month.filter(pl.col("month") == m)
        monthly_amounts.append(
            Decimal(str(round(row["monthly_total"][0], 4))) if len(row) else Decimal("0")
        )

    total = sum(monthly_amounts, Decimal("0"))
    txn_count = len(frame)
    first_charged = next((i for i, a in enumerate(monthly_amounts) if a > 0), None)
    avg_monthly = (
        Decimal("0") if first_charged is None else total / (len(month_list) - first_charged)
    )
    return {
        "monthly_amounts": monthly_amounts,
        "total": total,
        "avg_monthly": quantize_cents(avg_monthly),
        "avg_per_charge": quantize_cents(total / txn_count if txn_count else Decimal("0")),
        "last_charge_date": max(frame["date"].to_list()) if txn_count else None,
        "transaction_count": txn_count,
    }


async def subscriptions_report(
    session: AsyncSession, budget_id: uuid.UUID, months: int = 12
) -> dict:
    """Recurring charges: every posted outflow filed to a category tagged
    Subscription, grouped BY CATEGORY, with the payees inside each one.

    The tag is on categories (repositories/tag_repo.py
    CATEGORY_ONLY_SYSTEM_KEYS). Drawing one line per payee made the tag
    merely a filter and left the envelope — the thing actually tagged, and
    the thing a budget is made of — unnamed. The payees are still here,
    nested, because "which service grew" is the next question after
    "which envelope grew".

    Note what avg_monthly means at each level: per payee it is a service's
    cost; per category it is that envelope's recurring burn rate.
    """
    from igab.repositories.tag_repo import TagRepository

    empty = {
        "subscriptions": [],
        "summary": {
            "total_monthly": Decimal("0"),
            "total_annual": Decimal("0"),
            "active_count": 0,
        },
        "months": [],
    }

    tag_repo = TagRepository(session)
    tagged = await tag_repo.get_category_ids_by_system_keys(budget_id, ["subscription"])
    if not tagged:
        return empty

    today = date.today()
    end_date = today
    start_date = _subtract_months(today, months).replace(day=1)
    month_list = _months_in_range(start_date, end_date)

    q = (
        select(
            Transaction.category_id,
            Category.name.label("category_name"),
            CategoryGroup.name.label("group_name"),
            Transaction.payee_id,
            Payee.name.label("payee_name"),
            Transaction.date,
            Transaction.amount,
        )
        .join(Category, Category.id == Transaction.category_id)
        .join(CategoryGroup, CategoryGroup.id == Category.category_group_id)
        .outerjoin(Payee, Payee.id == Transaction.payee_id)
        .where(
            Transaction.budget_id == budget_id,
            category_tagged("subscription"),
            NOT_DELETED,
            POSTED,
            Transaction.amount < 0,  # outflows only
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            LEAF,
            ON_BUDGET_ACCOUNT,
        )
    )
    rows = (await session.execute(q)).all()
    if not rows:
        return {**empty, "months": month_list}

    # category_tagged guarantees category_id is not null, so there is no
    # "no category" sentinel to keep here — only payee can be missing.
    df = pl.DataFrame(
        {
            "category_id": [str(r.category_id) for r in rows],
            "category_name": [r.category_name for r in rows],
            "group_name": [r.group_name for r in rows],
            "payee_id": [str(r.payee_id) if r.payee_id else "__none__" for r in rows],
            "payee_name": [r.payee_name or "No payee" for r in rows],
            "month": [r.date.replace(day=1) for r in rows],
            "date": [r.date for r in rows],
            "amount": [abs(float(r.amount)) for r in rows],
        }
    )

    subscriptions: list[SubscriptionRow] = []
    for category_id in df["category_id"].unique().to_list():
        in_category = df.filter(pl.col("category_id") == category_id)

        payees: list[SubscriptionPayeeRow] = []
        for payee_id in in_category["payee_id"].unique().to_list():
            for_payee = in_category.filter(pl.col("payee_id") == payee_id)
            payees.append(
                {
                    "payee_id": None if payee_id == "__none__" else payee_id,
                    "payee_name": for_payee["payee_name"][0],
                    **_recurring_spend(for_payee, month_list),
                }
            )
        payees.sort(key=lambda p: p["total"], reverse=True)

        subscriptions.append(
            {
                "category_id": category_id,
                "category_name": in_category["category_name"][0],
                "group_name": in_category["group_name"][0],
                "payees": payees,
                **_recurring_spend(in_category, month_list),
            }
        )

    subscriptions.sort(key=lambda x: x["total"], reverse=True)

    total_monthly = sum((s["avg_monthly"] for s in subscriptions), Decimal("0"))
    return {
        "subscriptions": subscriptions,
        "summary": {
            "total_monthly": quantize_cents(total_monthly),
            "total_annual": quantize_cents(total_monthly * 12),
            "active_count": len(subscriptions),
        },
        "months": month_list,
    }


class CostOfLivingGroup(TypedDict):
    group_name: str
    monthly_amounts: list[Decimal]
    total: Decimal
    avg_monthly: Decimal
    #: This group's share of the essentials total, 0-100. Not of income —
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


#: What the null-group bucket is called. One spelling: the report labels the
#: bar with it and the client tests it to decide that a drill-down means "no
#: category at all" rather than "these ids".
UNCATEGORIZED_GROUP = "Uncategorized"


async def cost_of_living(session: AsyncSession, budget_id: uuid.UUID, months: int = 12) -> dict:
    """What it costs to keep the lights on, by category group.

    Built on the Essential tag rather than a new one. A sixth system tag whose
    only job is grouping would be a permanent addition to a vocabulary that
    otherwise changes how money is COUNTED, and the groups a budget already
    has are the shape a household thinks in — Housing, Utilities, Groceries.

    Nothing new is queried: `essential_spend_by_category_month` is the same
    query the Essentials report and the Overview card read, so a category
    counted here is counted there. Only the rollup is new.

    `basis` says how "essential" was decided — bound categories, the tag, or
    everything. "all" means nothing is tagged yet, and the caller must say so
    rather than present a figure that equals plain burn rate.
    """
    from igab.repositories.transaction_repo import TransactionRepository

    today = date.today()
    start_date = _subtract_months(today, months - 1).replace(day=1)
    month_list = _months_in_range(start_date, today)
    index = {m: i for i, m in enumerate(month_list)}

    repo = TransactionRepository(session)
    rows, basis = await repo.essential_spend_by_category_month(budget_id, start_date, today)
    excluded, _ = await repo.essential_excluded_by_class(budget_id, start_date, today)

    #: Rows carry a null group where an essential PAYEE tagged a transaction
    #: with no category. They are real spending and must not vanish.
    #:
    #: Their category ids ride along so a bar can be opened. A single
    #: uncategorized row can dominate this chart — a $30,000 YNAB closing
    #: adjustment on an account someone had imported on-budget did exactly
    #: that — and the report had no drill-down at all, so the only honest
    #: reading of an unexplainable block was "this report is broken".
    by_group: dict[str, list[Decimal]] = {}
    ids_by_group: dict[str, set[str]] = {}
    for row in rows:
        name = row.group_name or UNCATEGORIZED_GROUP
        bucket = by_group.setdefault(name, [Decimal("0")] * len(month_list))
        seen = ids_by_group.setdefault(name, set())
        if row.category_id is not None:
            seen.add(str(row.category_id))
        slot = index.get(date(row.month.year, row.month.month, 1))
        if slot is not None:
            # Outflows are negative in the ledger; a cost reads positive here.
            bucket[slot] += -Decimal(row.total)

    groups: list[CostOfLivingGroup] = []
    essentials_total = Decimal("0")
    for name, amounts in by_group.items():
        total = sum(amounts, Decimal("0"))
        essentials_total += total
        groups.append(
            {
                "group_name": name,
                "monthly_amounts": amounts,
                "total": quantize_cents(total),
                "avg_monthly": quantize_cents(total / len(month_list)),
                "share": Decimal("0"),
                "category_ids": sorted(ids_by_group.get(name, set())),
            }
        )
    for g in groups:
        g["share"] = (
            quantize_cents(g["total"] / essentials_total * 100)
            if essentials_total
            else Decimal("0")
        )
    groups.sort(key=lambda g: g["total"], reverse=True)

    income = await income_by_source(session, budget_id, months)
    income_total = Decimal(income["total"])
    avg_income = quantize_cents(income_total / len(month_list)) if month_list else Decimal("0")
    avg_essentials = (
        quantize_cents(essentials_total / len(month_list)) if month_list else Decimal("0")
    )

    return {
        "months": month_list,
        #: The exact window the figures cover, so a drill-down opened from a
        #: bar asks for the same days. The client used to have no way to know
        #: it — and re-deriving "twelve months back, from the first of that
        #: month, to today" on the other side is the same rule written twice.
        "window_start": start_date,
        "window_end": today,
        "groups": groups,
        "avg_monthly_essentials": avg_essentials,
        "avg_monthly_income": avg_income,
        #: What share of take-home is already spoken for before anything
        #: discretionary. None when there is no income on record: a ratio
        #: against zero is not 100%, it is unknown.
        "required_ratio": (
            quantize_cents(essentials_total / income_total * 100) if income_total > 0 else None
        ),
        "basis": basis,
        #: False when nothing is tagged Essential, so the page can say the
        #: figure is every category rather than a chosen few.
        "tagged": basis != "all",
        #: What was in scope and not counted. Tagging a category IS pointing at
        #: it, so this fires whenever the basis is a tag or a Guide binding —
        #: the case the note was written for is exactly "I tagged ten and two
        #: showed up".
        "class_excluded": class_excluded_note(excluded, scoped=basis != "all") or [],
        #: The classes the figures above DO count, so a drill-down opened from
        #: a bar totals what the bar says. Without it a click on Housing lists
        #: the savings transfers too.
        "counted_classes": [c.value for c in COST_OF_LIVING_CLASSES],
    }


async def wishlist_discipline(session: AsyncSession, budget_id: uuid.UUID) -> dict:
    """Cooling-off outcomes across the whole wishlist, open and closed.

    All time, deliberately: the point is the habit, and a habit measured over
    the last twelve months forgets the wish you talked yourself out of two
    years ago. The arithmetic is guide/wishlist.discipline — pure, and tested
    a case at a time.
    """
    from igab.db.models import WishlistItem
    from igab.guide.wishlist import DisciplineInput, discipline

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
            created_at=w.created_at.date(),
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
        "still_open": stats.still_open,
        "resisted_total": stats.resisted_total,
        "bought_total": stats.bought_total,
        "open_total": stats.open_total,
        "avg_days_to_buy": stats.avg_days_to_buy,
        "avg_wish_cost": stats.avg_wish_cost,
        "unplaced": stats.unplaced,
    }
