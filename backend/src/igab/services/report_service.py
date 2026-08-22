import io
import json
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict

import polars as pl
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from igab.db.models import (
    Account,
    BudgetAssignment,
    BudgetView,
    BudgetViewGroup,
    BudgetViewPlacement,
    Category,
    CategoryGroup,
    Liability,
    LiabilityBalanceSnapshot,
    Payee,
    Transaction,
)
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    CLASS_LABEL,
    SPENDING_CLASSES,
    ActivityClass,
)
from igab.repositories.txn_filters import (
    CASH_FLOW_ROW,
    LEAF,
    NOT_DELETED,
    ON_BUDGET_ACCOUNT,
    PARENT_ROW,
    POSTED,
)

# CASH_FLOW_ROW: plain rows plus categorized transfer legs (spending
# transfers to off-budget accounts count as real income/expense; internal
# uncategorized transfers never do). For category-scoped queries the
# predicate is vacuously true, keeping one uniform rule.
from igab.services.amortization import add_months

# Report payload shapes.
#
# These rows are built as plain dicts and then sorted and summed by key. Left
# untyped, each one infers as dict[str, <union of every value type>], so
# `-row["months_over"]`, `sum(r["total_inflow"] for ...)` and
# `abs(row["z_score"])` all resolve against that whole union and fail: `str`
# has no `__abs__`, `Decimal` has no unary minus in the union, and so on. The
# values are correct at runtime — the type just could not be narrowed.
#
# TypedDict pins each key to its own type, so indexing narrows and the
# arithmetic checks. total=True throughout: every key is always written.


class ChronicMonth(TypedDict):
    month: date
    assigned: Decimal
    spent: Decimal
    variance: Decimal


class ChronicCategory(TypedDict):
    category_id: str
    category_name: str
    category_group_name: str
    monthly: list[ChronicMonth]
    months_over: int
    months_active: int
    total_assigned: Decimal
    total_spent: Decimal
    avg_overspend: Decimal
    chronic: bool


class SubscriptionRow(TypedDict):
    payee_id: str
    payee_name: str
    monthly_amounts: list[Decimal]
    total: Decimal
    avg_monthly: Decimal
    avg_per_charge: Decimal
    last_charge_date: date | None
    transaction_count: int


class SavingsCategory(TypedDict):
    category_id: str
    category_name: str
    group_name: str
    monthly_balances: list[Decimal]
    current_balance: Decimal
    target_balance: Decimal | None
    total_inflow: Decimal


class AnomalyRow(TypedDict):
    category_id: str
    category_name: str
    group_name: str
    month: date
    actual: Decimal
    baseline_mean: Decimal
    z_score: float
    direction: str
    history: list[Decimal]


#: Bucket for categories a view has not placed. A string, not a UUID, so it
#: cannot collide with a real group id.
UNASSIGNED_VIEW_GROUP = "__unassigned__"


def _spending_classes(
    include: Sequence[ActivityClass] | None = None, *, scoped_accounts: bool = False
):
    """WHERE clause limiting a spending query to the requested activity classes.

    Defaults to spending alone. That is the behaviour change derkus asked for:
    a transfer to a brokerage or a mortgage is money leaving the budget, but it
    is not money spent, and counting it as spending skews every average.
    Callers that genuinely want the wider picture pass the classes they mean.

    `scoped_accounts` says the caller has an explicit account selection, which
    overrides the on-budget default — so the user may be looking straight at a
    tracked account, whose outflows classify `investment_return` (brokerage
    fees) or `debt_interest` (loan interest) and never `spending`. Without
    widening here, deliberately picking "Brokerage" in the account filter
    returned an empty chart: this predicate is ANDed into the WHERE *before*
    the scope override, so it silently cancelled the user's selection.
    """
    classes = list(include or SPENDING_CLASSES)
    if scoped_accounts:
        classes += [ActivityClass.INVESTMENT_RETURN, ActivityClass.DEBT_INTEREST]
    return ACTIVITY_CLASS.in_([c.value for c in classes])


