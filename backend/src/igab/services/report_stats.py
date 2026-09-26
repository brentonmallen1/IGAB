"""Statistics over a category's monthly spending, without a database.

Split out of `report_service` because the arithmetic is the interesting part
and it needs no session: given the rows and the months they should cover, the
answer is pure. That also keeps `report_service.py` — the one file on the
file-length debt list — shrinking rather than growing.

**A month with nothing spent is a ZERO, not a missing row.** Grouping only the
months that carry rows makes every statistic per-ACTIVE-month, and that is not
what any of these figures claim to be: a bill paid twice a year reported a mean
of its full charge and a standard deviation of zero — "£600 a month, never
varies" — when its monthly cost is a sixth of that and it is the most volatile
thing in the budget.
"""

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, TypedDict

import polars as pl

from igab.domain.activity_class import class_label
from igab.domain.amortize import spread_forward
from igab.domain.concentration import items_to_share
from igab.domain.dates import month_start
from igab.domain.money import quantize_cents
from igab.domain.spending import UNCATEGORIZED, recurring_months, spent


def _amortized(filled: pl.DataFrame) -> pl.DataFrame:
    """`filled` with each category's series spread by `domain.amortize`.

    Months before a category's first charge come back null, which every
    aggregate below skips. See `spread_forward` for the rule.
    """
    key = ["category_id", "category_name", "group_name"]
    parts = [
        frame.with_columns(
            pl.Series("monthly_total", spread_forward(frame["monthly_total"].to_list())).cast(
                pl.Float64
            )
        )
        for _, frame in filled.sort("month").group_by(key, maintain_order=True)
    ]
    return pl.concat(parts) if parts else filled


def volatility_stats(rows, month_grid: list[date], *, amortize: bool = False) -> list[dict]:
    """Per-category mean, spread and quartiles over `month_grid`.

    `rows` are `(date, amount, category_id, category_name, group_name)` with
    outflows negative; amounts are reported as magnitudes. `month_grid` is
    contiguous. Every category with a row inside the grid gets an entry for
    every month in it, zero-filled; rows outside the grid count nowhere.

    `amortize` spreads each charge over the months it pays for, so a bill with
    steady cost and irregular timing reads flat. See `domain.amortize`.

    `months_included` is the count of months with a CHARGE, not the grid
    length — the one figure here that genuinely wants the sparse count, and
    what the client's `filterVolatile` reads. It is held before amortizing:
    spreading one charge across six months must not report six, and the
    client's drop-under-two is what keeps a single annual charge — flat by
    construction once spread — out of a report about variation.
    """
    if not rows:
        return []

    df = pl.DataFrame(
        {
            "date": [r.date for r in rows],
            "amount": [abs(float(r.amount)) for r in rows],
            "category_id": [str(r.category_id) for r in rows],
            "category_name": [r.category_name for r in rows],
            "group_name": [r.group_name for r in rows],
        },
        schema_overrides={"date": pl.Date, "amount": pl.Float64},
    )

    # Cut to the grid FIRST, so nothing below can see a month outside it: not
    # the charge count, and not the spread, which would otherwise carry a
    # charge dated before the window into its first months.
    monthly = (
        df.with_columns(pl.col("date").dt.truncate("1mo").alias("month"))
        .filter(pl.col("month").is_in(month_grid))
        .group_by(["category_id", "category_name", "group_name", "month"])
        .agg(pl.col("amount").sum().alias("monthly_total"))
    )
    charge_months = (
        monthly.filter(pl.col("monthly_total") != 0.0)
        .group_by("category_id")
        .agg(pl.col("month").count().alias("months_included"))
    )

    grid = pl.DataFrame({"month": month_grid}, schema_overrides={"month": pl.Date})
    cats = monthly.select(["category_id", "category_name", "group_name"]).unique()
    filled = (
        cats.join(grid, how="cross")
        .join(monthly, on=["category_id", "category_name", "group_name", "month"], how="left")
        .with_columns(pl.col("monthly_total").fill_null(0.0))
    )
    if amortize:
        filled = _amortized(filled)

    stats = (
        filled.group_by(["category_id", "category_name", "group_name"])
        .agg(
            pl.col("monthly_total").mean().alias("mean"),
            pl.col("monthly_total").std().alias("std_dev"),
            pl.col("monthly_total").min().alias("min_val"),
            pl.col("monthly_total").max().alias("max_val"),
            pl.col("monthly_total").quantile(0.25).alias("p25"),
            pl.col("monthly_total").quantile(0.75).alias("p75"),
        )
        .join(charge_months, on="category_id", how="left")
        .with_columns(pl.col("months_included").fill_null(0))
        .sort("mean", descending=True)
    )

    return [
        {
            "category_id": row["category_id"],
            "category_name": row["category_name"],
            "category_group_name": row["group_name"],
            "mean": Decimal(str(round(row["mean"] or 0, 4))),
            "std_dev": Decimal(str(round(row["std_dev"] or 0, 4))),
            "min_val": Decimal(str(round(row["min_val"] or 0, 4))),
            "max_val": Decimal(str(round(row["max_val"] or 0, 4))),
            "p25": Decimal(str(round(row["p25"] or 0, 4))),
            "p75": Decimal(str(round(row["p75"] or 0, 4))),
            "months_included": int(row["months_included"]),
        }
        for row in stats.iter_rows(named=True)
    ]


