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
from typing import Any

import polars as pl

from igab.domain.activity_class import CLASS_LABEL, ActivityClass
from igab.domain.amortize import spread_forward


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


def timeline_rows(rows, leg_classes: dict) -> list[dict]:
    """Timeline entries, with a split parent's class taken from its legs.

    The classifier is defined on LEAF rows — a split parent carries no category
    — so a parent fell through every rule to the SPENDING default. A transfer
    to a brokerage itemised into three legs was drawn as a red "Spending" dot.

    One distinct class among the legs IS the parent's class. Anything else is
    honestly mixed: `activity_class` is None and the label reads "Split", which
    is served rather than guessed at. The client used to fall back to the
    amount's sign there, and falling back to the sign is the mislabelling this
    taxonomy exists to end.
    """
    out: list[dict] = []
    for r in rows:
        cls: str | None = r.activity_class
        label = CLASS_LABEL[ActivityClass(cls)]
        if r.is_split:
            found = leg_classes.get(r.id, set())
            if len(found) == 1:
                cls = next(iter(found))
                label = CLASS_LABEL[ActivityClass(cls)]
            else:
                cls = None
                label = "Split"
        out.append(
            {
                "id": str(r.id),
                "date": r.date,
                "amount": Decimal(str(r.amount)),
                "payee_name": r.payee_name,
                "category_name": r.category_name,
                "memo": r.memo,
                "activity_class": cls,
                "activity_label": label,
            }
        )
    return out


#: A payee seen in this many distinct months is treated as recurring.
RECURRING_MONTHS = 3


def payee_breakdown(df: pl.DataFrame, payee_agg: pl.DataFrame, grand_total: Decimal) -> list[dict]:
    """One row per ranked payee: the trend, its biggest envelopes, and whether
    it recurs.

    `payee_agg` is already ranked and capped; `grand_total` spans EVERY payee,
    so `pct` is a share of the period rather than of the rows that survived
    the cap. Passing the truncated frame's own sum here is the defect this
    signature exists to make visible.
    """
    payees: list[dict] = []
    for row in payee_agg.iter_rows(named=True):
        pid = row["payee_id"]
        payee_df = df.filter(pl.col("payee_id") == pid)
        by_month = payee_df.with_columns(pl.col("date").dt.truncate("1mo").alias("month"))

        trend = by_month.group_by("month").agg(pl.col("amount").sum().alias("total")).sort("month")
        monthly_trend = [
            {"month": r["month"], "total": Decimal(str(round(r["total"], 4)))}
            for r in trend.iter_rows(named=True)
        ]

        top_cats = (
            payee_df.filter(pl.col("category_name") != "Uncategorized")
            .group_by("category_name")
            .agg(pl.col("amount").sum().alias("total"))
            .sort("total", descending=True)
            .head(3)
        )
        top_categories = [
            {"category_name": r["category_name"], "total": Decimal(str(round(r["total"], 4)))}
            for r in top_cats.iter_rows(named=True)
        ]

        payees.append(
            {
                "payee_id": pid,
                "payee_name": row["payee_name"],
                "total": Decimal(str(round(row["total"], 4))),
                "count": int(row["count"]),
                "pct": (
                    float(Decimal(str(row["total"])) / grand_total * 100) if grand_total else 0.0
                ),
                "monthly_trend": monthly_trend,
                "top_categories": top_categories,
                "is_recurring": by_month["month"].n_unique() >= RECURRING_MONTHS,
            }
        )
    return payees


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
