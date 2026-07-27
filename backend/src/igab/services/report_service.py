import io
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import polars as pl
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    Account,
    BudgetAssignment,
    Category,
    CategoryGroup,
    Liability,
    LiabilityBalanceSnapshot,
    Payee,
    Transaction,
)

# CASH_FLOW_ROW: plain rows plus categorized transfer legs (spending
# transfers to off-budget accounts count as real income/expense; internal
# uncategorized transfers never do). For category-scoped queries the
# predicate is vacuously true, keeping one uniform rule.
from igab.repositories.txn_filters import CASH_FLOW_ROW, LEAF, NOT_DELETED, PARENT_ROW, POSTED


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── Existing ─────────────────────────────────────────────────────────────

    async def spending_by_category(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        category_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
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
                NOT_DELETED,
                POSTED,
                Transaction.amount < 0,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                LEAF,
                CASH_FLOW_ROW,
            )
        )
        if category_ids:
            q = q.where(Transaction.category_id.in_(category_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
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
            NOT_DELETED,
            POSTED,
            Transaction.date >= start,
            Transaction.date <= today,
            PARENT_ROW,
            CASH_FLOW_ROW,
        )
        rows = (await self.session.execute(q)).all()

        if not rows:
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
            schema_overrides={"date": pl.Date, "amount": pl.Float64},
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

    # ─── Dashboard ────────────────────────────────────────────────────────────

    async def dashboard_metrics(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> dict:
        today = date.today()
        prev_start = (
            start_date.replace(month=start_date.month - 1)
            if start_date.month > 1
            else start_date.replace(year=start_date.year - 1, month=12)
        )
        prev_end = start_date - timedelta(days=1)

        # All posted rows for the budget: parent rows feed money flows
        # (net worth, income/expenses, burn); leaf rows feed the category
        # breakdown (split children carry the categories).
        q = select(
            Transaction.id,
            Transaction.date,
            Transaction.amount,
            Transaction.category_id,
            Transaction.payee_id,
            Transaction.transfer_id,
            Transaction.account_id,
            Transaction.is_split,
            Transaction.parent_transaction_id,
        ).where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
        )
        all_txns = (await self.session.execute(q)).all()

        # Account info for on_budget classification
        acct_q = select(
            Account.id, Account.on_budget, Account.account_type, Account.is_deleted
        ).where(
            Account.budget_id == budget_id,
            Account.is_deleted == False,  # noqa: E712
        )
        accounts = {str(r.id): r for r in (await self.session.execute(acct_q)).all()}

        # Category info for spending
        cat_q = (
            select(Category.id, Category.name, CategoryGroup.name.label("group_name"))
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Category.budget_id == budget_id,
                Category.is_deleted == False,  # noqa: E712
                CategoryGroup.is_deleted == False,  # noqa: E712
                CategoryGroup.is_system == False,  # noqa: E712
            )
        )
        cats = {str(r.id): r for r in (await self.session.execute(cat_q)).all()}

        if not all_txns:
            return _empty_dashboard()

        df = pl.DataFrame(
            {
                "id": [str(r.id) for r in all_txns],
                "date": [r.date for r in all_txns],
                "amount": [float(r.amount) for r in all_txns],
                "account_id": [str(r.account_id) for r in all_txns],
                "category_id": [str(r.category_id) if r.category_id else "" for r in all_txns],
                "is_transfer": [r.transfer_id is not None for r in all_txns],
                "is_split": [r.is_split for r in all_txns],
                "is_parent_row": [r.parent_transaction_id is None for r in all_txns],
            },
            schema_overrides={
                "date": pl.Date,
                "amount": pl.Float64,
                "is_transfer": pl.Boolean,
                "is_split": pl.Boolean,
                "is_parent_row": pl.Boolean,
            },
        )

        on_budget_ids = {aid for aid, a in accounts.items() if a.on_budget}
        df = df.with_columns(
            pl.col("account_id").is_in(list(on_budget_ids)).alias("on_budget"),
            # Cash-flow rows: non-transfers plus CATEGORIZED transfer legs
            # (spending transfers to off-budget accounts)
            (~pl.col("is_transfer") | (pl.col("category_id") != "")).alias("cash_flow"),
        )

        # Parent rows carry the account-level amounts (split children would
        # double-count); leaf rows carry the categories.
        pdf = df.filter(pl.col("is_parent_row"))

        # Net worth = sum of all on_budget account transactions (transfers cancel each other)
        net_worth = Decimal(
            str(pdf.filter(pl.col("on_budget")).select(pl.col("amount").sum()).item() or 0)
        )

        # Previous net worth: sum up to start_date
        net_worth_prev = Decimal(
            str(
                pdf.filter(pl.col("on_budget") & (pl.col("date") < start_date))
                .select(pl.col("amount").sum())
                .item()
                or 0
            )
        )

        # Unmanaged liabilities reduce net worth here exactly as they do in
        # net_worth_history — the dashboard card and the report headline
        # must never disagree.
        unmanaged_now, unmanaged_series = await self._unmanaged_liabilities(budget_id)
        net_worth -= unmanaged_now
        net_worth_prev -= self._unmanaged_total_at(unmanaged_series, prev_end)

        # Cash-flow expenses only
        expenses_df = pdf.filter(pl.col("cash_flow") & (pl.col("amount") < 0))

        # Current period income/expenses
        period_df = pdf.filter(
            (pl.col("date") >= start_date) & (pl.col("date") <= end_date) & pl.col("cash_flow")
        )
        income_this = Decimal(
            str(period_df.filter(pl.col("amount") > 0).select(pl.col("amount").sum()).item() or 0)
        )
        expenses_this = Decimal(
            str(
                period_df.filter(pl.col("amount") < 0).select(pl.col("amount").abs().sum()).item()
                or 0
            )
        )

        # Previous period expenses
        prev_df = pdf.filter(
            (pl.col("date") >= prev_start) & (pl.col("date") <= prev_end) & pl.col("cash_flow")
        )
        expenses_prev = Decimal(
            str(
                prev_df.filter(pl.col("amount") < 0).select(pl.col("amount").abs().sum()).item()
                or 0
            )
        )

        # Burn rates (annualized to monthly)
        thirty_ago = today - timedelta(days=30)
        ninety_ago = today - timedelta(days=90)
        burn_30 = Decimal(
            str(
                expenses_df.filter(pl.col("date") >= thirty_ago)
                .select(pl.col("amount").abs().sum())
                .item()
                or 0
            )
        )
        burn_90_raw = Decimal(
            str(
                expenses_df.filter(pl.col("date") >= ninety_ago)
                .select(pl.col("amount").abs().sum())
                .item()
                or 0
            )
        )
        burn_90 = burn_90_raw / 3  # Monthly equivalent

        # Savings rate
        savings_rate = (
            float((income_this - expenses_this) / income_this) if income_this > 0 else 0.0
        )

        # Days until zero
        daily_burn = float(burn_30) / 30 if burn_30 > 0 else 0
        days_until_zero: float | None = (
            float(net_worth) / daily_burn if daily_burn > 0 and net_worth > 0 else None
        )

        # Top 3 categories in current period — leaf rows so splits count;
        # categorized transfer legs (off-budget spending) count too
        cat_df = df.filter(
            ~pl.col("is_split")
            & (pl.col("amount") < 0)
            & (pl.col("date") >= start_date)
            & (pl.col("date") <= end_date)
            & (pl.col("category_id") != "")
        )
        top_cats: list[dict] = []
        if not cat_df.is_empty():
            cat_agg = (
                cat_df.group_by("category_id")
                .agg(pl.col("amount").abs().sum().alias("total"))
                .sort("total", descending=True)
                .head(3)
            )
            for row in cat_agg.iter_rows(named=True):
                cat_info = cats.get(row["category_id"])
                if cat_info:
                    top_cats.append(
                        {
                            "id": row["category_id"],
                            "name": cat_info.name,
                            "group_name": cat_info.group_name,
                            "total": Decimal(str(row["total"])),
                        }
                    )

        return {
            "net_worth": net_worth,
            "net_worth_prev": net_worth_prev,
            "burn_rate_30": burn_30,
            "burn_rate_90": burn_90,
            "savings_rate": savings_rate,
            "days_until_zero": days_until_zero,
            "income_this_month": income_this,
            "expenses_this_month": expenses_this,
            "expenses_prev_month": expenses_prev,
            "top_categories": top_cats,
        }

    # ─── Net Worth History ────────────────────────────────────────────────────

    async def _unmanaged_liabilities(
        self, budget_id: uuid.UUID
    ) -> tuple[Decimal, dict[uuid.UUID, list[tuple[date, Decimal]]]]:
        """Current total owed on unmanaged liabilities, plus each liability's
        snapshot series for historical step-function lookups.

        Unmanaged liabilities have no Account — without this bucket they'd
        silently vanish from net worth. Managed liabilities are already
        counted through their linked account and must NOT be added here
        (that would double-count them)."""
        liabilities = (
            await self.session.execute(
                select(Liability.id, Liability.manual_balance).where(
                    Liability.budget_id == budget_id,
                    Liability.is_deleted == False,  # noqa: E712
                    Liability.linked_account_id.is_(None),
                )
            )
        ).all()
        if not liabilities:
            return Decimal("0"), {}
        current_total = sum(
            (max(Decimal("0"), item.manual_balance or Decimal("0")) for item in liabilities),
            Decimal("0"),
        )
        liability_ids = [item.id for item in liabilities]
        snaps = (
            await self.session.execute(
                select(
                    LiabilityBalanceSnapshot.liability_id,
                    LiabilityBalanceSnapshot.date,
                    LiabilityBalanceSnapshot.balance,
                )
                .where(LiabilityBalanceSnapshot.liability_id.in_(liability_ids))
                .order_by(LiabilityBalanceSnapshot.date)
            )
        ).all()
        series: dict[uuid.UUID, list[tuple[date, Decimal]]] = {item.id: [] for item in liabilities}
        for s in snaps:
            series[s.liability_id].append((s.date, s.balance))
        return current_total, series

    @staticmethod
    def _unmanaged_total_at(
        series: dict[uuid.UUID, list[tuple[date, Decimal]]], as_of: date
    ) -> Decimal:
        """Step function: each liability's latest snapshot on or before as_of.
        A liability with no snapshot yet contributes nothing — before tracking
        began there is no honest number to show."""
        total = Decimal("0")
        for points in series.values():
            latest: Decimal | None = None
            for point_date, balance in points:
                if point_date <= as_of:
                    latest = balance
                else:
                    break
            if latest is not None and latest > 0:
                total += latest
        return total

    async def net_worth_history(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
    ) -> list[dict]:
        acct_q = select(Account.id, Account.name, Account.account_type, Account.on_budget).where(
            Account.budget_id == budget_id,
            Account.is_deleted == False,  # noqa: E712
            Account.on_budget == True,  # noqa: E712
        )
        accounts = (await self.session.execute(acct_q)).all()
        if not accounts:
            return []

        unmanaged_now, unmanaged_series = await self._unmanaged_liabilities(budget_id)
        account_map = {str(a.id): a for a in accounts}

        q = select(Transaction.date, Transaction.amount, Transaction.account_id).where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            PARENT_ROW,
            Transaction.account_id.in_([a.id for a in accounts]),
        )
        txns = (await self.session.execute(q)).all()

        today = date.today()
        first_of_month = today.replace(day=1)

        if not txns:
            points = []
            for i in range(months - 1, -1, -1):
                month_start = _subtract_months(first_of_month, i)
                unmanaged = (
                    unmanaged_now
                    if i == 0
                    else self._unmanaged_total_at(unmanaged_series, _last_day(month_start))
                )
                points.append(
                    {
                        "date": month_start,
                        "total_assets": Decimal("0"),
                        "total_liabilities": unmanaged,
                        "net_worth": -unmanaged,
                        "unmanaged_liability_total": unmanaged,
                        "accounts": [],
                    }
                )
            return points

        df = pl.DataFrame(
            {
                "date": [r.date for r in txns],
                "amount": [float(r.amount) for r in txns],
                "account_id": [str(r.account_id) for r in txns],
                "account_name": [account_map[str(r.account_id)].name for r in txns],
                "account_type": [account_map[str(r.account_id)].account_type for r in txns],
            },
            schema_overrides={"date": pl.Date, "amount": pl.Float64},
        )

        results = []
        for i in range(months - 1, -1, -1):
            month_start = _subtract_months(first_of_month, i)
            month_end = _last_day(month_start)
            month_df = df.filter(pl.col("date") <= month_end)

            acct_balances = month_df.group_by(["account_id", "account_name", "account_type"]).agg(
                pl.col("amount").sum().alias("balance")
            )

            snapshots = []
            total_assets = Decimal("0")
            total_liabilities = Decimal("0")

            for row in acct_balances.iter_rows(named=True):
                bal = Decimal(str(row["balance"]))
                snapshots.append(
                    {
                        "account_id": row["account_id"],
                        "account_name": row["account_name"],
                        "account_type": row["account_type"],
                        "balance": bal,
                    }
                )
                if row["account_type"] in ("checking", "savings", "tracking"):
                    if bal > 0:
                        total_assets += bal
                elif row["account_type"] in ("credit_card", "loan"):
                    if bal < 0:
                        total_liabilities += abs(bal)
                    else:
                        total_assets += bal

            # Unmanaged debts join the liability side: current total for the
            # current month, snapshot step-function for history.
            unmanaged = (
                unmanaged_now if i == 0 else self._unmanaged_total_at(unmanaged_series, month_end)
            )
            total_liabilities += unmanaged

            results.append(
                {
                    "date": month_start,
                    "total_assets": total_assets,
                    "total_liabilities": total_liabilities,
                    "net_worth": total_assets - total_liabilities,
                    "unmanaged_liability_total": unmanaged,
                    "accounts": snapshots,
                }
            )

        return results

    # ─── Account Composition ─────────────────────────────────────────────────

    async def account_composition(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
    ) -> list[dict]:
        history = await self.net_worth_history(budget_id, months)
        results = []
        for point in history:
            by_type: dict[str, Decimal] = {
                "checking": Decimal("0"),
                "savings": Decimal("0"),
                "credit_card": Decimal("0"),
                "loan": Decimal("0"),
                "tracking": Decimal("0"),
            }
            for snap in point["accounts"]:
                t = snap["account_type"]
                if t in by_type:
                    by_type[t] = by_type[t] + snap["balance"]
            results.append({"date": point["date"], **by_type})
        return results

    # ─── Burn Rate ────────────────────────────────────────────────────────────

    async def burn_rate(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
    ) -> list[dict]:
        today = date.today()
        first_of_month = today.replace(day=1)
        start = _subtract_months(first_of_month, months - 1 + 3)  # extra months for rolling

        q = select(Transaction.date, Transaction.amount).where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            Transaction.amount < 0,
            Transaction.date >= start,
            Transaction.date <= today,
            PARENT_ROW,
            CASH_FLOW_ROW,
        )
        txns = (await self.session.execute(q)).all()

        results = []
        for i in range(months - 1, -1, -1):
            month_start = _subtract_months(first_of_month, i)
            month_end = _last_day(month_start)

            # 30-day: sum expenses in 30 days ending at month_end
            d30 = month_end - timedelta(days=29)
            # 90-day: sum expenses in 90 days ending at month_end, divided by 3
            d90 = month_end - timedelta(days=89)

            r30 = sum(abs(float(r.amount)) for r in txns if d30 <= r.date <= month_end)
            r90 = sum(abs(float(r.amount)) for r in txns if d90 <= r.date <= month_end) / 3

            results.append(
                {
                    "date": month_start,
                    "rolling_30": Decimal(str(round(r30, 4))),
                    "rolling_90": Decimal(str(round(r90, 4))),
                }
            )

        return results

    # ─── Cash Flow Sankey ─────────────────────────────────────────────────────

    async def cash_flow_sankey(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        mode: str = "spent",  # "spent" or "budgeted"
        account_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        if mode == "budgeted":
            return await self._cash_flow_budgeted(budget_id, start_date, end_date)
        return await self._cash_flow_spent(budget_id, start_date, end_date, account_ids)

    async def _cash_flow_budgeted(
        self, budget_id: uuid.UUID, start_date: date, end_date: date
    ) -> dict:
        """Sankey based on budget assignments (no payee data)."""
        months = _months_in_range(start_date, end_date)

        # Get budget assignments with category/group info
        q = (
            select(
                BudgetAssignment.category_id,
                BudgetAssignment.assigned,
                Category.name.label("category_name"),
                CategoryGroup.id.label("group_id"),
                CategoryGroup.name.label("group_name"),
            )
            .join(Category, BudgetAssignment.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                BudgetAssignment.budget_id == budget_id,
                BudgetAssignment.month.in_(months),
                Category.is_deleted == False,  # noqa: E712
                CategoryGroup.is_deleted == False,  # noqa: E712
                CategoryGroup.is_system == False,  # noqa: E712
            )
        )
        rows = (await self.session.execute(q)).all()

        # Get total income from transactions
        income_q = select(func.sum(Transaction.amount)).where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.amount > 0,
            PARENT_ROW,
            CASH_FLOW_ROW,
        )
        total_income = (await self.session.execute(income_q)).scalar() or Decimal("0")

        if not rows:
            return {
                "nodes": [],
                "links": [],
                "total_income": total_income,
                "total_expense": Decimal("0"),
                "category_payees": {},
                "group_categories": {},
            }

        # Aggregate by category and group
        group_totals: dict[str, float] = {}
        cat_totals: dict[str, float] = {}
        cat_to_group: dict[str, tuple[str, str]] = {}
        cat_names: dict[str, str] = {}

        for r in rows:
            if r.assigned <= 0:
                continue
            cat_id = str(r.category_id)
            gid = str(r.group_id)
            gname = r.group_name or "Unknown"

            group_totals[gid] = group_totals.get(gid, 0) + float(r.assigned)
            cat_totals[cat_id] = cat_totals.get(cat_id, 0) + float(r.assigned)
            cat_to_group[cat_id] = (gid, gname)
            cat_names[cat_id] = r.category_name or cat_id

        total_budgeted = sum(group_totals.values())

        nodes: list[dict] = []
        links: list[dict] = []
        node_ids: dict[str, int] = {}

        def get_node(nid: str, name: str, ntype: str) -> int:
            if nid not in node_ids:
                node_ids[nid] = len(nodes)
                nodes.append({"id": nid, "name": name, "type": ntype})
            return node_ids[nid]

        get_node("__budget__", "Budget", "budget")

        # Groups
        for gid, total in sorted(group_totals.items(), key=lambda x: -x[1]):
            gname = next((v[1] for k, v in cat_to_group.items() if v[0] == gid), gid)
            get_node(f"g_{gid}", gname, "category_group")
            links.append(
                {
                    "source": "__budget__",
                    "target": f"g_{gid}",
                    "value": Decimal(str(round(total, 4))),
                }
            )

        # Categories
        group_to_cats: dict[str, list[str]] = {}
        for cat_id, (gid, _) in cat_to_group.items():
            group_to_cats.setdefault(gid, []).append(cat_id)
            get_node(f"c_{cat_id}", cat_names.get(cat_id, cat_id), "category")
            links.append(
                {
                    "source": f"g_{gid}",
                    "target": f"c_{cat_id}",
                    "value": Decimal(str(round(cat_totals[cat_id], 4))),
                }
            )

        # Group categories for tooltip
        group_categories: dict[str, list[dict]] = {}
        for gid, cats in group_to_cats.items():
            top10 = sorted(cats, key=lambda c: -cat_totals.get(c, 0))[:10]
            group_categories[f"g_{gid}"] = [
                {"name": cat_names.get(c, c), "total": Decimal(str(round(cat_totals.get(c, 0), 4)))}
                for c in top10
            ]

        return {
            "nodes": [{"id": n["id"], "name": n["name"], "type": n["type"]} for n in nodes],
            "links": links,
            "total_income": total_income,
            "total_expense": Decimal(str(round(total_budgeted, 4))),
            "category_payees": {},  # No payees in budgeted mode
            "group_categories": group_categories,
        }

    async def _cash_flow_spent(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        account_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        """Sankey based on actual transactions (includes payee data)."""
        q = (
            select(
                Transaction.id,
                Transaction.amount,
                Transaction.payee_id,
                Transaction.category_id,
                Transaction.transfer_id,
                Transaction.is_split,
                Transaction.parent_transaction_id,
                Payee.name.label("payee_name"),
                Category.name.label("category_name"),
                CategoryGroup.id.label("group_id"),
                CategoryGroup.name.label("group_name"),
            )
            .outerjoin(Payee, Transaction.payee_id == Payee.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .outerjoin(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                CASH_FLOW_ROW,
            )
        )
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        rows = (await self.session.execute(q)).all()

        if not rows:
            return {
                "nodes": [],
                "links": [],
                "total_income": Decimal("0"),
                "total_expense": Decimal("0"),
                "category_payees": {},
                "group_categories": {},
            }

        # Income at parent level (cash-flow view); expense category flows at
        # leaf level so split children reach their categories.
        income_rows = [r for r in rows if r.amount > 0 and r.parent_transaction_id is None]
        expense_rows = [r for r in rows if r.amount < 0 and not r.is_split]

        total_income = Decimal(str(sum(float(r.amount) for r in income_rows)))
        total_expense = Decimal(str(abs(sum(float(r.amount) for r in expense_rows))))

        nodes: list[dict] = []
        links: list[dict] = []
        node_ids: dict[str, int] = {}

        def get_node(nid: str, name: str, ntype: str) -> int:
            if nid not in node_ids:
                node_ids[nid] = len(nodes)
                nodes.append({"id": nid, "name": name, "type": ntype})
            return node_ids[nid]

        get_node("__budget__", "Budget", "budget")

        # Income: payees -> budget
        income_by_payee: dict[str, float] = {}
        for r in income_rows:
            pname = r.payee_name or "Unknown Income"
            pid = f"inc_{r.payee_id or pname}"
            income_by_payee[pid] = income_by_payee.get(pid, 0) + float(r.amount)

        for pid, total in sorted(income_by_payee.items(), key=lambda x: -x[1])[:15]:
            pname = next(
                (
                    r.payee_name or "Unknown"
                    for r in income_rows
                    if f"inc_{r.payee_id or r.payee_name}" == pid
                ),
                pid,
            )
            get_node(pid, pname, "income_payee")
            links.append(
                {
                    "source": pid,
                    "target": "__budget__",
                    "value": Decimal(str(round(total, 4))),
                }
            )

        # Expenses: budget -> category group -> category -> top payees
        group_totals: dict[str, float] = {}
        cat_totals: dict[str, float] = {}
        cat_to_group: dict[str, tuple[str, str]] = {}
        payee_by_cat: dict[str, dict[str, float]] = {}

        for r in expense_rows:
            if not r.category_id:
                continue
            cat_id = str(r.category_id)
            gid = str(r.group_id) if r.group_id else "__uncategorized__"
            gname = r.group_name or "Uncategorized"

            group_totals[gid] = group_totals.get(gid, 0) + abs(float(r.amount))
            cat_totals[cat_id] = cat_totals.get(cat_id, 0) + abs(float(r.amount))
            cat_to_group[cat_id] = (gid, gname)

            pname = r.payee_name or "Unknown"
            pid = str(r.payee_id) if r.payee_id else f"__payee_{pname}__"
            if cat_id not in payee_by_cat:
                payee_by_cat[cat_id] = {}
            payee_by_cat[cat_id][pid] = payee_by_cat[cat_id].get(pid, 0) + abs(float(r.amount))

        for gid, total in sorted(group_totals.items(), key=lambda x: -x[1]):
            gname = next((v[1] for k, v in cat_to_group.items() if v[0] == gid), gid)
            get_node(f"g_{gid}", gname, "category_group")
            links.append(
                {
                    "source": "__budget__",
                    "target": f"g_{gid}",
                    "value": Decimal(str(round(total, 4))),
                }
            )

        payee_names: dict[str, str] = {}
        for r in expense_rows:
            pname = r.payee_name or "Unknown"
            pid = str(r.payee_id) if r.payee_id else f"__payee_{pname}__"
            payee_names[pid] = pname

        group_to_cats: dict[str, list[str]] = {}
        cat_names: dict[str, str] = {}

        category_payees: dict[str, list[dict]] = {}
        for cat_id, cat_payees in payee_by_cat.items():
            cat_info = cat_to_group.get(cat_id)
            if not cat_info:
                continue
            gid, _ = cat_info
            cat_rows = [r for r in expense_rows if r.category_id and str(r.category_id) == cat_id]
            cat_name = next((r.category_name for r in cat_rows if r.category_name), cat_id)
            cat_names[cat_id] = cat_name or cat_id
            group_to_cats.setdefault(gid, []).append(cat_id)
            get_node(f"c_{cat_id}", cat_name or cat_id, "category")
            links.append(
                {
                    "source": f"g_{gid}",
                    "target": f"c_{cat_id}",
                    "value": Decimal(str(round(cat_totals[cat_id], 4))),
                }
            )
            top10 = sorted(cat_payees.items(), key=lambda x: -x[1])[:10]
            category_payees[f"c_{cat_id}"] = [
                {"name": payee_names.get(pid, "Unknown"), "total": Decimal(str(round(ptotal, 4)))}
                for pid, ptotal in top10
            ]

        group_categories: dict[str, list[dict]] = {}
        for gid, cats in group_to_cats.items():
            top10 = sorted(cats, key=lambda c: -cat_totals.get(c, 0))[:10]
            group_categories[f"g_{gid}"] = [
                {"name": cat_names.get(c, c), "total": Decimal(str(round(cat_totals.get(c, 0), 4)))}
                for c in top10
            ]

        return {
            "nodes": [{"id": n["id"], "name": n["name"], "type": n["type"]} for n in nodes],
            "links": links,
            "total_income": total_income,
            "total_expense": total_expense,
            "category_payees": category_payees,
            "group_categories": group_categories,
        }

    # ─── Budget vs Actual ─────────────────────────────────────────────────────

    async def budget_vs_actual(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        category_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        months_in_range = _months_in_range(start_date, end_date)

        # Assignments for those months
        assign_q = (
            select(
                BudgetAssignment.category_id,
                BudgetAssignment.month,
                BudgetAssignment.assigned,
                Category.name.label("category_name"),
                CategoryGroup.name.label("group_name"),
            )
            .join(Category, BudgetAssignment.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                BudgetAssignment.budget_id == budget_id,
                BudgetAssignment.month.in_(months_in_range),
                Category.is_deleted == False,  # noqa: E712
                CategoryGroup.is_deleted == False,  # noqa: E712
                CategoryGroup.is_system == False,  # noqa: E712
            )
        )

        # Activity (expenses) in range — leaf rows so split children count
        spend_q = select(Transaction.category_id, Transaction.amount).where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            Transaction.amount < 0,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            LEAF,
            CASH_FLOW_ROW,
            Transaction.category_id.isnot(None),
        )
        if category_ids:
            assign_q = assign_q.where(BudgetAssignment.category_id.in_(category_ids))
            spend_q = spend_q.where(Transaction.category_id.in_(category_ids))

        assignments = (await self.session.execute(assign_q)).all()
        spending = (await self.session.execute(spend_q)).all()

        if not assignments and not spending:
            return {"categories": [], "total_assigned": Decimal("0"), "total_spent": Decimal("0")}

        # Aggregate assignments by category
        assign_by_cat: dict[str, dict] = {}
        for r in assignments:
            cid = str(r.category_id)
            if cid not in assign_by_cat:
                assign_by_cat[cid] = {
                    "category_id": cid,
                    "category_name": r.category_name,
                    "category_group_name": r.group_name,
                    "assigned": Decimal("0"),
                    "spent": Decimal("0"),
                }
            assign_by_cat[cid]["assigned"] += Decimal(str(r.assigned))

        # Aggregate spending by category
        for r in spending:
            cid = str(r.category_id)
            if cid not in assign_by_cat:
                assign_by_cat[cid] = {
                    "category_id": cid,
                    "category_name": "Unknown",
                    "category_group_name": "",
                    "assigned": Decimal("0"),
                    "spent": Decimal("0"),
                }
            assign_by_cat[cid]["spent"] += abs(Decimal(str(r.amount)))

        categories = []
        total_assigned = Decimal("0")
        total_spent = Decimal("0")

        for item in sorted(assign_by_cat.values(), key=lambda x: x["spent"], reverse=True):
            variance = item["assigned"] - item["spent"]
            variance_pct = float(variance / item["assigned"] * 100) if item["assigned"] > 0 else 0.0
            categories.append({**item, "variance": variance, "variance_pct": variance_pct})
            total_assigned += item["assigned"]
            total_spent += item["spent"]

        return {
            "categories": categories,
            "total_assigned": total_assigned,
            "total_spent": total_spent,
        }

    # ─── Cumulative Variance ──────────────────────────────────────────────────

    async def cumulative_variance(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
    ) -> list[dict]:
        today = date.today()
        first_of_month = today.replace(day=1)
        months_list = [_subtract_months(first_of_month, i) for i in range(months - 1, -1, -1)]

        assign_q = (
            select(BudgetAssignment.month, BudgetAssignment.assigned)
            .join(Category, BudgetAssignment.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                BudgetAssignment.budget_id == budget_id,
                BudgetAssignment.month.in_(months_list),
                CategoryGroup.is_system == False,  # noqa: E712
                Category.is_deleted == False,  # noqa: E712
            )
        )
        assignments = (await self.session.execute(assign_q)).all()

        start = months_list[0]
        end = _last_day(months_list[-1])
        spend_q = select(Transaction.date, Transaction.amount).where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            Transaction.amount < 0,
            Transaction.date >= start,
            Transaction.date <= end,
            LEAF,
            CASH_FLOW_ROW,
            Transaction.category_id.isnot(None),
        )
        spending = (await self.session.execute(spend_q)).all()

        assign_by_month: dict[date, Decimal] = {}
        for r in assignments:
            m = r.month if isinstance(r.month, date) else date.fromisoformat(str(r.month))
            assign_by_month[m] = assign_by_month.get(m, Decimal("0")) + Decimal(str(r.assigned))

        spend_by_month: dict[date, Decimal] = {}
        for r in spending:
            m = r.date.replace(day=1)
            spend_by_month[m] = spend_by_month.get(m, Decimal("0")) + abs(Decimal(str(r.amount)))

        results = []
        cumulative = Decimal("0")
        for month in months_list:
            assigned = assign_by_month.get(month, Decimal("0"))
            spent = spend_by_month.get(month, Decimal("0"))
            variance = assigned - spent
            cumulative += variance
            results.append(
                {
                    "month": month,
                    "budget_assigned": assigned,
                    "actual_spent": spent,
                    "monthly_variance": variance,
                    "cumulative_variance": cumulative,
                }
            )

        return results

    # ─── Category Volatility ─────────────────────────────────────────────────

    async def category_volatility(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
    ) -> list[dict]:
        today = date.today()
        first_of_month = today.replace(day=1)
        start = _subtract_months(first_of_month, months - 1)

        q = (
            select(
                Transaction.date,
                Transaction.amount,
                Transaction.category_id,
                Category.name.label("category_name"),
                CategoryGroup.name.label("group_name"),
            )
            .join(Category, Transaction.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                Transaction.amount < 0,
                Transaction.date >= start,
                LEAF,
                CASH_FLOW_ROW,
                CategoryGroup.is_system == False,  # noqa: E712
            )
        )
        rows = (await self.session.execute(q)).all()

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

        stats = (
            monthly.group_by(["category_id", "category_name", "group_name"])
            .agg(
                pl.col("monthly_total").mean().alias("mean"),
                pl.col("monthly_total").std().alias("std_dev"),
                pl.col("monthly_total").min().alias("min_val"),
                pl.col("monthly_total").max().alias("max_val"),
                pl.col("monthly_total").quantile(0.25).alias("p25"),
                pl.col("monthly_total").quantile(0.75).alias("p75"),
                pl.col("monthly_total").count().alias("months_included"),
            )
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

    # ─── Spending Grouped (Pareto + Treemap) ──────────────────────────────────

    async def spending_grouped(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        category_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
        exclude_savings: bool = False,
    ) -> tuple[list[dict], Decimal]:
        # Get categories to exclude if exclude_savings is True
        exclude_cat_ids: set[uuid.UUID] = set()
        if exclude_savings:
            from igab.repositories.tag_repo import TagRepository

            tag_repo = TagRepository(self.session)
            exclude_cat_ids = await tag_repo.get_category_ids_by_system_keys(
                budget_id, ["savings", "long_term_expense"]
            )

        q = (
            select(
                Category.id,
                Category.name,
                CategoryGroup.id.label("group_id"),
                CategoryGroup.name.label("group_name"),
                Transaction.amount,
            )
            .join(Transaction, Transaction.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                Transaction.amount < 0,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                LEAF,
                CASH_FLOW_ROW,
                CategoryGroup.is_system == False,  # noqa: E712
            )
        )
        if category_ids:
            q = q.where(Transaction.category_id.in_(category_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        if exclude_cat_ids:
            q = q.where(Transaction.category_id.notin_(exclude_cat_ids))
        rows = (await self.session.execute(q)).all()

        if not rows:
            return [], Decimal("0")

        df = pl.DataFrame(
            {
                "cat_id": [str(r.id) for r in rows],
                "cat_name": [r.name for r in rows],
                "group_id": [str(r.group_id) for r in rows],
                "group_name": [r.group_name for r in rows],
                "amount": [abs(float(r.amount)) for r in rows],
            }
        )

        cat_agg = (
            df.group_by(["cat_id", "cat_name", "group_id", "group_name"])
            .agg(
                pl.col("amount").sum().alias("total"),
                pl.col("amount").count().alias("count"),
            )
            .sort("total", descending=True)
        )

        grand_total = float(cat_agg["total"].sum())

        items = [
            {
                "id": row["cat_id"],
                "name": row["cat_name"],
                "parent_id": row["group_id"],
                "parent_name": row["group_name"],
                "total": Decimal(str(row["total"])),
                "count": int(row["count"]),
                "pct": float(row["total"] / grand_total * 100) if grand_total else 0.0,
            }
            for row in cat_agg.iter_rows(named=True)
        ]

        return items, Decimal(str(grand_total))

    # ─── Seasonality ─────────────────────────────────────────────────────────

    async def seasonality(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
    ) -> dict:
        today = date.today()
        first_of_month = today.replace(day=1)
        start = _subtract_months(first_of_month, months - 1)

        q = (
            select(
                Transaction.date,
                Transaction.amount,
                Transaction.category_id,
                Category.name.label("category_name"),
            )
            .join(Category, Transaction.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                Transaction.amount < 0,
                Transaction.date >= start,
                LEAF,
                CASH_FLOW_ROW,
                CategoryGroup.is_system == False,  # noqa: E712
            )
        )
        rows = (await self.session.execute(q)).all()

        months_list = [_subtract_months(first_of_month, i) for i in range(months - 1, -1, -1)]

        if not rows:
            return {"cells": [], "months": months_list, "categories": []}

        df = pl.DataFrame(
            {
                "date": [r.date for r in rows],
                "amount": [abs(float(r.amount)) for r in rows],
                "category_id": [str(r.category_id) for r in rows],
                "category_name": [r.category_name for r in rows],
            },
            schema_overrides={"date": pl.Date, "amount": pl.Float64},
        )

        agg = (
            df.with_columns(pl.col("date").dt.truncate("1mo").alias("month"))
            .group_by(["category_id", "category_name", "month"])
            .agg(pl.col("amount").sum().alias("total"))
            .sort(["month", "total"], descending=[False, True])
        )

        cells = [
            {
                "category_id": row["category_id"],
                "category_name": row["category_name"],
                "month": row["month"],
                "total": Decimal(str(row["total"])),
            }
            for row in agg.iter_rows(named=True)
        ]

        # Top categories by total spend across period
        cat_totals = (
            agg.group_by(["category_id", "category_name"])
            .agg(pl.col("total").sum().alias("grand_total"))
            .sort("grand_total", descending=True)
            .head(20)
        )
        categories = [
            {"id": row["category_id"], "name": row["category_name"]}
            for row in cat_totals.iter_rows(named=True)
        ]

        return {"cells": cells, "months": months_list, "categories": categories}

    # ─── Payee Analysis ───────────────────────────────────────────────────────

    async def payee_analysis(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int = 25,
        payee_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
    ) -> tuple[list[dict], Decimal]:
        q = (
            select(
                Transaction.date,
                Transaction.amount,
                Transaction.payee_id,
                Transaction.category_id,
                Payee.name.label("payee_name"),
                Category.name.label("category_name"),
            )
            .outerjoin(Payee, Transaction.payee_id == Payee.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                Transaction.amount < 0,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                # Payee-of-record lives on the parent row; per-child payees on
                # splits are intentionally not surfaced here.
                PARENT_ROW,
                CASH_FLOW_ROW,
                Transaction.payee_id.isnot(None),
            )
        )
        if payee_ids:
            q = q.where(Transaction.payee_id.in_(payee_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        rows = (await self.session.execute(q)).all()

        if not rows:
            return [], Decimal("0")

        df = pl.DataFrame(
            {
                "date": [r.date for r in rows],
                "amount": [abs(float(r.amount)) for r in rows],
                "payee_id": [str(r.payee_id) for r in rows],
                "payee_name": [r.payee_name or "Unknown" for r in rows],
                "category_id": [str(r.category_id) if r.category_id else "" for r in rows],
                "category_name": [r.category_name or "Uncategorized" for r in rows],
            },
            schema_overrides={"date": pl.Date, "amount": pl.Float64},
        )

        payee_agg = (
            df.group_by(["payee_id", "payee_name"])
            .agg(
                pl.col("amount").sum().alias("total"),
                pl.col("amount").count().alias("count"),
            )
            .sort("total", descending=True)
            .head(limit)
        )

        grand_total = Decimal(str(payee_agg["total"].sum()))

        payees = []
        for row in payee_agg.iter_rows(named=True):
            pid = row["payee_id"]
            payee_df = df.filter(pl.col("payee_id") == pid)

            # Monthly trend
            trend = (
                payee_df.with_columns(pl.col("date").dt.truncate("1mo").alias("month"))
                .group_by("month")
                .agg(pl.col("amount").sum().alias("total"))
                .sort("month")
            )
            monthly_trend = [
                {"month": r["month"], "total": Decimal(str(r["total"]))}
                for r in trend.iter_rows(named=True)
            ]

            # Top categories
            top_cats = (
                payee_df.filter(pl.col("category_name") != "Uncategorized")
                .group_by("category_name")
                .agg(pl.col("amount").sum().alias("total"))
                .sort("total", descending=True)
                .head(3)
            )
            top_categories = [
                {"category_name": r["category_name"], "total": Decimal(str(r["total"]))}
                for r in top_cats.iter_rows(named=True)
            ]

            # Recurring: appears in >= 3 different months
            months_active = payee_df.with_columns(pl.col("date").dt.truncate("1mo").alias("month"))[
                "month"
            ].n_unique()
            is_recurring = months_active >= 3

            payees.append(
                {
                    "payee_id": pid,
                    "payee_name": row["payee_name"],
                    "total": Decimal(str(row["total"])),
                    "count": int(row["count"]),
                    "pct": (
                        float(Decimal(str(row["total"])) / grand_total * 100)
                        if grand_total
                        else 0.0
                    ),
                    "monthly_trend": monthly_trend,
                    "top_categories": top_categories,
                    "is_recurring": is_recurring,
                }
            )

        return payees, grand_total

    # ─── Day Patterns ─────────────────────────────────────────────────────────

    async def day_patterns(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        category_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
    ) -> list[dict]:
        # Leaf rows: with a category filter, split spending must be reachable
        q = select(Transaction.date, Transaction.amount).where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            Transaction.amount < 0,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            LEAF,
            CASH_FLOW_ROW,
        )
        if category_ids:
            q = q.where(Transaction.category_id.in_(category_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        rows = (await self.session.execute(q)).all()

        if not rows:
            return [
                {
                    "day_of_week": i,
                    "day_name": _DAY_NAMES[i],
                    "total": Decimal("0"),
                    "count": 0,
                    "avg_transaction": Decimal("0"),
                }
                for i in range(7)
            ]

        df = pl.DataFrame(
            {
                "date": [r.date for r in rows],
                "amount": [abs(float(r.amount)) for r in rows],
            },
            schema_overrides={"date": pl.Date, "amount": pl.Float64},
        )

        agg = (
            df.with_columns(((pl.col("date").dt.weekday() - 1) % 7).alias("dow"))
            .group_by("dow")
            .agg(
                pl.col("amount").sum().alias("total"),
                pl.col("amount").count().alias("count"),
                pl.col("amount").mean().alias("avg"),
            )
            .sort("dow")
        )

        dow_map = {row["dow"]: row for row in agg.iter_rows(named=True)}

        return [
            {
                "day_of_week": i,
                "day_name": _DAY_NAMES[i],
                "total": (
                    Decimal(str(round(dow_map[i]["total"], 4))) if i in dow_map else Decimal("0")
                ),
                "count": int(dow_map[i]["count"]) if i in dow_map else 0,
                "avg_transaction": (
                    Decimal(str(round(dow_map[i]["avg"], 4))) if i in dow_map else Decimal("0")
                ),
            }
            for i in range(7)
        ]

    # ─── Large Transactions (Timeline) ────────────────────────────────────────

    async def large_transactions(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int = 50,
        category_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
    ) -> list[dict]:
        q = (
            select(
                Transaction.id,
                Transaction.date,
                Transaction.amount,
                Transaction.memo,
                Payee.name.label("payee_name"),
                Category.name.label("category_name"),
            )
            .outerjoin(Payee, Transaction.payee_id == Payee.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                # Timeline is parent-centric: one entry per real purchase.
                PARENT_ROW,
                CASH_FLOW_ROW,
            )
        )
        if category_ids:
            q = q.where(Transaction.category_id.in_(category_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        q = q.order_by(Transaction.amount).limit(limit)  # most negative first
        rows = (await self.session.execute(q)).all()

        return [
            {
                "id": str(r.id),
                "date": r.date,
                "amount": Decimal(str(r.amount)),
                "payee_name": r.payee_name,
                "category_name": r.category_name,
                "memo": r.memo,
            }
            for r in rows
        ]

    # ─── Subscriptions Report ─────────────────────────────────────────────────

    async def subscriptions_report(self, budget_id: uuid.UUID, months: int = 12) -> dict:
        """Aggregate transactions from payees tagged with 'subscription' system tag."""
        from igab.repositories.tag_repo import TagRepository

        tag_repo = TagRepository(self.session)

        # Get the subscription system tag
        subscription_tag = await tag_repo.get_system_tag(budget_id, "subscription")
        if subscription_tag is None:
            return {
                "subscriptions": [],
                "summary": {
                    "total_monthly": Decimal("0"),
                    "total_annual": Decimal("0"),
                    "active_count": 0,
                },
                "months": [],
            }

        # Get payee IDs tagged with subscription
        subscription_payee_ids = await tag_repo.get_payee_ids_by_tags(
            budget_id, [subscription_tag.id]
        )
        if not subscription_payee_ids:
            return {
                "subscriptions": [],
                "summary": {
                    "total_monthly": Decimal("0"),
                    "total_annual": Decimal("0"),
                    "active_count": 0,
                },
                "months": [],
            }

        # Date range
        today = date.today()
        end_date = today
        start_date = _subtract_months(today, months).replace(day=1)
        month_list = _months_in_range(start_date, end_date)

        # Query transactions for subscription-tagged payees
        q = (
            select(
                Transaction.payee_id,
                Payee.name.label("payee_name"),
                Transaction.date,
                Transaction.amount,
            )
            .join(Payee, Payee.id == Transaction.payee_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.payee_id.in_(subscription_payee_ids),
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.cleared != "pending",
                Transaction.amount < 0,  # outflows only
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.is_split == False,  # noqa: E712 - leaf rows
            )
        )
        rows = (await self.session.execute(q)).all()

        if not rows:
            return {
                "subscriptions": [],
                "summary": {
                    "total_monthly": Decimal("0"),
                    "total_annual": Decimal("0"),
                    "active_count": 0,
                },
                "months": [m for m in month_list],
            }

        # Build DataFrame for aggregation
        df = pl.DataFrame(
            {
                "payee_id": [str(r.payee_id) for r in rows],
                "payee_name": [r.payee_name for r in rows],
                "month": [r.date.replace(day=1) for r in rows],
                "date": [r.date for r in rows],
                "amount": [abs(float(r.amount)) for r in rows],
            }
        )

        # Per-payee monthly aggregation
        payee_monthly = df.group_by(["payee_id", "payee_name", "month"]).agg(
            pl.col("amount").sum().alias("monthly_total")
        )

        # Build subscription items
        subscriptions = []
        for payee_id in df["payee_id"].unique().to_list():
            payee_rows = payee_monthly.filter(pl.col("payee_id") == payee_id)
            payee_name = payee_rows["payee_name"][0]

            # Monthly amounts for each month in the range
            monthly_amounts = []
            for m in month_list:
                row = payee_rows.filter(pl.col("month") == m)
                if len(row) > 0:
                    monthly_amounts.append(Decimal(str(row["monthly_total"][0])))
                else:
                    monthly_amounts.append(Decimal("0"))

            total = sum(monthly_amounts)
            months_with_charges = sum(1 for a in monthly_amounts if a > 0)
            avg_monthly = total / months_with_charges if months_with_charges > 0 else Decimal("0")

            # Last charge date and count
            payee_txns = df.filter(pl.col("payee_id") == payee_id)
            last_charge = max(payee_txns["date"].to_list()) if len(payee_txns) > 0 else None
            txn_count = len(payee_txns)

            subscriptions.append(
                {
                    "payee_id": payee_id,
                    "payee_name": payee_name,
                    "monthly_amounts": monthly_amounts,
                    "total": total,
                    "avg_monthly": avg_monthly.quantize(Decimal("0.01")),
                    "last_charge_date": last_charge,
                    "transaction_count": txn_count,
                }
            )

        # Sort by total descending
        subscriptions.sort(key=lambda x: x["total"], reverse=True)

        # Summary
        total_monthly = sum(s["avg_monthly"] for s in subscriptions)
        total_annual = total_monthly * 12

        return {
            "subscriptions": subscriptions,
            "summary": {
                "total_monthly": total_monthly.quantize(Decimal("0.01")),
                "total_annual": total_annual.quantize(Decimal("0.01")),
                "active_count": len(subscriptions),
            },
            "months": month_list,
        }

    # ─── Savings Report ───────────────────────────────────────────────────────

    async def savings_report(self, budget_id: uuid.UUID, months: int = 12) -> dict:
        """Aggregate categories tagged with 'savings' or 'long_term_expense'."""
        from igab.repositories.tag_repo import TagRepository

        tag_repo = TagRepository(self.session)

        # Get category IDs tagged with savings or long_term_expense
        savings_cat_ids = await tag_repo.get_category_ids_by_system_keys(
            budget_id, ["savings", "long_term_expense"]
        )

        if not savings_cat_ids:
            return {
                "categories": [],
                "summary": {
                    "total_balance": Decimal("0"),
                    "total_inflow": Decimal("0"),
                    "avg_monthly_inflow": Decimal("0"),
                    "category_count": 0,
                },
                "months": [],
            }

        # Date range
        today = date.today()
        end_date = today
        start_date = _subtract_months(today, months).replace(day=1)
        month_list = _months_in_range(start_date, end_date)

        # Get category info and current balances
        cat_info_q = (
            select(
                Category.id,
                Category.name,
                CategoryGroup.name.label("group_name"),
            )
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(Category.id.in_(savings_cat_ids))
        )
        cat_info_rows = (await self.session.execute(cat_info_q)).all()
        cat_info = {str(r.id): {"name": r.name, "group_name": r.group_name} for r in cat_info_rows}

        # Get assignments (inflows) per category per month
        assign_q = select(
            BudgetAssignment.category_id,
            BudgetAssignment.month,
            BudgetAssignment.assigned,
        ).where(
            BudgetAssignment.category_id.in_(savings_cat_ids),
            BudgetAssignment.month >= start_date,
            BudgetAssignment.month <= end_date,
        )
        assign_rows = (await self.session.execute(assign_q)).all()

        # Build assignment map: category_id -> month -> assigned
        assign_map: dict[str, dict[date, Decimal]] = {}
        for r in assign_rows:
            cid = str(r.category_id)
            if cid not in assign_map:
                assign_map[cid] = {}
            assign_map[cid][r.month] = r.assigned

        # Get category activity (transactions) per month for running balance
        txn_q = (
            select(
                Transaction.category_id,
                func.date_trunc("month", Transaction.date).label("month"),
                func.sum(Transaction.amount).label("activity"),
            )
            .where(
                Transaction.budget_id == budget_id,
                Transaction.category_id.in_(savings_cat_ids),
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.cleared != "pending",
                Transaction.is_split == False,  # noqa: E712
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
            .group_by(Transaction.category_id, func.date_trunc("month", Transaction.date))
        )
        txn_rows = (await self.session.execute(txn_q)).all()

        # Build activity map: category_id -> month -> activity
        activity_map: dict[str, dict[date, Decimal]] = {}
        for r in txn_rows:
            cid = str(r.category_id)
            if cid not in activity_map:
                activity_map[cid] = {}
            # date_trunc returns timestamp, convert to date
            month_date = r.month.date() if hasattr(r.month, "date") else r.month
            activity_map[cid][month_date.replace(day=1)] = r.activity

        # Get current balances for each category (use the budget months endpoint logic)
        # For simplicity, compute cumulative: prior + assigned + activity
        # We need prior balance before start_date
        prior_assign_q = (
            select(
                BudgetAssignment.category_id,
                func.sum(BudgetAssignment.assigned).label("total"),
            )
            .where(
                BudgetAssignment.category_id.in_(savings_cat_ids),
                BudgetAssignment.month < start_date,
            )
            .group_by(BudgetAssignment.category_id)
        )
        prior_assign_rows = (await self.session.execute(prior_assign_q)).all()
        prior_assigned = {str(r.category_id): r.total or Decimal("0") for r in prior_assign_rows}

        prior_activity_q = (
            select(
                Transaction.category_id,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.budget_id == budget_id,
                Transaction.category_id.in_(savings_cat_ids),
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.cleared != "pending",
                Transaction.is_split == False,  # noqa: E712
                Transaction.date < start_date,
            )
            .group_by(Transaction.category_id)
        )
        prior_activity_rows = (await self.session.execute(prior_activity_q)).all()
        prior_activity = {str(r.category_id): r.total or Decimal("0") for r in prior_activity_rows}

        # Build category results
        categories = []
        for cid in savings_cat_ids:
            cid_str = str(cid)
            if cid_str not in cat_info:
                continue

            info = cat_info[cid_str]
            prior_bal = prior_assigned.get(cid_str, Decimal("0")) + prior_activity.get(
                cid_str, Decimal("0")
            )

            # Compute monthly balances
            monthly_balances = []
            running_bal = prior_bal
            total_inflow = Decimal("0")

            for m in month_list:
                assigned = assign_map.get(cid_str, {}).get(m, Decimal("0"))
                activity = activity_map.get(cid_str, {}).get(m, Decimal("0"))
                running_bal = running_bal + assigned + activity
                monthly_balances.append(running_bal)
                if assigned > 0:
                    total_inflow += assigned

            current_balance = monthly_balances[-1] if monthly_balances else Decimal("0")

            categories.append(
                {
                    "category_id": cid_str,
                    "category_name": info["name"],
                    "group_name": info["group_name"],
                    "monthly_balances": monthly_balances,
                    "current_balance": current_balance,
                    "target_balance": None,  # Could fetch from category targets
                    "total_inflow": total_inflow,
                }
            )

        # Sort by current balance descending
        categories.sort(key=lambda x: x["current_balance"], reverse=True)

        # Summary
        total_balance = sum(c["current_balance"] for c in categories)
        total_inflow = sum(c["total_inflow"] for c in categories)
        avg_monthly = total_inflow / len(month_list) if month_list else Decimal("0")

        return {
            "categories": categories,
            "summary": {
                "total_balance": total_balance,
                "total_inflow": total_inflow,
                "avg_monthly_inflow": avg_monthly.quantize(Decimal("0.01")),
                "category_count": len(categories),
            },
            "months": month_list,
        }

    # ─── Anomaly Detection ────────────────────────────────────────────────────

    async def anomalies_report(
        self, budget_id: uuid.UUID, months: int = 12, threshold: float = 2.0
    ) -> dict:
        """Detect category-months with spending outside baseline z-score."""
        today = date.today()
        end_date = today
        start_date = _subtract_months(today, months).replace(day=1)

        # Get spending per category per month
        month_col = func.date_trunc(literal_column("'month'"), Transaction.date).label("month")
        q = (
            select(
                Category.id.label("category_id"),
                Category.name.label("category_name"),
                CategoryGroup.name.label("group_name"),
                month_col,
                func.sum(Transaction.amount).label("total"),
            )
            .join(Transaction, Transaction.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.cleared != "pending",
                Transaction.amount < 0,  # outflows only
                Transaction.is_split == False,  # noqa: E712
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                CategoryGroup.is_system == False,  # noqa: E712
            )
            .group_by(
                Category.id,
                Category.name,
                CategoryGroup.name,
                month_col,
            )
        )
        rows = (await self.session.execute(q)).all()

        if not rows:
            return {"anomalies": []}

        # Build DataFrame
        df = pl.DataFrame(
            {
                "category_id": [str(r.category_id) for r in rows],
                "category_name": [r.category_name for r in rows],
                "group_name": [r.group_name for r in rows],
                "month": [r.month.date() if hasattr(r.month, "date") else r.month for r in rows],
                "total": [abs(float(r.total)) for r in rows],
            }
        )

        anomalies = []

        # Group by category and compute z-scores
        for cat_id in df["category_id"].unique().to_list():
            cat_df = df.filter(pl.col("category_id") == cat_id).sort("month")

            if len(cat_df) < 6:
                continue

            cat_name = cat_df["category_name"][0]
            group_name = cat_df["group_name"][0]
            months_data = cat_df["month"].to_list()
            totals = cat_df["total"].to_list()

            # For each month, compute leave-one-out z-score
            for i, (month, actual) in enumerate(zip(months_data, totals)):
                # Leave-one-out: exclude current month
                others = [t for j, t in enumerate(totals) if j != i]
                if len(others) < 5:
                    continue

                mean = sum(others) / len(others)
                variance = sum((x - mean) ** 2 for x in others) / len(others)
                std = variance**0.5

                # Guard rails
                if std < 5.0:
                    continue
                if abs(actual - mean) < 25.0:
                    continue

                z_score = (actual - mean) / std if std > 0 else 0

                if abs(z_score) >= threshold:
                    # Get trailing 12 months for sparkline
                    history = totals[max(0, i - 11) : i + 1]
                    # Pad to 12 if needed
                    while len(history) < 12:
                        history.insert(0, 0)

                    anomalies.append(
                        {
                            "category_id": cat_id,
                            "category_name": cat_name,
                            "group_name": group_name,
                            "month": month,
                            "actual": Decimal(str(actual)).quantize(Decimal("0.01")),
                            "baseline_mean": Decimal(str(mean)).quantize(Decimal("0.01")),
                            "z_score": round(z_score, 2),
                            "direction": "high" if z_score > 0 else "low",
                            "history": [Decimal(str(h)).quantize(Decimal("0.01")) for h in history],
                        }
                    )

        # Sort by z-score magnitude descending
        anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)

        return {"anomalies": anomalies}

    # ─── Payday Effect ─────────────────────────────────────────────────────────

    async def payday_effect(
        self,
        budget_id: uuid.UUID,
        window: int = 14,
        months: int = 12,
    ) -> dict:
        """Compute average daily spending for N days after income events."""
        end_date = date.today()
        start_date = _subtract_months(end_date, months)

        # Get subscription-tagged payee ids to exclude
        from igab.repositories.tag_repo import TagRepository

        tag_repo = TagRepository(self.session)
        subscription_payee_ids = await tag_repo.get_payee_ids_by_system_keys(
            budget_id, system_keys=["subscription"]
        )

        # Get all transactions in the period
        q = (
            select(
                Transaction.date,
                Transaction.amount,
                Transaction.payee_id,
            )
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.cleared != "pending",
                Transaction.is_split == False,  # noqa: E712
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
            .order_by(Transaction.date)
        )
        rows = (await self.session.execute(q)).all()

        if not rows:
            return {
                "days": [{"offset": i, "avg_spend": Decimal("0")} for i in range(window)],
                "baseline_daily": Decimal("0"),
                "event_count": 0,
            }

        # Build DataFrame
        df = pl.DataFrame(
            {
                "date": [r.date for r in rows],
                "amount": [float(r.amount) for r in rows],
                "payee_id": [str(r.payee_id) if r.payee_id else None for r in rows],
            }
        )

        # Identify income events: inflows >= P75 of all inflows (floor $200)
        inflows = df.filter(pl.col("amount") > 0)
        if inflows.is_empty():
            return {
                "days": [{"offset": i, "avg_spend": Decimal("0")} for i in range(window)],
                "baseline_daily": Decimal("0"),
                "event_count": 0,
            }

        p75 = inflows["amount"].quantile(0.75)
        threshold = max(float(p75) if p75 is not None else 0.0, 200.0)
        income_events = inflows.filter(pl.col("amount") >= threshold)["date"].unique().to_list()
        income_dates = set(income_events)

        if not income_dates:
            return {
                "days": [{"offset": i, "avg_spend": Decimal("0")} for i in range(window)],
                "baseline_daily": Decimal("0"),
                "event_count": 0,
            }

        # Exclude subscription-tagged payees from spending
        sub_ids = {str(pid) for pid in subscription_payee_ids}
        outflows = df.filter(
            (pl.col("amount") < 0)
            & (~pl.col("payee_id").is_in(sub_ids) | pl.col("payee_id").is_null())
        )

        # Group by date
        daily_spend = (
            outflows.group_by("date")
            .agg(pl.col("amount").sum().alias("total"))
            .with_columns(pl.col("total").abs())
        )
        daily_map = {r["date"]: r["total"] for r in daily_spend.to_dicts()}

        # Compute spending for each offset day after income events
        offset_totals: dict[int, list[float]] = {i: [] for i in range(window)}
        baseline_days: list[float] = []

        all_dates = sorted(daily_map.keys())
        income_windows: set[date] = set()

        for inc_date in income_dates:
            for offset in range(window):
                target_date = inc_date + timedelta(days=offset)
                income_windows.add(target_date)
                if target_date in daily_map:
                    offset_totals[offset].append(daily_map[target_date])

        # Baseline: days NOT in any income window
        for d in all_dates:
            if d not in income_windows and d in daily_map:
                baseline_days.append(daily_map[d])

        # Compute averages
        days_result = []
        for offset in range(window):
            vals = offset_totals[offset]
            avg_spend = sum(vals) / len(vals) if vals else 0
            days_result.append(
                {"offset": offset, "avg_spend": Decimal(str(avg_spend)).quantize(Decimal("0.01"))}
            )

        baseline_daily = (
            Decimal(str(sum(baseline_days) / len(baseline_days))).quantize(Decimal("0.01"))
            if baseline_days
            else Decimal("0")
        )

        return {
            "days": days_result,
            "baseline_daily": baseline_daily,
            "event_count": len(income_dates),
        }

    # ─── Cash Projection ─────────────────────────────────────────────────────────

    async def cash_projection(
        self,
        budget_id: uuid.UUID,
        horizon_days: int = 90,
    ) -> dict:
        """Project future cash balances with uncertainty bands."""
        import random

        from igab.db.models import ScheduledTransaction
        from igab.repositories.tag_repo import TagRepository

        today = date.today()
        end_date = today + timedelta(days=horizon_days)

        # 1. Get current on-budget account balances (sum of cleared transactions)
        q = (
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared != "pending",
                Account.is_closed == False,  # noqa: E712
                Account.on_budget == True,  # noqa: E712
            )
        )
        result = await self.session.execute(q)
        start_balance = Decimal(str(result.scalar() or 0))

        # 2. Get scheduled transactions in the projection window
        sched_q = (
            select(
                ScheduledTransaction.id,
                ScheduledTransaction.amount,
                ScheduledTransaction.next_occurrence_date,
                ScheduledTransaction.frequency,
                ScheduledTransaction.end_date,
                Payee.name.label("payee_name"),
            )
            .outerjoin(Payee, Payee.id == ScheduledTransaction.payee_id)
            .where(
                ScheduledTransaction.budget_id == budget_id,
                ScheduledTransaction.is_deleted == False,  # noqa: E712
                ScheduledTransaction.next_occurrence_date <= end_date,
            )
        )
        sched_rows = (await self.session.execute(sched_q)).all()

        # Expand scheduled transactions into individual events
        scheduled_events: list[tuple[date, str, Decimal]] = []
        for row in sched_rows:
            occ_date = row.next_occurrence_date
            amount = Decimal(str(row.amount))
            payee_name = row.payee_name or "Scheduled"
            freq = row.frequency
            row_end_date = row.end_date

            while occ_date <= end_date:
                if row_end_date and occ_date > row_end_date:
                    break
                scheduled_events.append((occ_date, payee_name, amount))
                occ_date = _next_occurrence(occ_date, freq)
                if occ_date is None:
                    break

        # 3. Get subscription-tagged payees for expected subscription charges
        tag_repo = TagRepository(self.session)
        subscription_payee_ids = await tag_repo.get_payee_ids_by_system_keys(
            budget_id, system_keys=["subscription"]
        )

        subscription_events: list[tuple[date, str, Decimal]] = []
        if subscription_payee_ids:
            # Get last charge date and typical amount for each subscription payee
            sub_q = (
                select(
                    Transaction.payee_id,
                    Payee.name.label("payee_name"),
                    func.max(Transaction.date).label("last_date"),
                    func.avg(Transaction.amount).label("avg_amount"),
                )
                .join(Payee, Payee.id == Transaction.payee_id)
                .where(
                    Transaction.budget_id == budget_id,
                    Transaction.is_deleted == False,  # noqa: E712
                    Transaction.payee_id.in_(subscription_payee_ids),
                    Transaction.amount < 0,
                )
                .group_by(Transaction.payee_id, Payee.name)
            )
            sub_rows = (await self.session.execute(sub_q)).all()

            for row in sub_rows:
                last_date = row.last_date
                avg_amount = Decimal(str(row.avg_amount))
                payee_name = row.payee_name or "Subscription"

                # Assume monthly cadence, project forward
                next_date = last_date + timedelta(days=30)
                while next_date <= end_date:
                    if next_date >= today:
                        subscription_events.append((next_date, payee_name, avg_amount))
                    next_date = next_date + timedelta(days=30)

        # 4. Get historical daily net flows for stochastic layer
        hist_start = today - timedelta(days=180)
        hist_q = select(Transaction.date, Transaction.amount).where(
            Transaction.budget_id == budget_id,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.cleared != "pending",
            Transaction.is_split == False,  # noqa: E712
            Transaction.date >= hist_start,
            Transaction.date < today,
        )
        hist_rows = (await self.session.execute(hist_q)).all()

        # Group by date and weekday
        daily_flows: dict[int, list[float]] = {i: [] for i in range(7)}  # weekday buckets
        if hist_rows:
            df = pl.DataFrame(
                {
                    "date": [r.date for r in hist_rows],
                    "amount": [float(r.amount) for r in hist_rows],
                }
            )
            daily = df.group_by("date").agg(pl.col("amount").sum().alias("net"))
            for row in daily.iter_rows(named=True):
                d = row["date"]
                weekday = d.weekday()
                daily_flows[weekday].append(row["net"])

        # Ensure at least some history for each weekday
        all_flows = [f for flows in daily_flows.values() for f in flows]
        for wd in range(7):
            if not daily_flows[wd]:
                daily_flows[wd] = all_flows if all_flows else [0.0]

        # 5. Bootstrap simulation
        n_simulations = 500
        seed = int(today.toordinal())
        rng = random.Random(seed)

        # Pre-compute deterministic events by date
        det_by_date: dict[date, Decimal] = {}
        for d, _, amt in scheduled_events + subscription_events:
            det_by_date[d] = det_by_date.get(d, Decimal("0")) + amt

        # Run simulations
        sim_paths: list[list[float]] = []
        for _ in range(n_simulations):
            balance = float(start_balance)
            path = []
            for offset in range(horizon_days + 1):
                d = today + timedelta(days=offset)
                # Add deterministic events
                det = float(det_by_date.get(d, Decimal("0")))
                # Sample random daily flow from same weekday
                weekday = d.weekday()
                rand_flow = rng.choice(daily_flows[weekday])
                balance += det + rand_flow
                path.append(balance)
            sim_paths.append(path)

        # 6. Compute deterministic-only path
        det_path: list[Decimal] = []
        balance = start_balance
        for offset in range(horizon_days + 1):
            d = today + timedelta(days=offset)
            balance += det_by_date.get(d, Decimal("0"))
            det_path.append(balance)

        # 7. Compute percentiles
        points = []
        goes_negative_date: date | None = None
        for offset in range(horizon_days + 1):
            d = today + timedelta(days=offset)
            values = sorted([path[offset] for path in sim_paths])
            p10 = values[int(n_simulations * 0.10)]
            p25 = values[int(n_simulations * 0.25)]
            p50 = values[int(n_simulations * 0.50)]
            p75 = values[int(n_simulations * 0.75)]
            p90 = values[int(n_simulations * 0.90)]

            points.append(
                {
                    "date": d,
                    "p10": Decimal(str(p10)).quantize(Decimal("0.01")),
                    "p25": Decimal(str(p25)).quantize(Decimal("0.01")),
                    "p50": Decimal(str(p50)).quantize(Decimal("0.01")),
                    "p75": Decimal(str(p75)).quantize(Decimal("0.01")),
                    "p90": Decimal(str(p90)).quantize(Decimal("0.01")),
                    "deterministic": det_path[offset].quantize(Decimal("0.01")),
                }
            )

            if goes_negative_date is None and p50 < 0:
                goes_negative_date = d

        # 8. Build events list (first 30 days only, for display)
        events = []
        cutoff = today + timedelta(days=30)
        for d, payee, amt in sorted(scheduled_events):
            if d > cutoff:
                break
            events.append(
                {
                    "date": d,
                    "payee": payee,
                    "amount": amt,
                    "source": "scheduled",
                }
            )
        for d, payee, amt in sorted(subscription_events):
            if d > cutoff:
                break
            events.append(
                {
                    "date": d,
                    "payee": payee,
                    "amount": amt,
                    "source": "subscription",
                }
            )
        events.sort(key=lambda e: e["date"])

        return {
            "start_balance": start_balance,
            "points": points,
            "events": events[:20],  # Limit to first 20 events
            "goes_negative_date": goes_negative_date,
        }


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _next_occurrence(d: date, frequency: str) -> date | None:
    """Calculate next occurrence date based on frequency."""
    if frequency == "daily":
        return d + timedelta(days=1)
    elif frequency == "weekly":
        return d + timedelta(weeks=1)
    elif frequency == "biweekly":
        return d + timedelta(weeks=2)
    elif frequency == "monthly":
        month = d.month + 1
        year = d.year
        if month > 12:
            month = 1
            year += 1
        day = min(d.day, _last_day(date(year, month, 1)).day)
        return date(year, month, day)
    elif frequency == "yearly":
        return date(d.year + 1, d.month, d.day)
    return None


_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _empty_dashboard() -> dict:
    return {
        "net_worth": Decimal("0"),
        "net_worth_prev": Decimal("0"),
        "burn_rate_30": Decimal("0"),
        "burn_rate_90": Decimal("0"),
        "savings_rate": 0.0,
        "days_until_zero": None,
        "income_this_month": Decimal("0"),
        "expenses_this_month": Decimal("0"),
        "expenses_prev_month": Decimal("0"),
        "top_categories": [],
    }


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