#: A baseline this flat is noise, not a pattern: a category that spends the
#: same amount every month would make any deviation an infinite z-score.
ANOMALY_MIN_STD = 5.0
#: Below this, a "300% spike" is a few pounds and nobody wants to hear it.
ANOMALY_MIN_DEVIATION = 25.0
#: Months of history a category needs before it is scored at all, and the
#: smallest baseline any single month may be scored against (one fewer,
#: because a complete month is left out of its own baseline).
ANOMALY_MIN_MONTHS = 6
ANOMALY_MIN_BASELINE = 5


class AnomalyRow(TypedDict):
    category_id: str
    category_name: str
    group_name: str
    month: date
    actual: Decimal
    baseline_mean: Decimal
    z_score: float
    direction: str
    #: True for the month still in progress — see `anomaly_rows`. Required,
    #: never optional: a row that forgot it would read as a closed month.
    partial_month: bool
    history: list[Decimal]


def anomaly_rows(
    rows: Sequence[tuple[str, str, str, date, Decimal]],
    *,
    today: date,
    threshold: float,
) -> list[AnomalyRow]:
    """Category-months whose spending sits `threshold` standard deviations off
    that category's baseline, worst first.

    `rows` are `(category_id, category_name, group_name, month, signed_total)`,
    one per category-month, outflows negative; magnitudes are what is scored.

    **Every baseline is made of COMPLETE months only.** The month in progress
    is never in one, and never leaves one out either: scored as a full
    observation against complete neighbours it made every established category
    read anomalously LOW on the 2nd of every month — a household spending 400
    a month on groceries was told its grocery spending had collapsed, every
    month, for most of the month. A partial month is not a small month.

    **Deliberate divergence: a complete month flags in either direction, the
    month in progress only HIGH.** Spending accumulates, so a month that is not
    over can only understate itself — a LOW verdict on it is the calendar
    talking, not the household. It cannot understate its way *past* the
    baseline, though, so a spike is real the day it happens, and dropping the
    running month entirely hid a 3x grocery month for up to 31 days. Those rows
    carry `partial_month=True`, and every other row carries `False`, so a
    reader is told which figure is still being written.
    """
    running = month_start(today)
    series: dict[str, list[tuple[date, float]]] = {}
    names: dict[str, tuple[str, str]] = {}
    for category_id, category_name, group_name, month, total in rows:
        series.setdefault(category_id, []).append((month, abs(float(total))))
        names[category_id] = (category_name, group_name)

    anomalies: list[AnomalyRow] = []
    for category_id, months in series.items():
        months.sort()
        month_list = [m for m, _ in months]
        totals = [t for _, t in months]
        if sum(1 for m in month_list if m < running) < ANOMALY_MIN_MONTHS:
            continue
        category_name, group_name = names[category_id]

        for i, (month, actual) in enumerate(months):
            baseline = [t for j, t in enumerate(totals) if j != i and month_list[j] < running]
            if len(baseline) < ANOMALY_MIN_BASELINE:
                continue
            mean = sum(baseline) / len(baseline)
            std = (sum((x - mean) ** 2 for x in baseline) / len(baseline)) ** 0.5
            if std < ANOMALY_MIN_STD or abs(actual - mean) < ANOMALY_MIN_DEVIATION:
                continue

            z_score = (actual - mean) / std
            partial = month >= running
            if abs(z_score) < threshold or (partial and z_score < 0):
                continue

            history = totals[max(0, i - 11) : i + 1]
            history = [0.0] * (12 - len(history)) + history
            anomalies.append(
                {
                    "category_id": category_id,
                    "category_name": category_name,
                    "group_name": group_name,
                    "month": month,
                    "actual": quantize_cents(Decimal(str(actual))),
                    "baseline_mean": quantize_cents(Decimal(str(mean))),
                    "z_score": round(z_score, 2),
                    "direction": "high" if z_score > 0 else "low",
                    "partial_month": partial,
                    "history": [quantize_cents(Decimal(str(h))) for h in history],
                }
            )

    anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)
    return anomalies


