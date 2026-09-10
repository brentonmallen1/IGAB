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

from datetime import date
from decimal import Decimal

import polars as pl


def volatility_stats(rows, month_grid: list[date]) -> list[dict]:
    """Per-category mean, spread and quartiles over `month_grid`.

    `rows` are `(date, amount, category_id, category_name, group_name)` with
    outflows negative; amounts are reported as magnitudes. Every category in
    `rows` gets an entry for every month in `month_grid`, zero-filled.

    `months_included` is the count of months with ACTIVITY, not the grid
    length — the one figure here that genuinely wants the sparse count, and
    what the client's `filterVolatile` reads. It is counted off the filled grid
    so it can only ever mean "months in THIS window with activity"; counted off
    the sparse frame it would also count a month outside the window that
    happened to carry rows.
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

    monthly = (
        df.with_columns(pl.col("date").dt.truncate("1mo").alias("month"))
        .group_by(["category_id", "category_name", "group_name", "month"])
        .agg(pl.col("amount").sum().alias("monthly_total"))
    )

    grid = pl.DataFrame({"month": month_grid}, schema_overrides={"month": pl.Date})
    cats = monthly.select(["category_id", "category_name", "group_name"]).unique()
    filled = (
        cats.join(grid, how="cross")
        .join(monthly, on=["category_id", "category_name", "group_name", "month"], how="left")
        .with_columns(pl.col("monthly_total").fill_null(0.0))
    )

    active = (
        filled.filter(pl.col("monthly_total") != 0.0)
        .group_by("category_id")
        .agg(pl.col("month").count().alias("months_included"))
    )
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
        .join(active, on="category_id", how="left")
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
