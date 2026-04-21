import io
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import polars as pl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, CategoryGroup, Transaction


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def spending_by_category(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> tuple[list[dict], Decimal]:
        q = (
            select(
                Category.id,
                Category.name,
                CategoryGroup.name.label("group_name"),
                Transaction.amount,
            )
            .join(Transaction, Transaction.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.amount < 0,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.parent_transaction_id.is_(None),
            )
        )
        result = await self.session.execute(q)
        rows = result.all()

        if not rows:
            return [], Decimal("0")

        df = pl.DataFrame(
            {
                "id": [str(r.id) for r in rows],
                "name": [r.name for r in rows],
                "group_name": [r.group_name for r in rows],
                "amount": [float(r.amount) for r in rows],
            }
        )

        agg = (
            df.group_by(["id", "name", "group_name"])
            .agg(pl.col("amount").sum().alias("total"))
            .with_columns(pl.col("total").abs())
            .sort("total", descending=True)
        )

        grand_total = agg["total"].sum()
        categories = [
            {
                "id": row["id"],
                "name": row["name"],
                "group_name": row["group_name"],
                "total": Decimal(str(row["total"])),
                "pct": float(row["total"] / grand_total * 100) if grand_total else 0.0,
            }
            for row in agg.iter_rows(named=True)
        ]
        return categories, Decimal(str(grand_total))

    async def income_vs_expense(self, budget_id: uuid.UUID, months: int = 12) -> list[dict]:
        today = date.today()
        first_of_month = today.replace(day=1)
        start = _subtract_months(first_of_month, months - 1)

        q = select(Transaction.date, Transaction.amount).where(
            Transaction.budget_id == budget_id,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.date >= start,
            Transaction.date <= today,
            Transaction.parent_transaction_id.is_(None),
        )
        rows = (await self.session.execute(q)).all()

        if not rows:
            # Return zeroed months
            return [
                {
                    "month": _subtract_months(first_of_month, i),
                    "income": Decimal("0"),
                    "expenses": Decimal("0"),
                    "net": Decimal("0"),
                }
                for i in range(months - 1, -1, -1)
            ]

        df = pl.DataFrame(
            {
                "date": [r[0] for r in rows],
                "amount": [float(r[1]) for r in rows],
            },
            schema={"date": pl.Date, "amount": pl.Float64},
        )

        monthly = (
            df.with_columns(pl.col("date").dt.truncate("1mo").alias("month"))
            .group_by("month")
            .agg(
                pl.col("amount").filter(pl.col("amount") > 0).sum().alias("income"),
                pl.col("amount").filter(pl.col("amount") < 0).sum().abs().alias("expenses"),
                pl.col("amount").sum().alias("net"),
            )
            .sort("month")
        )

        month_map = {row["month"]: row for row in monthly.iter_rows(named=True)}

        results = []
        for i in range(months - 1, -1, -1):
            month_start = _subtract_months(first_of_month, i)
            if month_start in month_map:
                r = month_map[month_start]
                results.append(
                    {
                        "month": month_start,
                        "income": Decimal(str(r["income"] or 0)),
                        "expenses": Decimal(str(r["expenses"] or 0)),
                        "net": Decimal(str(r["net"] or 0)),
                    }
                )
            else:
                results.append(
                    {
                        "month": month_start,
                        "income": Decimal("0"),
                        "expenses": Decimal("0"),
                        "net": Decimal("0"),
                    }
                )
        return results

    async def export_transactions(
        self,
        budget_id: uuid.UUID,
        start_date: date | None,
        end_date: date | None,
        fmt: str,
    ) -> tuple[str, str]:
        q = (
            select(
                Transaction.id,
                Transaction.date,
                Transaction.amount,
                Transaction.memo,
                Transaction.cleared,
                Transaction.approved,
            )
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
            .order_by(Transaction.date.desc())
        )
        if start_date:
            q = q.where(Transaction.date >= start_date)
        if end_date:
            q = q.where(Transaction.date <= end_date)

        rows = (await self.session.execute(q)).all()

        df = pl.DataFrame(
            {
                "id": [str(r.id) for r in rows],
                "date": [r.date for r in rows],
                "amount": [str(r.amount) for r in rows],
                "memo": [r.memo or "" for r in rows],
                "cleared": [r.cleared for r in rows],
                "approved": [r.approved for r in rows],
            },
            schema={
                "id": pl.String,
                "date": pl.Date,
                "amount": pl.String,
                "memo": pl.String,
                "cleared": pl.String,
                "approved": pl.Boolean,
            },
        )

        if fmt == "json":
            data = [
                {
                    "id": row["id"],
                    "date": row["date"].isoformat(),
                    "amount": row["amount"],
                    "memo": row["memo"],
                    "cleared": row["cleared"],
                    "approved": row["approved"],
                }
                for row in df.iter_rows(named=True)
            ]
            return json.dumps(data, indent=2), "application/json"

        buf = io.BytesIO()
        df.write_csv(buf)
        return buf.getvalue().decode("utf-8"), "text/csv"


def _subtract_months(d: date, months: int) -> date:
    month = d.month - months
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return d.replace(year=year, month=month, day=1)


def _last_day(d: date) -> date:
    m = d.month + 1
    y = d.year
    if m > 12:
        m = 1
        y += 1
    return date(y, m, 1) - timedelta(days=1)