def timeline_rows(rows, parent_classes: dict) -> list[dict]:
    """Timeline entries, with a split parent's class rolled up from its legs.

    `parent_classes` is `activity_class.rolled_up_classes` for the split
    parents among `rows`; the rule — one distinct class among the legs, else
    None and "Split" — lives there, because the transaction editor's
    classification shows the same row and must say the same thing.
    """
    out: list[dict] = []
    for r in rows:
        cls: str | None = parent_classes.get(r.id) if r.is_split else r.activity_class
        out.append(
            {
                "id": str(r.id),
                "date": r.date,
                "amount": Decimal(str(r.amount)),
                "payee_name": r.payee_name,
                "category_name": r.category_name,
                "memo": r.memo,
                "activity_class": cls,
                "activity_label": class_label(cls),
            }
        )
    return out


#: Monday first, the order `date.weekday()` numbers them and the API serves.
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def payee_rollup(rows: Sequence[Any], window_months: int, limit: int) -> dict:
    """Payee Analysis from `ReportService._spending_query` rows: the `limit`
    largest payees, the total over EVERY payee, how many there were, and how
    many of the largest make up 80% of the spending.

    Net of refunds (`domain.spending.spent`), like every spending figure: a
    returned order lowers its shop's total, so a payee can end a window
    negative, and sorts last.

    **`count` is purchases, not rows.** Split legs share their parent's
    `txn_id`, so a supermarket trip itemised across three envelopes is one
    visit, not three — the count used to read the legs.

    `pct` and the 80% count are measured before the cap. The total and every
    share were once computed from the top 25 alone, so "Total Spent" was a
    subtotal and every share was inflated against it; and the Pareto card
    looked for 80% in 25 rows against a total over every payee, so it
    vanished for exactly the diffuse spending it exists to point out.

    Recurring is relative to the window (`domain.spending.recurring_months`);
    the threshold is served so the page can state it.
    """
    by_payee: dict[Any, dict] = {}
    for r in rows:
        p = by_payee.setdefault(
            r.payee_id,
            {
                "name": r.payee_name or "Unknown",
                "rows": [],
                "txns": set(),
                "months": {},
                "cats": {},
            },
        )
        p["rows"].append(r.amount)
        p["txns"].add(r.txn_id)
        p["months"].setdefault(month_start(r.date), []).append(r.amount)
        if r.name is not None:
            p["cats"].setdefault(r.name, []).append(r.amount)
    totals = {pid: spent(p["rows"]) for pid, p in by_payee.items()}
    ranked = sorted(by_payee, key=lambda pid: totals[pid], reverse=True)
    grand_total = sum(totals.values(), Decimal("0"))
    need = recurring_months(window_months)

    payees: list[dict] = []
    for pid in ranked[:limit]:
        p = by_payee[pid]
        cats = sorted(
            ((name, spent(amounts)) for name, amounts in p["cats"].items()),
            key=lambda c: c[1],
            reverse=True,
        )[:3]
        payees.append(
            {
                "payee_id": str(pid),
                "payee_name": p["name"],
                "total": quantize_cents(totals[pid]),
                "count": len(p["txns"]),
                "pct": float(totals[pid] / grand_total * 100) if grand_total > 0 else 0.0,
                "monthly_trend": [
                    {"month": m, "total": quantize_cents(spent(amounts))}
                    for m, amounts in sorted(p["months"].items())
                ],
                "top_categories": [
                    {"category_name": name, "total": quantize_cents(total)} for name, total in cats
                ],
                "is_recurring": need is not None and len(p["months"]) >= need,
            }
        )
    return {
        "payees": payees,
        "total": quantize_cents(grand_total),
        "payee_count": len(by_payee),
        "payees_to_80pct": items_to_share([totals[pid] for pid in ranked]),
        "recurring_min_months": need,
    }


