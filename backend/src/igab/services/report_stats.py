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


def _amortized(monthly: pl.DataFrame, month_grid: list[date]) -> pl.DataFrame:
    """Spread each charge forward over the months until the next one.

    A bill paid twice a year has a steady COST and irregular TIMING, and the
    raw series cannot tell those apart from a category whose cost genuinely
    swings. Spread £600 in January across January to June and £600 in July
    across July to December and the series reads a flat £100 — so what is left
    in the spread is variation in the rate, which is the thing a volatility
    report is for.

    Forward, not backward, and not over the whole window: the months before a
    category's first charge are months we know nothing about, and flattening
    everything to `total / window` would drive every standard deviation to zero
    and make the report say nothing at all.

    The final charge spreads to the end of the window, which is a guess about a
    gap that has not finished yet — so a category whose last charge is recent
    reads a little high. Bounded and deliberate: the alternative is dropping
    the most recent charge, and a report that ignores what just happened is
    worse than one that annualises it early.
    """
    out: list[dict] = []
    key = ["category_id", "category_name", "group_name"]
    for (cid, name, group), frame in monthly.group_by(key, maintain_order=True):
        charges = frame.sort("month").select(["month", "monthly_total"]).rows()
        for i, (month, amount) in enumerate(charges):
            nxt = charges[i + 1][0] if i + 1 < len(charges) else None
            covered = [m for m in month_grid if m >= month and (nxt is None or m < nxt)]
            if not covered:
                continue
            share = amount / len(covered)
            for m in covered:
                out.append(
                    {
                        "category_id": cid,
                        "category_name": name,
                        "group_name": group,
                        "month": m,
                        "monthly_total": share,
                    }
                )
    if not out:
        return monthly.clear()
    return pl.DataFrame(out, schema_overrides={"month": pl.Date, "monthly_total": pl.Float64})


def volatility_stats(rows, month_grid: list[date], *, amortize: bool = False) -> list[dict]:
    """Per-category mean, spread and quartiles over `month_grid`.

    `rows` are `(date, amount, category_id, category_name, group_name)` with
    outflows negative; amounts are reported as magnitudes. Every category in
    `rows` gets an entry for every month in `month_grid`, zero-filled.

    `amortize` spreads each charge forward over the months until the next one,
    so a bill with steady cost and irregular timing reads flat. See
    `_amortized`.

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

    # Held before amortization: `months_included` means months that carried a
    # CHARGE, and spreading one charge across six months must not report six.
    # The client's `filterVolatile` drops anything under two, which is what
    # keeps a single annual charge — flat by construction once spread — out of
    # a report about variation.
    charge_months = (
        monthly.filter(pl.col("monthly_total") != 0.0)
        .group_by("category_id")
        .agg(pl.col("month").count().alias("months_included"))
    )

    if amortize:
        monthly = _amortized(monthly, month_grid)

    grid = pl.DataFrame({"month": month_grid}, schema_overrides={"month": pl.Date})
    cats = monthly.select(["category_id", "category_name", "group_name"]).unique()
    filled = (
        cats.join(grid, how="cross")
        .join(monthly, on=["category_id", "category_name", "group_name", "month"], how="left")
        .with_columns(pl.col("monthly_total").fill_null(0.0))
    )

    # Counted off the filled grid so it can only ever mean "months in THIS
    # window with activity" — off the sparse frame it would also count a month
    # outside the window that happened to carry rows.
    in_window = filled.select("category_id").unique()
    active = charge_months.join(in_window, on="category_id", how="semi")
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