#: Payee of record for a leaf row: its own, falling back to its split parent's.
#: Splits are one trip to the shop with the legs itemised, so the parent names
#: where the money went — but the legs are what carry categories, and therefore
#: classes. Reading the parent row instead would classify the whole basket by
#: its net sign, counting a savings-tagged leg as spending.
_split_parent = aliased(Transaction)
PAYEE_OF_RECORD = func.coalesce(Transaction.payee_id, _split_parent.payee_id)


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
        include_classes: Sequence[ActivityClass] | None = None,
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
                _spending_classes(include_classes, scoped_accounts=bool(account_ids)),
            )
        )
        if category_ids:
            q = q.where(Transaction.category_id.in_(category_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        else:
            q = q.where(ON_BUDGET_ACCOUNT)
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
                "total": Decimal(str(round(row["total"], 4))),
                "pct": float(row["total"] / grand_total * 100) if grand_total else 0.0,
            }
            for row in agg.iter_rows(named=True)
        ]
        return categories, Decimal(str(round(grand_total, 4)))

    async def income_vs_expense(self, budget_id: uuid.UUID, months: int = 12) -> list[dict]:
        """Money in, money out, per month — with saving broken out of spending.

        `expenses` used to be every negative row, which meant a transfer into a
        brokerage read as an expense. It now means spending; money that left the
        budget but stayed in the household's net worth is reported separately as
        `savings` and `debt_principal`.

        `net` remains income minus everything that left, so the four figures
        still reconcile — a chart can stack them without the total drifting.
        Internal transfers between two on-budget accounts are excluded: they
        cancel, and showing them would double the apparent flow.
        """
        today = date.today()
        first_of_month = today.replace(day=1)
        start = _subtract_months(first_of_month, months - 1)

        by_month = await self._monthly_class_totals(budget_id, start, today)

        results = []
        for i in range(months - 1, -1, -1):
            month_start = _subtract_months(first_of_month, i)
            buckets = by_month.get(month_start, {})
            income = buckets.get(ActivityClass.INCOME.value, Decimal("0"))
            # Outflow classes are stored negative; report magnitudes.
            expenses = -buckets.get(ActivityClass.SPENDING.value, Decimal("0"))
            savings = -buckets.get(ActivityClass.SAVINGS.value, Decimal("0"))
            debt = -buckets.get(ActivityClass.DEBT_PRINCIPAL.value, Decimal("0"))
            results.append(
                {
                    "month": month_start,
                    "income": income,
                    "expenses": expenses,
                    "savings": savings,
                    "debt_principal": debt,
                    "net": income - expenses - savings - debt,
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
                NOT_DELETED,
                PARENT_ROW,
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
        # Day-clamped month shift: a naive .replace(month=month-1) explodes
        # whenever start_date's day doesn't exist in the previous month
        # (July 31 → "June 31").
        prev_start = add_months(start_date, -1)
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
            # Budget cash flow: ON-BUDGET rows that are non-transfers or
            # CATEGORIZED transfer legs (spending transfers to off-budget
            # accounts). Plain activity inside tracking accounts (dividends,
            # market adjustments) moves net worth, never income/expense.
            (
                pl.col("account_id").is_in(list(on_budget_ids))
                & (~pl.col("is_transfer") | (pl.col("category_id") != ""))
            ).alias("cash_flow"),
        )

        # Parent rows carry the account-level amounts (split children would
        # double-count); leaf rows carry the categories.
        pdf = df.filter(pl.col("is_parent_row"))

        # Net worth spans EVERY account — matching net_worth_history, which
        # this card must never disagree with. Assets minus liabilities reduces
        # to the plain sum of all ledgers (transfers cancel), minus unmanaged.
        net_worth = Decimal(str(pdf.select(pl.col("amount").sum()).item() or 0))

        # Previous net worth: sum up to start_date
        net_worth_prev = Decimal(
            str(pdf.filter(pl.col("date") < start_date).select(pl.col("amount").sum()).item() or 0)
        )

        # Unmanaged liabilities reduce net worth here exactly as they do in
        # net_worth_history — the dashboard card and the report headline
        # must never disagree.
        unmanaged_now, unmanaged_series = await self._unmanaged_liabilities(budget_id)
        net_worth -= unmanaged_now
        net_worth_prev -= self._unmanaged_total_at(unmanaged_series, prev_end)

        # Every figure below reads the activity-class partition, not the sign
        # of the amount. The dashboard summarises the report tabs, so it has to
        # mean the same thing they do: reading `amount < 0` as "expense" made
        # this card announce "Savings Rate 0% / Expenses $5,000" beside a
        # Savings Rate tab reading 40% and an Income vs Expenses tab reading
        # $3,000, for the same window and the same budget.
        thirty_ago = today - timedelta(days=30)
        ninety_ago = today - timedelta(days=90)
        cdf = await self._class_frame(budget_id, min(prev_start, ninety_ago), today)

        def _cls_total(start: date, end: date, cls: ActivityClass) -> Decimal:
            window = cdf.filter(
                (pl.col("date") >= start) & (pl.col("date") <= end) & (pl.col("cls") == cls.value)
            )
            return Decimal(str(window.select(pl.col("amount").sum()).item() or 0))

        income_this = _cls_total(start_date, end_date, ActivityClass.INCOME)
        # Outflow classes are stored negative; these cards report magnitudes.
        expenses_this = -_cls_total(start_date, end_date, ActivityClass.SPENDING)
        savings_this = -_cls_total(start_date, end_date, ActivityClass.SAVINGS)
        expenses_prev = -_cls_total(prev_start, prev_end, ActivityClass.SPENDING)

        # Burn rate is how fast money is consumed, so savings and debt
        # principal are out — matching the Burn Rate chart exactly.
        burn_30 = -_cls_total(thirty_ago, today, ActivityClass.SPENDING)
        burn_90 = -_cls_total(ninety_ago, today, ActivityClass.SPENDING) / 3

        # savings / income, the same ratio the Savings Rate tab shows by
        # default. The old (income - expenses) / income counted a brokerage
        # transfer as an expense and so reported 0% for a household saving 40%.
        savings_rate = float(savings_this / income_this) if income_this > 0 else 0.0

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
                            "total": Decimal(str(round(row["total"], 4))),
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
        # EVERY account counts toward net worth — off-budget assets (brokerage,
        # HSA, property) and off-budget loans included. on_budget scopes the
        # envelope math, never the balance sheet. Closed accounts stay too:
        # their history is real and their balance flattens after closing.
        acct_q = select(
            Account.id, Account.name, Account.account_type, Account.classification
        ).where(
            Account.budget_id == budget_id,
            Account.is_deleted == False,  # noqa: E712
        )
        accounts = (await self.session.execute(acct_q)).all()

        unmanaged_now, unmanaged_series = await self._unmanaged_liabilities(budget_id)
        account_map = {str(a.id): a for a in accounts}

        q = select(Transaction.date, Transaction.amount, Transaction.account_id).where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            PARENT_ROW,
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
                "classification": [
                    account_map[str(r.account_id)].classification or "asset" for r in txns
                ],
            },
            schema_overrides={"date": pl.Date, "amount": pl.Float64},
        )

        results = []
        for i in range(months - 1, -1, -1):
            month_start = _subtract_months(first_of_month, i)
            month_end = _last_day(month_start)
            month_df = df.filter(pl.col("date") <= month_end)

            acct_balances = month_df.group_by(
                ["account_id", "account_name", "account_type", "classification"]
            ).agg(pl.col("amount").sum().alias("balance"))

            snapshots = []
            total_assets = Decimal("0")
            liability_balances = Decimal("0")

            # Sign-preserving identity math, keyed on classification: an
            # overdrawn checking account NETS ASSETS DOWN (the old bucketing
            # counted it in neither pile) and an overpaid credit card nets
            # liabilities down. net_worth == assets - liabilities always.
            for row in acct_balances.iter_rows(named=True):
                bal = Decimal(str(round(row["balance"], 4)))
                snapshots.append(
                    {
                        "account_id": row["account_id"],
                        "account_name": row["account_name"],
                        "account_type": row["account_type"],
                        "classification": row["classification"],
                        "balance": bal,
                    }
                )
                if row["classification"] == "liability":
                    liability_balances += bal
                else:
                    total_assets += bal

            # Unmanaged debts join the liability side: current total for the
            # current month, snapshot step-function for history.
            unmanaged = (
                unmanaged_now if i == 0 else self._unmanaged_total_at(unmanaged_series, month_end)
            )
            total_liabilities = -liability_balances + unmanaged

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
        # Series per type key actually present (custom types included) —
        # every point carries every key so the chart's series stay aligned.
        all_types = sorted(
            {snap["account_type"] for point in history for snap in point["accounts"]}
        )
        results = []
        for point in history:
            by_type: dict[str, Decimal] = {t: Decimal("0") for t in all_types}
            for snap in point["accounts"]:
                by_type[snap["account_type"]] += snap["balance"]
            results.append({"date": point["date"], "balances": by_type})
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
            # LEAF, not PARENT_ROW. The two sum to the same figure, but only
            # leaves carry categories and therefore classes: a split parent has
            # none, so it classified as plain spending and dragged any
            # savings-tagged leg in with it — burn rate reported $300 for a
            # split whose real spending was $100.
            LEAF,
            CASH_FLOW_ROW,
            ON_BUDGET_ACCOUNT,
            # A burn rate is how fast money is consumed. Money moved into
            # savings has not been burned.
            _spending_classes(),
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
            return await self._cash_flow_budgeted(budget_id, start_date, end_date, account_ids)
        return await self._cash_flow_spent(budget_id, start_date, end_date, account_ids)

    async def _cash_flow_budgeted(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        account_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        """Sankey based on budget assignments (no payee data).

        Assignments belong to the budget, not to accounts, so the account
        filter applies only to the transaction-derived income total.
        """
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
        if account_ids:
            income_q = income_q.where(Transaction.account_id.in_(account_ids))
        else:
            income_q = income_q.where(ON_BUDGET_ACCOUNT)
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
                ACTIVITY_CLASS.label("activity_class"),
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
        else:
            q = q.where(ON_BUDGET_ACCOUNT)
        rows = (await self.session.execute(q)).all()

        if not rows:
            return {
                "nodes": [],
                "links": [],
                "total_income": Decimal("0"),
                "total_expense": Decimal("0"),
                "total_spending": Decimal("0"),
                "total_savings": Decimal("0"),
                "total_debt_principal": Decimal("0"),
                "category_payees": {},
                "group_categories": {},
            }

        # Income at parent level (cash-flow view); expense category flows at
        # leaf level so split children reach their categories.
        income_rows = [r for r in rows if r.amount > 0 and r.parent_transaction_id is None]
        expense_rows = [r for r in rows if r.amount < 0 and not r.is_split]

        total_income = sum((r.amount for r in income_rows), Decimal("0"))
        # Everything leaving the budget. Kept as one figure because the links
        # off the budget node must sum to it — that flow conservation is what
        # makes the diagram readable, and it holds however the branches split.
        total_expense = abs(sum((r.amount for r in expense_rows), Decimal("0")))

        def _class_total(cls: ActivityClass) -> Decimal:
            return abs(
                sum(
                    (r.amount for r in expense_rows if r.activity_class == cls.value),
                    Decimal("0"),
                )
            )

        total_spending = _class_total(ActivityClass.SPENDING)
        total_savings = _class_total(ActivityClass.SAVINGS)
        total_debt_principal = _class_total(ActivityClass.DEBT_PRINCIPAL)

        nodes: list[dict] = []
        links: list[dict] = []
        node_ids: dict[str, int] = {}

        def get_node(nid: str, name: str, ntype: str, entity_id: str | None = None) -> int:
            if nid not in node_ids:
                node_ids[nid] = len(nodes)
                nodes.append({"id": nid, "name": name, "type": ntype, "entity_id": entity_id})
            return node_ids[nid]

        get_node("__budget__", "Budget", "budget")

        # Income: payees -> budget
        income_by_payee: dict[str, Decimal] = {}
        for r in income_rows:
            pname = r.payee_name or "Unknown Income"
            pid = f"inc_{r.payee_id or pname}"
            income_by_payee[pid] = income_by_payee.get(pid, Decimal("0")) + r.amount

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
                    "value": total,
                }
            )

        # Expenses: budget -> category group -> category -> top payees.
        # Uncategorized spending flows through its own pseudo group/category so
        # the links always sum to total_expense (flow conservation).
        # Keyed by (group, category), not category alone: with savings on its
        # own branch, one category can legitimately appear under two trunks —
        # ordinary spending in its real group, and a savings transfer filed to
        # the same category under Savings. Keying by category would collapse
        # them and break flow conservation.
        group_totals: dict[str, Decimal] = {}
        cat_totals: dict[tuple[str, str], Decimal] = {}
        group_names: dict[str, str] = {}
        cat_names: dict[tuple[str, str], str] = {}
        payee_by_cat: dict[tuple[str, str], dict[str, Decimal]] = {}

        # Saving and paying down debt leave the budget but are not spending, so
        # they get their own branch off the budget node instead of sitting
        # inside an expense group where they read as consumption. The real
        # categories still hang beneath, so the detail is unchanged — only
        # which trunk they belong to.
        CLASS_BRANCH = {
            ActivityClass.SAVINGS.value: ("__savings__", "Savings"),
            ActivityClass.DEBT_PRINCIPAL.value: ("__debt_principal__", "Debt Payments"),
        }

        for r in expense_rows:
            branch = CLASS_BRANCH.get(r.activity_class)
            if r.category_id:
                cat_id = str(r.category_id)
                cname = r.category_name or cat_id
                if branch:
                    gid, gname = branch
                else:
                    gid = str(r.group_id) if r.group_id else "__uncategorized__"
                    gname = r.group_name or "Uncategorized"
            elif branch:
                gid, gname = branch
                cat_id, cname = gid, gname
            else:
                cat_id = "__uncategorized__"
                gid = "__uncategorized__"
                gname = "Uncategorized"
                cname = "Uncategorized"

            slot = (gid, cat_id)
            group_totals[gid] = group_totals.get(gid, Decimal("0")) + abs(r.amount)
            cat_totals[slot] = cat_totals.get(slot, Decimal("0")) + abs(r.amount)
            group_names[gid] = gname
            cat_names[slot] = cname

            pname = r.payee_name or "Unknown"
            pid = str(r.payee_id) if r.payee_id else f"__payee_{pname}__"
            payee_by_cat.setdefault(slot, {})
            payee_by_cat[slot][pid] = payee_by_cat[slot].get(pid, Decimal("0")) + abs(r.amount)

        for gid, total in sorted(group_totals.items(), key=lambda x: -x[1]):
            get_node(f"g_{gid}", group_names.get(gid, gid), "category_group")
            links.append(
                {
                    "source": "__budget__",
                    "target": f"g_{gid}",
                    "value": total,
                }
            )

        payee_names: dict[str, str] = {}
        for r in expense_rows:
            pname = r.payee_name or "Unknown"
            pid = str(r.payee_id) if r.payee_id else f"__payee_{pname}__"
            payee_names[pid] = pname

        group_to_cats: dict[str, list[tuple[str, str]]] = {}

        category_payees: dict[str, list[dict]] = {}
        for slot, cat_payees in payee_by_cat.items():
            gid, cat_id = slot
            # Keyed by (group, category) so one category can appear under both
            # its own group and the savings/debt trunk. The composite is a
            # display key only — `entity_id` is what a drill-down needs, and
            # parsing it back out of the id sent a non-UUID to the API.
            node_id = f"c_{gid}_{cat_id}"
            group_to_cats.setdefault(gid, []).append(slot)
            get_node(node_id, cat_names[slot], "category", entity_id=cat_id)
            links.append(
                {
                    "source": f"g_{gid}",
                    "target": node_id,
                    "value": cat_totals[slot],
                }
            )
            top10 = sorted(cat_payees.items(), key=lambda x: -x[1])[:10]
            category_payees[node_id] = [
                {"name": payee_names.get(pid, "Unknown"), "total": ptotal} for pid, ptotal in top10
            ]

        group_categories: dict[str, list[dict]] = {}
        for gid, slots in group_to_cats.items():
            top10 = sorted(slots, key=lambda sl: -cat_totals.get(sl, Decimal("0")))[:10]
            group_categories[f"g_{gid}"] = [
                {"name": cat_names.get(sl, sl[1]), "total": cat_totals.get(sl, Decimal("0"))}
                for sl in top10
            ]

        return {
            "nodes": [
                {
                    "id": n["id"],
                    "name": n["name"],
                    "type": n["type"],
                    "entity_id": n.get("entity_id"),
                }
                for n in nodes
            ],
            "links": links,
            "total_income": total_income,
            "total_expense": total_expense,
            "total_spending": total_spending,
            "total_savings": total_savings,
            "total_debt_principal": total_debt_principal,
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

    # ─── Plan vs Reality ─────────────────────────────────────────────────────

    async def plan_vs_reality(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
    ) -> dict:
        """Assigned vs actually spent, per category per month.

        Deliberately ignores carryover: this report measures monthly plan
        discipline (did the month's spending fit the month's assignment?),
        not envelope health — a category living off January's surplus still
        reads as over-plan in February if nothing was assigned then.

        A month counts as "over" when spent > assigned among active months
        (any assignment or spending). Chronic = over in 3+ of the last 6
        months of the window — the signal that a plan is habitually wrong
        rather than occasionally unlucky.
        """
        today = date.today()
        first_of_month = today.replace(day=1)
        months_list = [_subtract_months(first_of_month, i) for i in range(months - 1, -1, -1)]

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
                BudgetAssignment.month.in_(months_list),
                Category.is_deleted == False,  # noqa: E712
                CategoryGroup.is_deleted == False,  # noqa: E712
                CategoryGroup.is_system == False,  # noqa: E712
            )
        )
        spend_q = (
            select(
                Transaction.category_id,
                Transaction.date,
                Transaction.amount,
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
                Transaction.date >= months_list[0],
                Transaction.date <= _last_day(months_list[-1]),
                LEAF,
                CASH_FLOW_ROW,
                Category.is_deleted == False,  # noqa: E712
                CategoryGroup.is_deleted == False,  # noqa: E712
                CategoryGroup.is_system == False,  # noqa: E712
            )
        )
        assignments = (await self.session.execute(assign_q)).all()
        spending = (await self.session.execute(spend_q)).all()

        zero = Decimal("0")
        cats: dict[str, dict] = {}

        def cat_entry(category_id, name: str, group: str) -> dict:
            cid = str(category_id)
            if cid not in cats:
                cats[cid] = {
                    "category_id": cid,
                    "category_name": name,
                    "category_group_name": group,
                    "assigned": dict.fromkeys(months_list, zero),
                    "spent": dict.fromkeys(months_list, zero),
                }
            return cats[cid]

        for r in assignments:
            m = r.month if isinstance(r.month, date) else date.fromisoformat(str(r.month))
            entry = cat_entry(r.category_id, r.category_name, r.group_name)
            entry["assigned"][m] += Decimal(str(r.assigned))
        for r in spending:
            m = r.date.replace(day=1)
            entry = cat_entry(r.category_id, r.category_name, r.group_name)
            entry["spent"][m] += abs(Decimal(str(r.amount)))

        recent = set(months_list[-6:])
        categories: list[ChronicCategory] = []
        total_assigned = zero
        total_spent = zero
        chronic_count = 0
        for entry in cats.values():
            monthly: list[ChronicMonth] = []
            months_over = 0
            months_active = 0
            recent_over = 0
            over_total = zero
            for m in months_list:
                assigned = entry["assigned"][m]
                spent = entry["spent"][m]
                over = spent > assigned
                if assigned != zero or spent != zero:
                    months_active += 1
                    if over:
                        months_over += 1
                        over_total += spent - assigned
                        if m in recent:
                            recent_over += 1
                monthly.append(
                    {"month": m, "assigned": assigned, "spent": spent, "variance": assigned - spent}
                )
            cat_assigned = sum(entry["assigned"].values(), zero)
            cat_spent = sum(entry["spent"].values(), zero)
            chronic = recent_over >= 3
            if chronic:
                chronic_count += 1
            avg_overspend = (
                (over_total / months_over).quantize(Decimal("0.01")) if months_over else zero
            )
            categories.append(
                {
                    "category_id": entry["category_id"],
                    "category_name": entry["category_name"],
                    "category_group_name": entry["category_group_name"],
                    "monthly": monthly,
                    "months_over": months_over,
                    "months_active": months_active,
                    "total_assigned": cat_assigned,
                    "total_spent": cat_spent,
                    "avg_overspend": avg_overspend,
                    "chronic": chronic,
                }
            )
            total_assigned += cat_assigned
            total_spent += cat_spent

        categories.sort(
            key=lambda c: (
                not c["chronic"],
                -c["months_over"],
                -c["total_spent"],
                c["category_name"],
            )
        )
        return {
            "months": months_list,
            "categories": categories,
            "total_assigned": total_assigned,
            "total_spent": total_spent,
            "chronic_count": chronic_count,
        }

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
        include_classes: Sequence[ActivityClass] | None = None,
        view_id: uuid.UUID | None = None,
    ) -> tuple[list[dict], Decimal, dict]:
        """Spending rolled up by group.

        With `view_id`, the groups come from that view's arrangement instead of
        the budget's own — the same money read a different way, which is the
        point of a view. Categories the view hides drop out; ones it has not
        placed collect under "Unassigned", or drop out too if the view says so.

        The third element is a notes dict explaining what the report left out,
        so the chart can say so instead of silently shrinking:

        - ``view_hidden``: ``{"categories": n, "total": Decimal}`` or None —
          spending dropped because the active view hides those categories.
        - ``class_excluded``: per-class list or None — activity in categories
          the user is looking at (their selection, or the view's visible set)
          that is savings / debt payment rather than spending. A car payment
          that "vanishes" from a spending report is this, and without the note
          the exclusion is indistinguishable from data loss.

        The groups/total shape is identical either way, so the client-side
        rollup does not care which arrangement produced it.
        """
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
                _spending_classes(include_classes, scoped_accounts=bool(account_ids)),
            )
        )
        if category_ids:
            q = q.where(Transaction.category_id.in_(category_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        else:
            q = q.where(ON_BUDGET_ACCOUNT)
        rows = (await self.session.execute(q)).all()

        # `_view_arrangement` returns None for a view that does not exist or
        # belongs to another budget. Falling back to the budget's own groups
        # there is right — an empty report would be worse — but it must be
        # visible: reportStore persists viewId outside any budget scope, so
        # deleting a view in another tab, or switching budgets, otherwise left
        # the page charting one arrangement while still requesting another.
        regroup = await self._view_arrangement(budget_id, view_id) if view_id else None
        view_unavailable = view_id is not None and regroup is None
        dropped_by_view: dict | None = None
        if regroup is not None:
            dropped = [r for r in rows if regroup(r.id) is None]
            if dropped:
                dropped_by_view = {
                    "categories": len({r.id for r in dropped}),
                    "total": sum((abs(r.amount) for r in dropped), Decimal("0")),
                }
            rows = [r for r in rows if regroup(r.id) is not None]

        class_excluded = await self._class_excluded(
            budget_id,
            start_date,
            end_date,
            category_ids,
            account_ids,
            include_classes,
            regroup,
        )
        notes = {
            "view_hidden": dropped_by_view,
            "class_excluded": class_excluded,
            "view_unavailable": view_unavailable,
        }

        # The all-hidden case still carries the notes: an empty chart with
        # no explanation is exactly the failure these exist to prevent.
        if not rows:
            return [], Decimal("0"), notes

        def _group_of(r) -> tuple[str, str]:
            if regroup is None:
                return str(r.group_id), r.group_name
            placed = regroup(r.id)
            assert placed is not None  # filtered above
            return placed

        df = pl.DataFrame(
            {
                "cat_id": [str(r.id) for r in rows],
                "cat_name": [r.name for r in rows],
                "group_id": [_group_of(r)[0] for r in rows],
                "group_name": [_group_of(r)[1] for r in rows],
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
                "total": Decimal(str(round(row["total"], 4))),
                "count": int(row["count"]),
                "pct": float(row["total"] / grand_total * 100) if grand_total else 0.0,
            }
            for row in cat_agg.iter_rows(named=True)
        ]

        return items, Decimal(str(round(grand_total, 4))), notes

    async def _class_excluded(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        category_ids: list[uuid.UUID] | None,
        account_ids: list[uuid.UUID] | None,
        include_classes: Sequence[ActivityClass] | None,
        regroup,
    ) -> list[dict] | None:
        """Savings / debt activity inside the user's current scope that a
        spending report will not count.

        Only computed when the user has *pointed at* categories — an explicit
        selection or an active view — because that is when absence misleads:
        "I selected Car Payment and it isn't here" reads as a bug, not a
        definition. The unfiltered report stays calm; the info panel already
        explains the general rule.
        """
        if not category_ids and regroup is None:
            return None

        included = set(include_classes or SPENDING_CLASSES)
        targets = [
            c
            for c in (
                ActivityClass.SAVINGS,
                ActivityClass.DEBT_PRINCIPAL,
                ActivityClass.DEBT_INTEREST,
            )
            if c not in included
        ]
        if not targets:
            return None

        q = (
            select(
                Category.id,
                ACTIVITY_CLASS.label("activity_class"),
                func.sum(func.abs(Transaction.amount)).label("total"),
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
                ACTIVITY_CLASS.in_([c.value for c in targets]),
            )
            .group_by(Category.id, ACTIVITY_CLASS)
        )
        if category_ids:
            q = q.where(Transaction.category_id.in_(category_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        else:
            q = q.where(ON_BUDGET_ACCOUNT)

        rows = (await self.session.execute(q)).all()
        # A view scopes what the user sees — activity in categories the view
        # hides is the view_hidden note's story, not this one's.
        if regroup is not None:
            rows = [r for r in rows if regroup(r.id) is not None]
        if not rows:
            return None

        by_class: dict[str, dict] = {}
        for r in rows:
            slot = by_class.setdefault(
                r.activity_class,
                {"activity_class": r.activity_class, "categories": set(), "total": Decimal("0")},
            )
            slot["categories"].add(r.id)
            slot["total"] += r.total
        return sorted(
            (
                {
                    "activity_class": v["activity_class"],
                    "label": CLASS_LABEL[ActivityClass(v["activity_class"])],
                    "categories": len(v["categories"]),
                    # Storage is 4dp; the note is user-facing copy, so cents.
                    "total": v["total"].quantize(Decimal("0.01")),
                }
                for v in by_class.values()
            ),
            key=lambda v: v["total"],
            reverse=True,
        )

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
                "total": Decimal(str(round(row["total"], 4))),
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
                PAYEE_OF_RECORD.label("payee_id"),
                Transaction.category_id,
                Payee.name.label("payee_name"),
                Category.name.label("category_name"),
            )
            .outerjoin(_split_parent, Transaction.parent_transaction_id == _split_parent.id)
            .outerjoin(Payee, PAYEE_OF_RECORD == Payee.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                Transaction.amount < 0,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                # Leaves, so each split leg classifies on its own category;
                # the payee still comes from the parent row via PAYEE_OF_RECORD.
                LEAF,
                CASH_FLOW_ROW,
                PAYEE_OF_RECORD.isnot(None),
                # Otherwise "Transfer : Brokerage" ranks as a top payee, which
                # is true and useless — it is not somewhere money was spent.
                _spending_classes(scoped_accounts=bool(account_ids)),
            )
        )
        if payee_ids:
            q = q.where(PAYEE_OF_RECORD.in_(payee_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        else:
            q = q.where(ON_BUDGET_ACCOUNT)
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

        grand_total = Decimal(str(round(payee_agg["total"].sum(), 4)))

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
                {"month": r["month"], "total": Decimal(str(round(r["total"], 4)))}
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
                {"category_name": r["category_name"], "total": Decimal(str(round(r["total"], 4)))}
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
                    "total": Decimal(str(round(row["total"], 4))),
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
            _spending_classes(scoped_accounts=bool(account_ids)),
        )
        if category_ids:
            q = q.where(Transaction.category_id.in_(category_ids))
        if account_ids:
            q = q.where(Transaction.account_id.in_(account_ids))
        else:
            q = q.where(ON_BUDGET_ACCOUNT)
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
                # Not filtered by class: a large transfer into savings really is
                # one of the largest transactions, and a timeline that hid it
                # would misrepresent what moved. But colouring by sign called it
                # an expense — the same mislabelling this taxonomy exists to fix
                # — so the class rides along and the chart labels it honestly.
                ACTIVITY_CLASS.label("activity_class"),
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
        else:
            q = q.where(ON_BUDGET_ACCOUNT)
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
                "activity_class": r.activity_class,
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
                NOT_DELETED,
                POSTED,
                Transaction.amount < 0,  # outflows only
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                LEAF,
                ON_BUDGET_ACCOUNT,
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
        subscriptions: list[SubscriptionRow] = []
        for payee_id in df["payee_id"].unique().to_list():
            payee_rows = payee_monthly.filter(pl.col("payee_id") == payee_id)
            payee_name = payee_rows["payee_name"][0]

            # Monthly amounts for each month in the range
            monthly_amounts = []
            for m in month_list:
                row = payee_rows.filter(pl.col("month") == m)
                if len(row) > 0:
                    monthly_amounts.append(Decimal(str(round(row["monthly_total"][0], 4))))
                else:
                    monthly_amounts.append(Decimal("0"))

            total = sum(monthly_amounts, Decimal("0"))

            # Last charge date and count
            payee_txns = df.filter(pl.col("payee_id") == payee_id)
            last_charge = max(payee_txns["date"].to_list()) if len(payee_txns) > 0 else None
            txn_count = len(payee_txns)

            # avg_monthly is the TRUE monthly burden: total spread over the
            # months since the first charge, not the average charged month —
            # a quarterly $30 sub costs $10/mo, not $30/mo.
            first_charged_idx = next((i for i, a in enumerate(monthly_amounts) if a > 0), None)
            if first_charged_idx is None:
                avg_monthly = Decimal("0")
            else:
                avg_monthly = total / (len(month_list) - first_charged_idx)
            avg_per_charge = total / txn_count if txn_count else Decimal("0")

            subscriptions.append(
                {
                    "payee_id": payee_id,
                    "payee_name": payee_name,
                    "monthly_amounts": monthly_amounts,
                    "total": total,
                    "avg_monthly": avg_monthly.quantize(Decimal("0.01")),
                    "avg_per_charge": avg_per_charge.quantize(Decimal("0.01")),
                    "last_charge_date": last_charge,
                    "transaction_count": txn_count,
                }
            )

        # Sort by total descending
        subscriptions.sort(key=lambda x: x["total"], reverse=True)

        # Summary
        total_monthly = sum((s["avg_monthly"] for s in subscriptions), Decimal("0"))
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

    async def _class_frame(self, budget_id: uuid.UUID, start: date, end: date) -> pl.DataFrame:
        """(date, amount, class) for on-budget leaf rows, for window slicing.

        Same rows and same classification as `_monthly_class_totals`; that one
        groups by month in SQL, this one hands back the rows so a caller can
        cut arbitrary windows (30 days, previous period) without a query each.
        """
        rows = (
            await self.session.execute(
                select(
                    Transaction.date,
                    Transaction.amount,
                    ACTIVITY_CLASS.label("cls"),
                ).where(
                    Transaction.budget_id == budget_id,
                    NOT_DELETED,
                    POSTED,
                    LEAF,
                    Transaction.date >= start,
                    Transaction.date <= end,
                    ON_BUDGET_ACCOUNT,
                )
            )
        ).all()
        return pl.DataFrame(
            {
                "date": [r.date for r in rows],
                "amount": [float(r.amount) for r in rows],
                "cls": [r.cls for r in rows],
            },
            schema_overrides={"date": pl.Date, "amount": pl.Float64, "cls": pl.String},
        )

    async def _monthly_class_totals(
        self, budget_id: uuid.UUID, start: date, end: date
    ) -> dict[date, dict[str, Decimal]]:
        """month -> activity class -> signed total, for on-budget rows.

        LEAF, not PARENT_ROW. The two sum to the same figure (money
        conservation), but only leaves carry a category, and a split parent can
        mix classes across its legs — one bank row holding both groceries and a
        transfer into savings. Aggregating the parent would force that row into
        a single class chosen by its net sign.
        """
        month_col = func.date_trunc(literal_column("'month'"), Transaction.date).label("month")
        q = (
            select(
                month_col,
                ACTIVITY_CLASS.label("cls"),
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            )
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                LEAF,
                Transaction.date >= start,
                Transaction.date <= end,
                ON_BUDGET_ACCOUNT,
            )
            .group_by(month_col, ACTIVITY_CLASS)
        )
        rows = (await self.session.execute(q)).all()

        by_month: dict[date, dict[str, Decimal]] = {}
        for row in rows:
            key = row.month.date() if hasattr(row.month, "date") else row.month
            by_month.setdefault(key, {})[row.cls] = Decimal(str(row.total))
        return by_month

    async def _view_arrangement(self, budget_id: uuid.UUID, view_id: uuid.UUID):
        """Return `category_id -> (group_id, group_name)` for one view, or None
        for a category the view leaves out.

        Mirrors the budget page's `groupByView` so a report and the grid never
        disagree about where a category sits: hidden placements are dropped,
        unplaced ones fall to "Unassigned" unless the view hides those too.
        """
        view = (
            await self.session.execute(
                select(BudgetView).where(
                    BudgetView.id == view_id,
                    BudgetView.budget_id == budget_id,
                    BudgetView.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if view is None:
            return None

        group_names = {
            g.id: g.name
            for g in (
                await self.session.execute(
                    select(BudgetViewGroup).where(BudgetViewGroup.view_id == view_id)
                )
            )
            .scalars()
            .all()
        }
        placements = {
            p.category_id: p
            for p in (
                await self.session.execute(
                    select(BudgetViewPlacement).where(BudgetViewPlacement.view_id == view_id)
                )
            )
            .scalars()
            .all()
        }
        hide_unassigned = view.hide_unassigned

        def arrange(category_id) -> tuple[str, str] | None:
            placement = placements.get(category_id)
            if placement is not None and placement.is_hidden:
                return None
            group_id = placement.group_id if placement else None
            if group_id is None:
                if hide_unassigned:
                    return None
                return UNASSIGNED_VIEW_GROUP, "Unassigned"
            return str(group_id), group_names.get(group_id, "Unassigned")

        return arrange

    # ─── Savings Rate ─────────────────────────────────────────────────────────

    async def savings_rate(self, budget_id: uuid.UUID, months: int = 12) -> dict:
        """How much of what came in was kept, month by month.

        derkus asked for this directly: "i would like there to be categories
        that are classified as savings and be able to track my savings rate as
        compared to income and/or all spending".

        Two rates, because paying down a mortgage and funding a brokerage both
        build net worth but people think about them differently:

            savings_rate           = savings / income
            savings_rate_with_debt = (savings + debt_principal) / income

        Scoped to on-budget accounts, which is what makes the number honest:
        growth inside a tracked account classifies as `investment_return` and
        is left out. A savings rate that counted market gains as saving would
        rise in a bull market without the household doing anything.

        A month with no income yields a rate of None rather than 0 — "no income
        recorded" and "saved nothing" are different facts, and a chart should
        show a gap rather than a floor.
        """
        today = date.today()
        first = today.replace(day=1)
        start = _subtract_months(first, months - 1)

        by_month = await self._monthly_class_totals(budget_id, start, today)

        def _rate(numerator: Decimal, income: Decimal) -> float | None:
            if income <= 0:
                return None
            return float(numerator / income)

        series: list[dict] = []
        for i in range(months - 1, -1, -1):
            month = _subtract_months(first, i)
            buckets = by_month.get(month, {})
            income = buckets.get(ActivityClass.INCOME.value, Decimal("0"))
            # Outflow classes are stored negative; report them as magnitudes.
            savings = -buckets.get(ActivityClass.SAVINGS.value, Decimal("0"))
            debt = -buckets.get(ActivityClass.DEBT_PRINCIPAL.value, Decimal("0"))
            spending = -buckets.get(ActivityClass.SPENDING.value, Decimal("0"))
            series.append(
                {
                    "month": month,
                    "income": income,
                    "spending": spending,
                    "savings": savings,
                    "debt_principal": debt,
                    "savings_rate": _rate(savings, income),
                    "savings_rate_with_debt": _rate(savings + debt, income),
                }
            )

        totals = {
            key: sum((m[key] for m in series), Decimal("0"))
            for key in ("income", "spending", "savings", "debt_principal")
        }
        return {
            "months": series,
            "summary": {
                **totals,
                "savings_rate": _rate(totals["savings"], totals["income"]),
                "savings_rate_with_debt": _rate(
                    totals["savings"] + totals["debt_principal"], totals["income"]
                ),
            },
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

        # Get category activity (transactions) per month for running balance.
        # literal_column inlines 'month' so SELECT and GROUP BY render the
        # same expression — as a bound parameter Postgres rejects the query.
        month_col = func.date_trunc(literal_column("'month'"), Transaction.date).label("month")
        txn_q = (
            select(
                Transaction.category_id,
                month_col,
                func.sum(Transaction.amount).label("activity"),
            )
            .where(
                Transaction.budget_id == budget_id,
                Transaction.category_id.in_(savings_cat_ids),
                NOT_DELETED,
                POSTED,
                LEAF,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
            .group_by(Transaction.category_id, month_col)
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
                NOT_DELETED,
                POSTED,
                LEAF,
                Transaction.date < start_date,
            )
            .group_by(Transaction.category_id)
        )
        prior_activity_rows = (await self.session.execute(prior_activity_q)).all()
        prior_activity = {str(r.category_id): r.total or Decimal("0") for r in prior_activity_rows}

        # Build category results
        categories: list[SavingsCategory] = []
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
        total_balance = sum((c["current_balance"] for c in categories), Decimal("0"))
        total_inflow = sum((c["total_inflow"] for c in categories), Decimal("0"))
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
                NOT_DELETED,
                POSTED,
                Transaction.amount < 0,  # outflows only
                LEAF,
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

        anomalies: list[AnomalyRow] = []

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

        # All cash-flow rows in the period. CASH_FLOW_ROW keeps transfers out:
        # a transfer into checking is not a payday, and the outflow leg of a
        # transfer is not spending.
        q = (
            select(
                Transaction.date,
                Transaction.amount,
                Transaction.payee_id,
            )
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                LEAF,
                CASH_FLOW_ROW,
                ON_BUDGET_ACCOUNT,
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
                NOT_DELETED,
                PARENT_ROW,
                POSTED,
                Account.is_closed == False,  # noqa: E712
                Account.on_budget == True,  # noqa: E712
            )
        )
        result = await self.session.execute(q)
        start_balance = Decimal(str(result.scalar() or 0))

        # 2. Get scheduled transactions in the projection window. The
        # projection covers on-budget cash, so schedules pointed at
        # off-budget or closed accounts don't belong in it.
        sched_q = (
            select(
                ScheduledTransaction.id,
                ScheduledTransaction.amount,
                ScheduledTransaction.next_occurrence_date,
                ScheduledTransaction.frequency,
                ScheduledTransaction.end_date,
                Payee.name.label("payee_name"),
            )
            .join(Account, Account.id == ScheduledTransaction.account_id)
            .outerjoin(Payee, Payee.id == ScheduledTransaction.payee_id)
            .where(
                ScheduledTransaction.budget_id == budget_id,
                ScheduledTransaction.is_deleted == False,  # noqa: E712
                ScheduledTransaction.next_occurrence_date <= end_date,
                Account.is_closed == False,  # noqa: E712
                Account.on_budget == True,  # noqa: E712
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
                .join(Account, Account.id == Transaction.account_id)
                .where(
                    Transaction.budget_id == budget_id,
                    NOT_DELETED,
                    POSTED,
                    LEAF,
                    Transaction.payee_id.in_(subscription_payee_ids),
                    Transaction.amount < 0,
                    Account.is_closed == False,  # noqa: E712
                    Account.on_budget == True,  # noqa: E712
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

        # 4. Get historical daily net flows for stochastic layer — on-budget
        # open accounts only, matching the balance being projected (a
        # brokerage swing is not a cash flow).
        hist_start = today - timedelta(days=180)
        hist_q = (
            select(Transaction.date, Transaction.amount)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                LEAF,
                Transaction.date >= hist_start,
                Transaction.date < today,
                Account.is_closed == False,  # noqa: E712
                Account.on_budget == True,  # noqa: E712
            )
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
            # sort() makes the weekday buckets order-stable: group_by returns
            # rows in arbitrary order, and the seeded rng.choice() below is
            # only reproducible when each bucket lists its samples in a fixed
            # order (same-day calls must return identical projections).
            daily = df.group_by("date").agg(pl.col("amount").sum().alias("net")).sort("date")
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
        # Clamp like the monthly branch: Feb 29 -> Feb 28 in non-leap years
        day = min(d.day, _last_day(date(d.year + 1, d.month, 1)).day)
        return date(d.year + 1, d.month, day)
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