def weekday_rollup(rows: Sequence[Any], weekdays: Sequence[int]) -> list[dict]:
    """Day Patterns from `ReportService._spending_query` rows: each weekday's
    net spending, its purchases, and its average per calendar day.

    `weekdays` is how many of each weekday the window holds
    (`domain.dates.weekday_counts`), and **it is the divisor**: a quiet
    Saturday is a Saturday with nothing spent, not a Saturday that did not
    happen. The chart once served the average per transaction, which says
    nothing about which day costs the most — a week of one big shop and six
    coffees made the shop's day look extravagant and the coffee days frugal
    in exactly the wrong proportion. None where the window holds no such
    weekday.
    """
    amounts: list[list[Decimal]] = [[] for _ in range(7)]
    txns: list[set] = [set() for _ in range(7)]
    for r in rows:
        dow = r.date.weekday()
        amounts[dow].append(r.amount)
        txns[dow].add(r.txn_id)
    out = []
    for i in range(7):
        total = spent(amounts[i])
        out.append(
            {
                "day_of_week": i,
                "day_name": DAY_NAMES[i],
                "total": quantize_cents(total),
                "count": len(txns[i]),
                "weekdays": weekdays[i],
                "avg_per_day": quantize_cents(total / weekdays[i]) if weekdays[i] else None,
            }
        )
    return out


def category_month_grid(rows: Sequence[Any], top: int) -> dict:
    """Seasonality from `ReportService._spending_query` rows: net spending per
    category per month, and the `top` categories by net total over the window.

    Uncategorized spending is a row of its own (id None) rather than missing:
    the heatmap and Spending Trends read one row set, and a household whose
    unfiled purchases spike in December should see that spike. `category_count`
    is every category that spent, so the page can say "top 20 of 34".
    """
    cells: dict[tuple[Any, date], list[Decimal]] = {}
    names: dict[Any, str] = {}
    for r in rows:
        names[r.id] = r.name or UNCATEGORIZED
        cells.setdefault((r.id, month_start(r.date)), []).append(r.amount)
    net = {key: spent(amounts) for key, amounts in cells.items()}
    by_cat: dict[Any, Decimal] = {}
    for (cid, _month), total in net.items():
        by_cat[cid] = by_cat.get(cid, Decimal("0")) + total
    ranked = sorted(by_cat, key=lambda cid: by_cat[cid], reverse=True)
    return {
        "cells": [
            {
                "category_id": cid,
                "category_name": names[cid],
                "month": month,
                "total": quantize_cents(total),
            }
            for (cid, month), total in sorted(net.items(), key=lambda kv: (kv[0][1], -kv[1]))
        ],
        "categories": [{"id": cid, "name": names[cid]} for cid in ranked[:top]],
        "category_count": len(ranked),
    }


def balance_sheet(
    accounts: Sequence[Any],
    balances: dict[uuid.UUID, tuple[int, list[Decimal]]],
    i: int,
    stated_assets: Decimal,
    unmanaged: Decimal,
) -> dict:
    """Net worth at the `i`-th cutoff of `balances`
    (`AccountRepository.balances_through`), given the stated asset values and
    unmanaged debts standing then.

    `accounts` carries id, name, account_type and classification. Every
    account counts — off-budget assets and loans included, closed ones too:
    on_budget scopes the envelope math, never the balance sheet.

    Sign-preserving identity math, keyed on classification: an overdrawn
    checking account NETS ASSETS DOWN (the old bucketing counted it in
    neither pile) and an overpaid credit card nets liabilities down.
    net_worth == assets − liabilities always. Stated asset values and
    unmanaged debts join their side without appearing in any account tile,
    which is why both are served beside the totals.

    An account with no row yet is absent from the stack rather than drawn at
    zero — an account that opens in March is not a zero tile in February.
    """
    snapshots = []
    total_assets = stated_assets
    liability_balances = Decimal("0")
    for account in accounts:
        first, running = balances.get(account.id, (i + 1, []))
        if i < first:
            continue
        classification = account.classification or "asset"
        snapshots.append(
            {
                "account_id": str(account.id),
                "account_name": account.name,
                "account_type": account.account_type,
                "classification": classification,
                "balance": running[i],
            }
        )
        if classification == "liability":
            liability_balances += running[i]
        else:
            total_assets += running[i]
    total_liabilities = unmanaged - liability_balances
    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "unmanaged_liability_total": unmanaged,
        "asset_value_total": stated_assets,
        "accounts": snapshots,
    }
