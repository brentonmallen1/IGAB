import io
import json
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import NamedTuple, TypedDict

import polars as pl
from sqlalchemy import Row, Select, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from igab.db.models import (
    Account,
    BudgetAssignment,
    BudgetView,
    BudgetViewGroup,
    BudgetViewPlacement,
    Category,
    CategoryGroup,
    Payee,
    Transaction,
)
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    DISCRETIONARY_ROW,
    INCOME_ROW,
    NOT_OPENING_BALANCE,
    ActivityClass,
    apply_class_joins,
    counted_classes,
    rolled_up_classes,
    split_leg_classes,
)

# CASH_FLOW_ROW: plain rows plus categorized transfer legs (spending
# transfers to off-budget accounts count as real income/expense; internal
# uncategorized transfers never do). For category-scoped queries the
# predicate is vacuously true, keeping one uniform rule.
from igab.domain.burn_rate import (
    Burn,
    DayClassTotal,
    burn,
    burn_as_of,
    burn_windows,
)
from igab.domain.cash_flow import (
    HUB_CLASSES,
    AssignedRow,
    FlowRow,
    budgeted_diagram,
    spent_diagram,
)

# Aliased: `report_basics.history_window` is the per-month reports' window;
# this one is the projection sampler's whole-week stretch of days.
from igab.domain.cash_projection import history_window as projection_history
from igab.domain.cash_projection import project, zero_filled
from igab.domain.dates import (
    ReportWindow,
    month_starts,
    months_spanned,
    previous_window,
    report_window,
    weekday_counts,
)
from igab.domain.dates import month_end as _month_end
from igab.domain.money import format_csv_amount, quantize_cents
from igab.domain.money_moves import Figures, figures, flows
from igab.domain.plan import CHRONIC_WINDOW, is_chronic, plan_outcome, total_variance
from igab.domain.schedule import projected_occurrences, subscription_occurrences
from igab.domain.spending import UNCATEGORIZED, spent
from igab.domain.tracking_start import (
    STALE_AFTER_DAYS,
    Entry,
    StatedValue,
    entered,
    is_stale,
    like_for_like,
    stated_total,
)
from igab.domain.view_arrangement import arrange_by_view
from igab.repositories.account_repo import AccountRepository
from igab.repositories.account_type_repo import AccountTypeRepository
from igab.repositories.category_filters import BUDGETED_ENVELOPE
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import (
    CASH_ACCOUNT,
    CASH_FLOW_ROW,
    CLASS_TOTAL_ROW,
    LEAF,
    LIVE_ACCOUNT,
    NOT_DELETED,
    ON_BUDGET_ACCOUNT,
    ON_CARD_ACCOUNT,
    PARENT_ROW,
    PAYEE_OF_RECORD,
    POSTED,
    SPENDING_ROW,
    SUBSCRIPTION_CHARGE,
    account_scope,
    category_tagged,
    in_category_scope,
    join_split_parent,
    none_of,
    reapplied_by_schedule,
    reapplied_by_subscriptions,
)
from igab.services.essentials import reported_essentials
from igab.services.plan_ledger import PlanMonth, ledger_rows, plan_ledger
from igab.services.report_basics import (
    budget_window,
    class_excluded_note,
    history_window,
    means_months,
)
from igab.services.report_day import reader_today
from igab.services.report_scope import scoped
from igab.services.report_stats import (
    anomaly_scan,
    balance_sheet,
    category_month_grid,
    payee_rollup,
    timeline_rows,
    volatility_stats,
    weekday_rollup,
)
from igab.services.runway import runway_read
from igab.services.savings_held import held_between, held_by_month
from igab.services.tracking_start import entries_by_point, last_moved, stated_values

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
    moved_in: Decimal
    moved_out: Decimal
    plan: Decimal
    spent: Decimal
    variance: Decimal
    over: bool
    active: bool


class ChronicCategory(TypedDict):
    category_id: str
    category_name: str
    category_group_name: str
    monthly: list[ChronicMonth]
    months_over: int
    months_active: int
    total_assigned: Decimal
    total_moved_in: Decimal
    total_moved_out: Decimal
    total_spent: Decimal
    avg_overspend: Decimal
    chronic: bool
    sinking_fund: bool


#: The smallest inflow that counts as a payday.
#:
#: Absolute, deliberately. `payday_effect` used the P75 of every inflow, so a
#: relative quartile decided which paydays existed — and a quartile of a
#: varying wage discards three quarters of them. A floor only has to be low
#: enough to catch a real wage and high enough to ignore a refund.
PAYDAY_FLOOR = Decimal("200")


class BalanceSheets(NamedTuple):
    """`ReportService._balance_sheets`: a sheet per cutoff, what entered each
    point's stretch, and the stated values the sheets read."""

    sheets: list[dict]
    entries: list[list[Entry]]
    stated: list[StatedValue]


class SpendingRows(NamedTuple):
    """`ReportService._spending_rows`: the rows a spending report counts, the
    rows in its scope it does not (for `class_excluded_note`), and the class
    values it counted — served, so a drill-down lists what the chart totals."""

    counted: list[Row]
    excluded: list[Row]
    classes: list[str]


#: How many categories the Seasonality heatmap draws, largest first. The
#: count of the rest is served beside them, so the page says "top 20 of N".
SEASONALITY_TOP = 20


def _rate_figures(f: Figures) -> dict:
    """One Savings Rate row — a month or the summary — from its figures."""
    return {
        "income": f.income,
        "spending": f.spending,
        "savings": f.savings,
        "savings_moved": f.savings_moved,
        "savings_held": f.savings_held,
        "debt_principal": f.debt_principal,
        "savings_rate": f.savings_rate,
        "savings_rate_with_debt": f.savings_rate_with_debt,
    }


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.txns = TransactionRepository(session)
        self.accounts = AccountRepository(session)
        self.session = session

    async def available_range(self, budget_id: uuid.UUID, today: date | None = None) -> dict:
        """How far back this budget's reports can look.

        Served so the range picker offers only windows that exist: a budget
        with eighteen months of history has no 24-month view to give, and
        offering one draws six empty leading months that read as a data loss.
        It is also what "All" resolves to — the client cannot know it, and the
        alternative (asking for a very large number of months) is the same
        empty-months problem with extra steps.
        """
        earliest = await self.txns.earliest_date(budget_id)
        return {
            "earliest_month": earliest.replace(day=1) if earliest else None,
            "months_available": months_spanned(earliest, reader_today(today)) if earliest else 0,
        }

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
        """Spending per category, largest first: the AI spending tool and — its
        first three rows — the Overview's Top Spending card. Net of refunds,
        with uncategorized spending as its own line (id None).

        `_spending_rows`, not a hand copy of them. The copy was one term short
        of it (`SPENT_ENVELOPE`), the card was a second copy three terms
        short, and Decimal throughout rather than a float sum.
        """
        found = await self._spending_rows(
            budget_id, start_date, end_date, category_ids, account_ids, include_classes
        )
        by_cat: dict[uuid.UUID | None, dict] = {}
        for r in found.counted:
            by_cat.setdefault(
                r.id,
                {
                    "id": r.id,
                    "name": r.name or UNCATEGORIZED,
                    "group_name": r.group_name or UNCATEGORIZED,
                    "amounts": [],
                },
            )["amounts"].append(r.amount)
        categories = [
            {**{k: c[k] for k in ("id", "name", "group_name")}, "total": spent(c["amounts"])}
            for c in by_cat.values()
        ]
        grand_total = sum((c["total"] for c in categories), Decimal("0"))
        categories.sort(key=lambda c: c["total"], reverse=True)
        for c in categories:
            c["pct"] = float(c["total"] / grand_total * 100) if grand_total > 0 else 0.0
        return categories, grand_total

    async def income_vs_expense(
        self, budget_id: uuid.UUID, months: int = 12, today: date | None = None
    ) -> list[dict]:
        """Money in, money out, per month — with saving broken out of spending.

        `expenses` used to be every negative row, which meant a transfer into a
        brokerage read as an expense. It now means spending; money that left the
        budget but stayed in the household's net worth is reported separately as
        `savings` and `debt_principal`.

        `savings` is saved — moved plus held (`domain.savings`), the figure the
        Savings Rate tab divides — served with its two parts.

        **`net` is money-moved, deliberately:** income − expenses −
        `savings_moved` − debt principal. It reconciles to what the on-budget
        accounts did, and money assigned to a kept-here envelope never left
        them, so subtracting held would report a deficit the balances do not
        show. So `net` ≠ income − expenses − savings − debt by exactly
        `savings_held`, and no more (pinned by
        `test_income_vs_expense_net_stays_money_moved`). Internal transfers
        between two on-budget accounts are excluded: they cancel, and showing
        them would double the apparent flow.
        """
        today = reader_today(today)
        window, series = await self._class_series(budget_id, months, today)
        held = await held_by_month(self.session, budget_id, [m for m, _ in series], today)
        results = []
        for (month_start, buckets), month_held in zip(series, held, strict=True):
            f = figures(buckets, month_held)
            results.append(
                {
                    "month": month_start,
                    "partial_month": window.is_running(month_start),
                    "income": f.income,
                    "expenses": f.spending,
                    "savings": f.savings,
                    "savings_moved": f.savings_moved,
                    "savings_held": f.savings_held,
                    "debt_principal": f.debt_principal,
                    "net": f.income - f.spending - f.savings_moved - f.debt_principal,
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
                # `format_csv_amount`, not `str(Decimal)`: the column dtype
                # is stored NUMERIC(12,4), so `str` wrote "-42.5000" where
                # every other export in this app writes "-42.50" — and
                # `parse_csv_amount`, the exact inverse, is what reads these
                # files back in. An f-string or a bare `str` at a call site is
                # how the two directions drift.
                "amount": [format_csv_amount(r.amount) for r in rows],
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
        today: date | None = None,
    ) -> dict:
        # The reader's day (`report_day`): every figure below is "as of today".
        today = reader_today(today)
        # "vs prior period" is the equal-length window before this one — the
        # month before `start`, as this was, held a twelve-day month-to-date
        # against a whole prior month. `prev_end` is also the net-worth "before".
        prev_start, prev_end = previous_window(start_date, end_date)

        # This used to pull EVERY posted row in the budget into Python to
        # answer two scalar sums and a top-three. Each figure below now asks
        # the one rule its report tab reads, so none can drift from its tab.

        # Net worth "now" and as it stood the day before the window, from the
        # one rule the net-worth chart reads (`_balance_sheets`). This card
        # was its own SQL sum beside the chart's per-account walk, linked by
        # a comment saying they must never disagree — and their date bounds
        # had already drifted. An empty budget takes the same path: it had a
        # short-circuit of its own that restated the composition, set prev to
        # "now", and so drew a 0.0% change the chart beside it contradicted.
        #
        # Its change is like-for-like, the Net Worth report's headline rule:
        # less what began being counted since the "before". Linking accounts
        # and first valuing a house inside the range read "+225.5%" here, for
        # a household whose like-for-like year was slightly down.
        both = await self._balance_sheets(
            budget_id, [prev_end, today], today, since=prev_end + timedelta(days=1)
        )
        prev_sheet, now_sheet = both.sheets
        net_worth, net_worth_prev = now_sheet["net_worth"], prev_sheet["net_worth"]
        net_worth_entered = entered(both.entries[1])

        # Every figure below reads the activity-class partition, not the sign
        # of the amount. The dashboard summarises the report tabs, so it has to
        # mean the same thing they do: reading `amount < 0` as "expense" made
        # this card announce "Savings Rate 0% / Expenses $5,000" beside a
        # Savings Rate tab reading 40% and an Income vs Expenses tab reading
        # $3,000, for the same window and the same budget.
        cdf = await self._class_frame(budget_id, prev_start, today)

        def _buckets(start: date, end: date) -> dict[str, Decimal]:
            """class -> signed total over a window: the shape the month-bucketed
            tabs hand `class_magnitude`, so the cards flip signs by the same rule
            rather than a window-sized copy of it."""
            window = cdf.filter((pl.col("date") >= start) & (pl.col("date") <= end))
            totals = window.group_by("cls").agg(pl.col("amount").sum())
            return {cls: Decimal(str(amount)) for cls, amount in totals.iter_rows()}

        # The window's figures through `money_moves.figures`, the one reading
        # of class buckets the report tabs and the Guide's worked month share.
        # This card flipped each class's sign itself beside it — the same
        # arithmetic twice, one refactor from disagreeing. `cost_of_living` is
        # every class in COST_OF_LIVING_CLASSES, the one tuple Cost of Living
        # and the Essentials figures read, so the Overview's means verdict
        # cannot count a class those reports do not. Debt payments are served
        # beside it because the verdict's dialog names them; savings are
        # neither: they are what was left over.
        #
        # The savings rate is savings / income, the ratio the Savings Rate tab
        # shows by default — debt payments only when its toggle adds them. (The
        # tab used to open with them on, so this card and that tab disagreed
        # about the same month by the month's debt payments.) The old
        # (income - expenses) / income counted a brokerage transfer as an
        # expense and reported 0% for a household saving 40%. None, not 0.0,
        # when nothing came in: "no income recorded" and "saved nothing" are
        # different facts.
        #
        # Saved is moved plus held (`domain.savings`), held read over the same
        # window the frame is cut to: the day before `start` through today at
        # the latest. The prior window's spending is a row sum, so `flows`.
        held = await held_between(self.session, budget_id, start_date, min(end_date, today))
        this = figures(_buckets(start_date, end_date), held)
        expenses_prev = flows(_buckets(prev_start, prev_end)).spending

        # The burn and what it is compared with: the Burn Rate chart's newest
        # point, through the same service path and the same domain rule
        # (`domain.burn_rate`), so the card and the chart agree by construction
        # rather than by a comment claiming they do: one such comment already
        # sat over a card and a chart that disagreed about refunds.
        (now_burn,) = await self._burns(budget_id, [burn_as_of(today)])

        # What a lean month costs — the Guide's figure, from the Guide's window,
        # so this card and the roadmap's emergency-fund target never disagree.
        # None until something is tagged: the untagged fallback IS burn rate,
        # and a second card saying the same number would mislead.
        essentials, essentials_tagged = await reported_essentials(self.session, budget_id, today)

        # Runway — how long the money lasts if income stopped, at the
        # Overview's choice (Essentials against the cash and the emergency
        # fund, card debt taken out), from the one rule every runway reads
        # (`services.runway`). This was "Days Until Zero": the cash ÷ the last
        # thirty days' burn, which assumed every kind of spending carried on,
        # counted checking alone and ignored both the cards and the savings —
        # a budget whose checking never dipped below a month's pay read 17
        # days.
        runway = await runway_read(self.session, budget_id, today)

        # Top Spending is the Breakdown's first three rows, not a second query
        # kept agreeing with it. It was one — the class filter, the envelope
        # rule and the truncation order each copied across after the card had
        # drifted three ways — under a comment calling its missing on-budget
        # term deliberate, though a categorized transfer leg sits on the
        # on-budget side and passes `ON_BUDGET_ACCOUNT` (see its comment).
        breakdown, _spent = await self.spending_by_category(budget_id, start_date, end_date)
        top_cats = [
            {**{k: c[k] for k in ("id", "name", "group_name")}, "total": quantize_cents(c["total"])}
            for c in breakdown[:3]
        ]

        return {
            "net_worth": net_worth,
            "net_worth_prev": net_worth_prev,
            "net_worth_entered": net_worth_entered,
            "net_worth_change": like_for_like(
                [net_worth_prev, net_worth], [Decimal("0"), net_worth_entered]
            ),
            "burn_rate_30": now_burn.recent,
            "burn_rate_prior_60": now_burn.prior,
            "essentials": essentials if essentials_tagged else None,
            "essentials_tagged": essentials_tagged,
            "savings_rate": this.savings_rate,
            "runway": {
                **asdict(runway.default),
                "fund_chosen": runway.fund_chosen,
                "essentials_known": runway.essentials_known,
                "window_start": runway.window_start,
                "window_end": runway.window_end,
            },
            "income_this_month": this.income,
            "expenses_this_month": this.spending,
            "expenses_prev_month": expenses_prev,
            "debt_payments_this_month": this.debt_principal,
            "outflows_this_month": this.cost_of_living,
            "top_categories": top_cats,
            "means_months": await means_months(self, budget_id, today),
        }

    # ─── Net Worth History ────────────────────────────────────────────────────

    async def _balance_sheets(
        self, budget_id: uuid.UUID, as_of: list[date], today: date, since: date
    ) -> BalanceSheets:
        """The balance sheet (`balance_sheet`) at the end of each day in
        `as_of`, ascending — net worth's one rule — with what began being
        counted in each point's stretch (`tracking_start.place_entries`, the
        first stretch starting at `since`). The Overview card asks it for two
        days, the chart for every month end.

        Clamped to the reader's `today`: a month end still ahead is not net
        worth yet, and money that has not moved is not in it. On today, stated
        debts and asset values read their current figures; before it, each
        reads its step function (`StatedValue.at`) and contributes nothing
        before its first point. `today` is the caller's and never read here:
        this read the server's clock while the Overview card asked for the
        reader's day, so every evening west of UTC the card's "now" missed the
        clamp's, and its stated debts and asset values fell back to their step
        functions.
        """
        cutoffs = [min(day, today) for day in as_of]
        accounts = (
            await self.session.execute(
                select(
                    Account.id, Account.name, Account.account_type, Account.classification
                ).where(Account.budget_id == budget_id, LIVE_ACCOUNT)
            )
        ).all()
        balances = await self.accounts.balances_through(budget_id, cutoffs)
        stated = await stated_values(self.session, budget_id)
        sheets = [
            balance_sheet(
                accounts,
                balances,
                i,
                stated_total(stated, "stated_asset", cutoff, today),
                stated_total(stated, "manual_debt", cutoff, today),
            )
            for i, cutoff in enumerate(cutoffs)
        ]
        entries = await entries_by_point(self.session, budget_id, cutoffs, since, today, stated)
        return BalanceSheets(sheets, entries, stated)

    async def net_worth_history(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
        today: date | None = None,
    ) -> list[dict]:
        """Net worth at the end of each of the last `months` complete months,
        then today (`report_window`), each point carrying what entered it
        (`entered`, `entries`). An empty register needs no branch of its
        own: stated assets and unmanaged debts still stand on every point.

        Not clamped to the first transaction, as the flow reports are: a
        balance exists before the register does — a stated asset, a debt
        recorded by hand — and a month-end with nothing in it is a real zero,
        not an unrecorded month."""
        return (await self.net_worth(budget_id, months, today))["points"]

    async def net_worth(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
        today: date | None = None,
    ) -> dict:
        """The Net Worth report: its points (`net_worth_history`), the change
        over them both as drawn and like-for-like (`tracking_start.like_for_like`
        — less what began being counted after the first point), the stated
        values with their dates, and the balances that have not moved in
        `STALE_AFTER_DAYS`.

        The headline is the like-for-like change. A year in which accounts
        were linked and a house first valued read +$620k on the chart and was
        slightly down; the raw change is served beside it so the page can say
        how the two differ."""
        today = reader_today(today)
        grid = report_window(today, months).axis
        drawn = await self._balance_sheets(
            budget_id, [_month_end(m) for m in grid], today, since=grid[0]
        )
        arrived = [entered(bucket) for bucket in drawn.entries]
        values: list[Decimal] = [sheet["net_worth"] for sheet in drawn.sheets]
        points = [
            {"date": month, **sheet, "entered": total, "entries": [e.__dict__ for e in bucket]}
            for month, sheet, bucket, total in zip(
                grid, drawn.sheets, drawn.entries, arrived, strict=True
            )
        ]
        return {
            "points": points,
            "change": values[-1] - values[0],
            "like_for_like_change": like_for_like(values, arrived),
            "entered_total": sum(arrived[1:], Decimal("0")),
            "stated_values": [
                {"kind": s.kind, "id": s.id, "name": s.name, "value": s.current, "as_of": s.as_of}
                for s in drawn.stated
                if s.current > 0
            ],
            "stale_after_days": STALE_AFTER_DAYS,
            "stale_balances": await self._stale_balances(
                budget_id, points[-1], drawn.stated, today
            ),
        }

    async def _stale_balances(
        self, budget_id: uuid.UUID, now: dict, stated: list[StatedValue], today: date
    ) -> list[dict]:
        """Every figure in today's net worth that has not moved in
        `STALE_AFTER_DAYS`: an account holding a balance whose newest row is
        that old, and a stated value whose newest point is. Flat on the chart
        means unknown here, not unchanged, and the page says which lines."""
        held = {a["account_id"]: a for a in now["accounts"] if a["balance"] != 0}
        moved = await last_moved(self.session, [uuid.UUID(i) for i in held], today)
        stale = [
            {
                "kind": "account",
                "id": account_id,
                "name": account["account_name"],
                "last_changed": moved.get(uuid.UUID(account_id)),
            }
            for account_id, account in held.items()
            if is_stale(moved.get(uuid.UUID(account_id)), today)
        ]
        stale += [
            {"kind": s.kind, "id": s.id, "name": s.name, "last_changed": s.as_of}
            for s in stated
            if s.current > 0 and is_stale(s.as_of, today)
        ]
        return sorted(stale, key=lambda s: (s["last_changed"] or date.min, s["name"]))

    # ─── Account Composition ─────────────────────────────────────────────────

    async def account_composition(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
        today: date | None = None,
    ) -> dict:
        """Net worth's points by account type, plus two bands for what no
        account holds — stated asset values above zero, debts with no account
        below — so the stack sums to the Net line. It floated above the stack
        by the house's value, with a footnote saying so.

        `series` is every type a live account has, in the registry's order,
        whether or not the window holds a row of it: the chart colours a
        series by its place here, and a colour that moved when a range
        dropped a type named a different account type on each range."""
        history = await self.net_worth_history(budget_id, months, today)
        present = {
            a.account_type
            for a in (
                await self.session.execute(
                    select(Account.account_type).where(Account.budget_id == budget_id, LIVE_ACCOUNT)
                )
            ).all()
        } | {snap["account_type"] for point in history for snap in point["accounts"]}
        registry = [t.key for t in await AccountTypeRepository(self.session).get_all(budget_id)]
        series = [k for k in registry if k in present] + sorted(present - set(registry))
        points = []
        for point in history:
            by_type: dict[str, Decimal] = {t: Decimal("0") for t in series}
            for snap in point["accounts"]:
                by_type[snap["account_type"]] += snap["balance"]
            points.append(
                {
                    "date": point["date"],
                    "balances": by_type,
                    "stated_assets": point["asset_value_total"],
                    "manual_debts": -point["unmanaged_liability_total"],
                    # History already computed it; the chart re-deriving it
                    # from the visible series would disagree the moment a
                    # figure were in net worth and in no band.
                    "net_worth": point["net_worth"],
                    "asset_value_total": point["asset_value_total"],
                    "entered": point["entered"],
                    "entries": point["entries"],
                }
            )
        return {"points": points, "series": series}

    # ─── Burn Rate ────────────────────────────────────────────────────────────

    async def burn_rate(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
        today: date | None = None,
    ) -> list[dict]:
        """Per month: the trailing thirty days ending on the month's last day
        and the sixty days before them, per thirty days — `domain.burn_rate`,
        the rule the Overview's card reads. The last `months` complete months
        (`budget_window`), then the running month, whose point is the card's:
        both windows ending yesterday (`burn_as_of`).

        A rolling window deliberately does not tile the calendar — over a
        31-day month one day falls in no window, over a 28-day month one
        falls in two. That is what "rolling" means, and `rolling_30` says so;
        a per-calendar-month figure is what Spending Trends is for.
        """
        today = reader_today(today)
        window = await budget_window(self.session, budget_id, months, today)
        as_ofs = [burn_as_of(today) if window.is_running(m) else _month_end(m) for m in window.axis]
        burns = await self._burns(budget_id, as_ofs)
        return [
            {"date": month_start, "rolling_30": b.recent, "prior_60": b.prior}
            for month_start, b in zip(window.axis, burns, strict=True)
        ]

    async def _burns(self, budget_id: uuid.UUID, as_ofs: Sequence[date]) -> list[Burn]:
        """The burn as of each date, from one read of every day any of them
        looks back over — the one path the Overview's card and the Burn Rate
        chart share.

        CLASS_TOTAL_ROW, the rows Spent This Period and Essentials sum, with
        no sign filter: a refund to a spending category is a positive SPENDING
        row and lowers the burn, as it lowers them. The chart used to add
        `amount < 0` and CASH_FLOW_ROW. The first ignored refunds; the second
        is implied by the class — a row is outside cash flow only when it is
        an uncategorized transfer leg pointed at another on-budget account,
        and ACTIVITY_CLASS never calls that SPENDING (asserted in
        test_dashboard_matches_charts.py, not assumed).

        LEAF (inside CLASS_TOTAL_ROW), not PARENT_ROW: only leaves carry a
        category and so a class. A split parent classified as plain spending
        and dragged a savings-tagged leg in with it — burn read $300 for a
        split whose real spending was $100.
        """
        start = burn_windows(min(as_ofs)).prior_start
        end = max(as_ofs)
        q = (
            select(
                Transaction.date,
                ACTIVITY_CLASS.label("cls"),
                func.sum(Transaction.amount).label("amount"),
            )
            .where(
                Transaction.budget_id == budget_id,
                CLASS_TOTAL_ROW,
                Transaction.date >= start,
                Transaction.date <= end,
            )
            .group_by(Transaction.date, ACTIVITY_CLASS)
        )
        rows = (await self.session.execute(apply_class_joins(q))).all()
        days = [DayClassTotal(r.date, r.cls, Decimal(r.amount)) for r in rows]
        return [burn(days, as_of) for as_of in as_ofs]

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
        """Budget assignments over the window, netted per category
        (`domain.cash_flow.budgeted_diagram`). No payees.

        Assignments belong to the budget, not to accounts, so the account
        filter applies only to the transaction-derived income total.
        """
        months = month_starts(start_date, end_date)
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
                BUDGETED_ENVELOPE,
            )
        )
        rows = (await self.session.execute(q)).all()

        # Income is INCOME_ROW, as in spent mode: the mode changes what the
        # money went to, never what came in.
        income_q = select(func.sum(Transaction.amount)).where(
            Transaction.budget_id == budget_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            INCOME_ROW,
        )
        income_q, _ = account_scope(income_q, account_ids)
        income_q = apply_class_joins(income_q.select_from(Transaction))
        total_income = (await self.session.execute(income_q)).scalar() or Decimal("0")

        return budgeted_diagram(
            [
                AssignedRow(
                    category_id=str(r.category_id),
                    category_name=r.category_name or str(r.category_id),
                    group_id=str(r.group_id),
                    group_name=r.group_name or "Unknown",
                    assigned=Decimal(r.assigned),
                )
                for r in rows
            ],
            total_income,
        )

    async def _cash_flow_spent(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        account_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        """Actual transactions, net (`domain.cash_flow.spent_diagram`).

        **Spending is `_spending_rows`** — the one definition every spending
        report reads, so a category's node is the Breakdown's line for it, the
        Uncategorized node its Uncategorized line, and `total_spending` its
        total, over the same account scope. The rest of the diagram is the
        `HUB_CLASSES` rows — income, money moved to savings, debt principal —
        the classes Income vs Expenses nets beside spending; the two reads are
        disjoint by class. This read every flow row but openings and sorted
        them itself: an unfiled card credit reached the hub as "Other money
        in", and a fee on a selected brokerage was a node but not Spending.

        ONE row shape for every branch — income, outflow, drawn: LEAF.
        Income used to come from PARENT rows while expenses came from leaves,
        and a split straddles the two: +1,000 of pay and -300 of fees is a
        +700 parent, so income read 700 and the -300 was subtracted twice.
        LEAF loses nothing — a plain transaction is both a parent row and a
        leaf — and drops precisely the split parent, whose amount is its legs
        restated.

        Split by activity class, not by sign: a withdrawal FROM a brokerage
        (+500 into checking) is not income. Income is INCOME_ROW, which
        budgeted mode reads too.
        """
        found = await self._spending_rows(budget_id, start_date, end_date, account_ids=account_ids)
        q = (
            join_split_parent(
                select(
                    Transaction.amount,
                    # A split leg created in the app carries no payee: the parent
                    # names where the money came from, as in payee_analysis.
                    PAYEE_OF_RECORD.label("payee_id"),
                    Transaction.category_id,
                    Payee.name.label("payee_name"),
                    Category.name.label("category_name"),
                    CategoryGroup.id.label("group_id"),
                    CategoryGroup.name.label("group_name"),
                    ACTIVITY_CLASS.label("activity_class"),
                    INCOME_ROW.label("is_income"),
                )
            )
            .outerjoin(Payee, PAYEE_OF_RECORD == Payee.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .outerjoin(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                LEAF,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                CASH_FLOW_ROW,
                ACTIVITY_CLASS.in_(HUB_CLASSES),
            )
        )
        q, _ = account_scope(q, account_ids)
        rows = (await self.session.execute(apply_class_joins(q))).all()

        def opt(value) -> str | None:
            return str(value) if value else None

        return spent_diagram(
            [
                FlowRow(
                    amount=Decimal(r.amount),
                    activity_class=r.activity_class,
                    is_income=bool(r.is_income),
                    payee_id=opt(r.payee_id),
                    payee_name=r.payee_name,
                    category_id=opt(r.category_id),
                    category_name=r.category_name,
                    group_id=opt(r.group_id),
                    group_name=r.group_name,
                )
                for r in rows
            ]
            + [
                FlowRow(
                    amount=Decimal(r.amount),
                    activity_class=r.cls,
                    is_income=False,
                    payee_id=opt(r.payee_id),
                    payee_name=r.payee_name,
                    category_id=opt(r.id),
                    category_name=r.name,
                    group_id=opt(r.group_id),
                    group_name=r.group_name,
                )
                for r in found.counted
            ],
            found.classes,
        )

    # ─── Budget vs Actual ─────────────────────────────────────────────────────

    async def budget_vs_actual(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        category_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        """Each category's plan for the window against what it spent.

        The plan is the window's assignments plus money moved into the
        envelope less money moved out, and spent is net of refunds —
        `plan_ledger` reads both and `domain.plan` says why. A category with
        no activity at all (`PlanMonth.quiet`: nothing assigned, moved or
        spent) is not a row. One whose plan floors to nothing is: a mortgage
        paid by a principal transfer is on plan, not missing.

        The totals are the served rows summed, so the headline cannot say
        something the rows under it do not (`plan.total_variance`).
        """
        ledger = await plan_ledger(
            self.session, budget_id, start_date, end_date, category_ids=category_ids
        )
        zero = Decimal("0")
        categories: list[dict] = []
        outcomes = []
        totals = {
            "assigned": zero,
            "moved_in": zero,
            "moved_out": zero,
            "plan": zero,
            "spent": zero,
        }
        for cat in ledger.values():
            t = cat.total()
            outcome = plan_outcome(t.assigned, t.spent, moved_in=t.moved_in, moved_out=t.moved_out)
            if t.quiet:
                continue
            # `overspent` is served so the chart stops deciding it from the
            # raw assignment; `plan` so it never adds moved-in money itself.
            outcomes.append(outcome)
            categories.append(
                {
                    "category_id": str(cat.category_id),
                    "category_name": cat.name,
                    "category_group_name": cat.group,
                    "assigned": t.assigned,
                    "moved_in": t.moved_in,
                    "moved_out": t.moved_out,
                    "plan": outcome.plan,
                    "spent": t.spent,
                    "variance": outcome.variance,
                    "variance_pct": outcome.variance_pct,
                    "overspent": outcome.over,
                }
            )
            totals["assigned"] += t.assigned
            totals["moved_in"] += t.moved_in
            totals["moved_out"] += t.moved_out
            totals["plan"] += outcome.plan
            totals["spent"] += t.spent
        categories.sort(key=lambda c: (-c["spent"], c["category_name"]))
        return {
            "categories": categories,
            "total_assigned": totals["assigned"],
            "total_moved_in": totals["moved_in"],
            "total_moved_out": totals["moved_out"],
            "total_plan": totals["plan"],
            "total_spent": totals["spent"],
            "total_variance": total_variance(outcomes),
        }

    # ─── Cumulative Variance ──────────────────────────────────────────────────

    async def cumulative_variance(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
        today: date | None = None,
    ) -> list[dict]:
        """Each month's plan against its spending, and the running drift of
        the complete months (`budget_window`).

        A month's variance is its categories' verdicts summed — the column
        totals of Plan vs Reality's matrix — not `assigned - spent` over the
        whole budget. That raw difference read money moved out of one
        envelope and spent from another as an overrun (the second's plan came
        from the first's carryover, which a monthly plan cannot see), and it
        read a transfer from savings into an envelope as spending with no plan
        behind it. `planned - actual_spent` is `monthly_variance` by
        construction.

        The running month is served with its figures so far and NO cumulative
        figure: its whole assignment is in on the 1st while its spending
        arrives over thirty days, so adding it made the drift leap "under
        budget" at the start of every month and drift back by its end.
        """
        today = reader_today(today)
        window = await budget_window(self.session, budget_id, months, today)
        ledger = await plan_ledger(self.session, budget_id, window.start, today)
        zero = Decimal("0")
        results = []
        cumulative = zero
        for month in window.axis:
            assigned = moved_in = moved_out = planned = spent = variance = zero
            for cat in ledger.values():
                cell = cat.months.get(month)
                if cell is None:
                    continue
                outcome = plan_outcome(
                    cell.assigned, cell.spent, moved_in=cell.moved_in, moved_out=cell.moved_out
                )
                assigned += cell.assigned
                moved_in += cell.moved_in
                moved_out += cell.moved_out
                planned += outcome.plan
                spent += cell.spent
                variance += outcome.variance
            running = window.is_running(month)
            if not running:
                cumulative += variance
            results.append(
                {
                    "month": month,
                    "partial_month": running,
                    "budget_assigned": assigned,
                    "moved_in": moved_in,
                    "moved_out": moved_out,
                    "planned": planned,
                    "actual_spent": spent,
                    "monthly_variance": variance,
                    "cumulative_variance": None if running else cumulative,
                }
            )
        return results

    # ─── Plan vs Reality ─────────────────────────────────────────────────────

    async def plan_vs_reality(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
        today: date | None = None,
    ) -> dict:
        """Each category's plan against its spending, per month.

        Deliberately ignores carryover: this report measures monthly plan
        discipline (did the month's spending fit the month's plan?), not
        envelope health — a category living off January's surplus still
        reads as over-plan in February if nothing was assigned or moved in.

        The plan and spent are `plan_ledger`'s, the universe Budget vs Actual
        and Cumulative Variance count. A month counts as "over" when
        `plan_outcome` says so — past the plan by a dollar and 1% of it —
        and a category is chronic by `plan.is_chronic`, over the window's
        last `CHRONIC_WINDOW` complete months. The Guide's chronic-overspend
        check reads the served flag, so saving, a transfer into an envelope, a
        few cents of rounding or a sinking fund paying its bill can never be
        reported as a bad habit.

        The window is `budget_window`'s: `months` complete months, and the
        running month drawn beside them as `running_month`. Every verdict and
        total — a cell's `over`, chronic, months over, the headline sums —
        reads the complete months alone: a month whose assignment is all in
        and whose spending is a week old is neither over nor under yet.

        A category with no active month — nothing assigned, moved or spent
        anywhere in the window, the running month included (`PlanMonth.quiet`)
        — is not a row.
        """
        today = reader_today(today)
        window = await budget_window(self.session, budget_id, months, today)
        months_list = window.axis
        ledger = await plan_ledger(self.session, budget_id, window.start, today)

        zero = Decimal("0")
        recent = set(window.complete[-CHRONIC_WINDOW:])
        categories: list[ChronicCategory] = []
        total_assigned = total_moved_in = total_moved_out = total_spent = zero
        chronic_count = 0
        for cat in ledger.values():
            monthly: list[ChronicMonth] = []
            months_over = 0
            months_active = 0
            recent_over = 0
            over_total = zero
            shown = False
            t = PlanMonth()
            for m in months_list:
                cell = cat.months.get(m) or PlanMonth()
                # One verdict for the chronic count, the cell's tint AND its
                # variance: a drained envelope was once coloured as overspent
                # while the chronic flag beside it disagreed.
                outcome = plan_outcome(
                    cell.assigned, cell.spent, moved_in=cell.moved_in, moved_out=cell.moved_out
                )
                active = not cell.quiet
                running = window.is_running(m)
                shown = shown or active
                if not running:
                    t.assigned += cell.assigned
                    t.moved_in += cell.moved_in
                    t.moved_out += cell.moved_out
                    t.spent += cell.spent
                    if active:
                        months_active += 1
                        if outcome.over:
                            months_over += 1
                            over_total += -outcome.variance
                            if m in recent:
                                recent_over += 1
                monthly.append(
                    {
                        "month": m,
                        "assigned": cell.assigned,
                        "moved_in": cell.moved_in,
                        "moved_out": cell.moved_out,
                        "plan": outcome.plan,
                        "spent": cell.spent,
                        "variance": outcome.variance,
                        "over": outcome.over and not running,
                        "active": active,
                    }
                )
            if not shown:
                continue
            chronic = is_chronic(recent_over, sinking_fund=cat.sinking_fund)
            if chronic:
                chronic_count += 1
            avg_overspend = quantize_cents(over_total / months_over) if months_over else zero
            categories.append(
                {
                    "category_id": str(cat.category_id),
                    "category_name": cat.name,
                    "category_group_name": cat.group,
                    "monthly": monthly,
                    "months_over": months_over,
                    "months_active": months_active,
                    "total_assigned": t.assigned,
                    "total_moved_in": t.moved_in,
                    "total_moved_out": t.moved_out,
                    "total_spent": t.spent,
                    "avg_overspend": avg_overspend,
                    "chronic": chronic,
                    "sinking_fund": cat.sinking_fund,
                }
            )
            total_assigned += t.assigned
            total_moved_in += t.moved_in
            total_moved_out += t.moved_out
            total_spent += t.spent

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
            # Which column is still being written: the page marks it "so far"
            # rather than guessing.
            "running_month": window.running,
            "categories": categories,
            "total_assigned": total_assigned,
            "total_moved_in": total_moved_in,
            "total_moved_out": total_moved_out,
            "total_spent": total_spent,
            "chronic_count": chronic_count,
        }

    # ─── Category Volatility ─────────────────────────────────────────────────

    async def category_volatility(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
        amortize: bool = False,
        today: date | None = None,
    ) -> dict:
        """Per-category spread over complete months, and the window it read.

        COMPLETE months only, and bounded at both ends. There was no upper
        bound at all, so a future-dated row landed in a month bucket outside
        the window it is labelled with. And the current month was counted as
        though complete, which invents a historical minimum on the 2nd of every
        month: a category that always spends 400 read a spread of 12-400 purely
        because today is early.

        The window is SERVED because the drill-down must list the rows these
        figures came from. The chart computed it for itself, under a comment
        saying it was "the same window the backend aggregates over", and it
        stopped being the same the day this one moved: the panel added the
        partial current month the statistics leave out and dropped the oldest.
        """
        start, end = await history_window(self.session, budget_id, months, reader_today(today))
        # Spent as the plan family counts it, net of refunds: this was
        # `abs(amount)` of every outflow of every class, so a transfer to a
        # brokerage swung a category and a refund made a month bigger.
        ledger = await plan_ledger(self.session, budget_id, start, end, assignments=False)
        return {
            "categories": volatility_stats(
                ledger_rows(ledger), month_starts(start, end), amortize=amortize
            ),
            "window_start": start,
            "window_end": end,
        }

    @staticmethod
    def _spending_query(
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        category_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
        include_classes: Sequence[ActivityClass] | None = None,
        payee_ids: list[uuid.UUID] | None = None,
    ) -> tuple[Select, set[str]]:
        """Every posted spending row in the window — `SPENDING_ROW`, net of
        refunds, uncategorized included — with its category, group, payee of
        record, purchase and activity class, and the classes of those rows to
        count. **The one definition of spending** for every report of that
        shape: Spending Trends, the Breakdown, Pareto, the Treemap,
        Seasonality, Payees and Day Patterns all read `_spending_rows`, so a
        bar on one and a cell on another cannot total differently.

        They did. The Breakdown and Trends inner-joined Category and so
        dropped uncategorized spending; Payees and Day Patterns kept it;
        Seasonality counted every class, savings and debt payments included;
        and all of them summed outflows alone while Income vs Expenses netted
        refunds — four answers to "what did I spend" over one window.

        Category and group are OUTER joins: an uncategorized row comes back
        with a None id and is its own Uncategorized line. `txn_id` is the
        purchase a row belongs to — a split leg's parent — so a count of
        purchases does not count legs.

        The class set comes back with the query because it widens on the
        account scope applied here: derived beside it, the two cannot
        disagree about whether the user picked accounts."""
        q = (
            join_split_parent(
                select(
                    Transaction.amount,
                    Transaction.date,
                    Category.id,
                    Category.name,
                    CategoryGroup.id.label("group_id"),
                    CategoryGroup.name.label("group_name"),
                    PAYEE_OF_RECORD.label("payee_id"),
                    Payee.name.label("payee_name"),
                    func.coalesce(Transaction.parent_transaction_id, Transaction.id).label(
                        "txn_id"
                    ),
                    ACTIVITY_CLASS.label("cls"),
                )
            )
            .outerjoin(Category, Transaction.category_id == Category.id)
            .outerjoin(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .outerjoin(Payee, PAYEE_OF_RECORD == Payee.id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                SPENDING_ROW,
            )
        )
        q = scoped(q, Transaction.category_id, category_ids)
        # PAYEE_OF_RECORD rather than the raw column, so a split's legs are
        # in their shop's scope; `scoped` keeps [] apart from None.
        q = scoped(q, PAYEE_OF_RECORD, payee_ids)
        q, explicit = account_scope(q, account_ids)
        return apply_class_joins(q), counted_classes(include_classes, scoped_accounts=explicit)

    async def _spending_rows(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        category_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
        include_classes: Sequence[ActivityClass] | None = None,
        payee_ids: list[uuid.UUID] | None = None,
    ) -> SpendingRows:
        """`_spending_query`'s rows, partitioned by the class set in one scan.

        Partitioned here rather than filtered in the WHERE: the complement is
        what `class_excluded_note` explains, and re-querying for it paid the
        per-row subqueries ACTIVITY_CLASS compiles to a second time.
        """
        q, included = self._spending_query(
            budget_id, start_date, end_date, category_ids, account_ids, include_classes, payee_ids
        )
        rows = (await self.session.execute(q)).all()
        return SpendingRows(
            counted=[r for r in rows if r.cls in included],
            excluded=[r for r in rows if r.cls not in included],
            classes=sorted(included),
        )

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
        """Spending per category with its group: the Breakdown, Pareto and the
        Treemap. Net of refunds, with an Uncategorized line (id None).

        With `view_id`, the groups come from that view's arrangement instead of
        the budget's own — the same money read a different way, which is the
        point of a view. Categories the view hides drop out; ones it has not
        placed collect under "Unassigned", or drop out too if the view says so.
        Uncategorized spending is no category a view can place or hide, so it
        stays, under its own group.

        The third element is a notes dict explaining what the report left out,
        so the chart can say so instead of silently shrinking:

        - ``view_hidden``: ``{"categories": n, "total": Decimal}`` or None —
          spending dropped because the active view hides those categories.
        - ``class_excluded``: per-class list or None — activity in categories
          the user is looking at (their selection, or the view's visible set)
          that is savings / debt payment rather than spending. A car payment
          that "vanishes" from a spending report is this, and without the note
          the exclusion is indistinguishable from data loss.
        - ``counted_classes``: the classes the figures count, served so every
          drill-down asks for exactly them.
        """
        found = await self._spending_rows(
            budget_id, start_date, end_date, category_ids, account_ids, include_classes
        )

        # `_view_arrangement` returns None for a view that does not exist or
        # belongs to another budget. Falling back to the budget's own groups
        # there is right — an empty report would be worse — but it must be
        # visible: reportStore persists viewId outside any budget scope, so
        # deleting a view in another tab, or switching budgets, otherwise left
        # the page charting one arrangement while still requesting another.
        regroup = await self._view_arrangement(budget_id, view_id) if view_id else None
        view_unavailable = view_id is not None and regroup is None

        def _shown(r) -> bool:
            return regroup is None or r.id is None or regroup(r.id) is not None

        # "This view hides $X of spending" means spending, not every class —
        # a debt payment the view also hides belongs to neither note.
        dropped = [r for r in found.counted if not _shown(r)]
        dropped_by_view = (
            {"categories": len({r.id for r in dropped}), "total": spent(r.amount for r in dropped)}
            if dropped
            else None
        )

        # A category the view deliberately hides is the view's story, so its
        # excluded activity is left out of this note too.
        notes = {
            "view_hidden": dropped_by_view,
            "class_excluded": class_excluded_note(
                [r for r in found.excluded if _shown(r)],
                scoped=bool(category_ids) or regroup is not None,
            ),
            "view_unavailable": view_unavailable,
            "counted_classes": found.classes,
        }

        def _group_of(r) -> tuple[str | None, str]:
            if r.id is None:
                return None, UNCATEGORIZED
            if regroup is None:
                return str(r.group_id), r.group_name
            placed = regroup(r.id)
            assert placed is not None  # filtered by _shown
            return placed

        by_cat: dict[uuid.UUID | None, dict] = {}
        for r in found.counted:
            if not _shown(r):
                continue
            parent_id, parent_name = _group_of(r)
            item = by_cat.setdefault(
                r.id,
                {
                    "id": r.id,
                    "name": r.name or UNCATEGORIZED,
                    "parent_id": parent_id,
                    "parent_name": parent_name,
                    "amounts": [],
                },
            )
            item["amounts"].append(r.amount)
        grand_total = spent(r.amount for r in found.counted if _shown(r))
        items = []
        for item in by_cat.values():
            total = spent(item["amounts"])
            items.append(
                {
                    **{k: item[k] for k in ("id", "name", "parent_id", "parent_name")},
                    "total": quantize_cents(total),
                    "count": len(item["amounts"]),
                    "pct": float(total / grand_total * 100) if grand_total > 0 else 0.0,
                }
            )
        items.sort(key=lambda i: i["total"], reverse=True)
        return items, quantize_cents(grand_total), notes

    # ─── Seasonality ─────────────────────────────────────────────────────────

    async def seasonality(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
        today: date | None = None,
        include_classes: Sequence[ActivityClass] | None = None,
    ) -> dict:
        """Net spending per category per complete month: the heatmap.

        `_spending_rows`, so the same spending Trends and the Breakdown read —
        it counted every class, so a brokerage transfer or a mortgage payment
        coloured the grid as spending, and the Include-savings choice the other
        spending reports offer did not exist here.

        COMPLETE months only, bounded at both ends, and never before the
        budget's history (`complete_month_window`). With no upper bound a
        future-dated row set the heatmap's colour scale for every real cell.
        The axis is built from the SAME bounds: it was once built through the
        current month while the query stopped at the end of the last one, so
        the newest column was always blank.
        """
        start, end = await history_window(self.session, budget_id, months, reader_today(today))
        found = await self._spending_rows(budget_id, start, end, include_classes=include_classes)
        return {
            **category_month_grid(found.counted, top=SEASONALITY_TOP),
            "months": month_starts(start, end),
            "counted_classes": found.classes,
        }

    # ─── Payee Analysis ───────────────────────────────────────────────────────

    async def payee_analysis(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int = 25,
        payee_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        """The `limit` largest payees, the total over EVERY payee, and the
        figures `report_stats.payee_rollup` states — from `_spending_rows`, so
        a payee's total is the same spending the Breakdown shows, net of
        refunds, split legs under their shop.

        A row with no payee of record ranks nowhere: there is no shop to
        name. It is the one gap between this total and the Breakdown's over
        the same scope, pinned by
        `test_one_spending_definition.py::TestEveryReportTotalsTheSameSpending`.
        """
        found = await self._spending_rows(
            budget_id, start_date, end_date, account_ids=account_ids, payee_ids=payee_ids
        )
        return {
            **payee_rollup(
                [r for r in found.counted if r.payee_id is not None],
                months_spanned(start_date, end_date),
                limit,
            ),
            "counted_classes": found.classes,
        }

    # ─── Day Patterns ─────────────────────────────────────────────────────────

    async def day_patterns(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        category_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
        today: date | None = None,
    ) -> dict:
        """Spending by day of the week, and what the class filter left out.

        Each weekday's net total, and its average per CALENDAR day
        (`report_stats.weekday_rollup`) over the days the window really holds:
        from the later of `start_date` and the budget's first transaction, to
        the earlier of `end_date` and today. A day before the history began
        is not a quiet day, and neither is one that has not happened yet.

        Dates are the bank's posting dates — a Saturday purchase that posts on
        Monday is Monday's — which the page says.

        ``class_excluded`` is the same note Pareto and the treemap carry.
        Without it, filtering to a category whose activity is all debt
        principal or savings drew the generic "no spending" empty state,
        which reads as missing data rather than as a definition.
        """
        found = await self._spending_rows(
            budget_id, start_date, end_date, category_ids, account_ids
        )
        earliest = await self.txns.earliest_date(budget_id)
        first = max(start_date, earliest) if earliest else start_date
        last = min(end_date, reader_today(today))
        return {
            "days": weekday_rollup(found.counted, weekday_counts(first, last)),
            "window_start": first,
            "window_end": last,
            "class_excluded": class_excluded_note(found.excluded, scoped=bool(category_ids)),
            # Served so the drill-down asks for the same classes the bar
            # counted. Without it the panel opened from a Tuesday bar totalled
            # more than the bar did — the chart filters to spending and the
            # panel filtered to nothing.
            "counted_classes": found.classes,
        }

    # ─── Large Transactions (Timeline) ────────────────────────────────────────

    async def large_transactions(
        self,
        budget_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int = 50,
        category_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
        outflows_only: bool = False,
    ) -> list[dict]:
        """The `limit` largest transactions by size, every class drawn.

        `outflows_only` is the page's default: "largest transactions" is read
        as "where did the big money go", and a month's paycheques otherwise
        took most of the slots. The All view keeps inflows one click away.
        """
        q = (
            select(
                Transaction.id,
                Transaction.date,
                Transaction.amount,
                Transaction.memo,
                Transaction.is_split,
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
                # Every class is drawn, but an opening is not a transaction
                # anybody made.
                NOT_OPENING_BALANCE,
            )
        )
        # `in_category_scope`, not `scoped`: a split parent carries no
        # category, so a plain `category_id IN (...)` dropped every split
        # transaction the household had the moment a category, tag or saved
        # filter was applied — the report went quieter the more precisely you
        # asked. A parent is in scope when any of its legs is.
        if category_ids is not None:
            q = q.where(in_category_scope(category_ids))
        if outflows_only:
            q = q.where(Transaction.amount < 0)
        q, _ = account_scope(q, account_ids)
        # Ranked by SIZE, not by signed amount.
        #
        # `order_by(amount)` puts the most negative first, which is right for
        # outflows and wrong the moment an inflow makes the cut: a 4,000 refund
        # sorted to the very END, so a "largest transactions" list could omit
        # the largest transaction in the window while including a 20 coffee.
        # The client reads `transactions[0]` as the largest and scales every
        # dot against it, so the whole chart's proportions came from whichever
        # row happened to sort first.
        q = q.order_by(func.abs(Transaction.amount).desc()).limit(limit)
        q = apply_class_joins(q)
        rows = (await self.session.execute(q)).all()

        # A split parent's own class is meaningless and was being drawn anyway.
        #
        # The classifier is defined on LEAF rows — a parent carries no category
        # — so a parent fell through every rule to the SPENDING default. An
        # all-savings split, a transfer to a brokerage itemised into three
        # legs, was drawn as a red "Spending" dot. Its class comes from its
        # legs: one distinct class among them is the parent's class, and
        # anything else is honestly mixed.
        # One query for the parents on this page, at most `limit` of them.
        split_ids = [r.id for r in rows if r.is_split]
        legs = (await self.session.execute(split_leg_classes(split_ids))).all() if split_ids else []
        return timeline_rows(rows, rolled_up_classes(legs))

    # ─── Subscriptions Report ─────────────────────────────────────────────────

    async def _class_frame(self, budget_id: uuid.UUID, start: date, end: date) -> pl.DataFrame:
        """(date, amount, class) for on-budget leaf rows, for window slicing.

        Same rows and same classification as `_monthly_class_totals`; that one
        groups by month in SQL, this one hands back the rows so a caller can
        cut arbitrary windows (30 days, previous period) without a query each.
        """
        rows = (
            await self.session.execute(
                apply_class_joins(
                    select(
                        Transaction.date,
                        Transaction.amount,
                        ACTIVITY_CLASS.label("cls"),
                    ).where(
                        Transaction.budget_id == budget_id,
                        CLASS_TOTAL_ROW,
                        Transaction.date >= start,
                        Transaction.date <= end,
                    )
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
                CLASS_TOTAL_ROW,
                Transaction.date >= start,
                Transaction.date <= end,
            )
            .group_by(month_col, ACTIVITY_CLASS)
        )
        q = apply_class_joins(q)
        rows = (await self.session.execute(q)).all()

        by_month: dict[date, dict[str, Decimal]] = {}
        for row in rows:
            key = row.month.date() if hasattr(row.month, "date") else row.month
            by_month.setdefault(key, {})[row.cls] = Decimal(str(row.total))
        return by_month

    async def _class_series(
        self, budget_id: uuid.UUID, months: int, today: date
    ) -> tuple[ReportWindow, list[tuple[date, dict[str, Decimal]]]]:
        """The window (`budget_window`) and each of its months, oldest first,
        with class totals — the running month last.

        `income_vs_expense` and `savings_rate` each walked
        `_monthly_class_totals` with their own copy of this reversed range, so
        a change to the window — how a partial current month counts, say —
        landed in one report and not the other. Months with no activity are
        present with an empty bucket: a gap in the series is a gap in the
        chart, not a shorter chart.

        The rows run from the window's start through `today`, which the
        caller reads once — a second clock read could name a day the rows
        were not read through.
        """
        window = await budget_window(self.session, budget_id, months, today)
        by_month = await self._monthly_class_totals(budget_id, window.start, today)
        return window, [(month, by_month.get(month, {})) for month in window.axis]

    async def _view_arrangement(self, budget_id: uuid.UUID, view_id: uuid.UUID):
        """The arranger for one view (`domain/view_arrangement.py`, the rule
        the budget page's `groupByView` runs too), or None if there is no such
        view in this budget."""
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
        return arrange_by_view(
            hide_unassigned=view.hide_unassigned, group_names=group_names, placements=placements
        )

    # ─── Savings Rate ─────────────────────────────────────────────────────────

    async def savings_rate(
        self, budget_id: uuid.UUID, months: int = 12, today: date | None = None
    ) -> dict:
        """How much of what came in was kept, month by month.

        Asked for directly: "i would like there to be categories
        that are classified as savings and be able to track my savings rate as
        compared to income and/or all spending".

        Two rates, because paying down a mortgage and funding a brokerage both
        build net worth but people think about them differently:

            savings_rate           = (moved + held) / income
            savings_rate_with_debt = (moved + held + debt_principal) / income

        `savings` is saved: money moved into savings plus what kept-here
        Savings envelopes came to hold (`domain.savings`), served with both
        parts as `savings_moved` and `savings_held`.

        Scoped to on-budget accounts, which is what makes the number honest:
        growth inside a tracked account classifies as `investment_return` and
        is left out. A savings rate that counted market gains as saving would
        rise in a bull market without the household doing anything.

        A month with no income yields a rate of None rather than 0 — "no income
        recorded" and "saved nothing" are different facts, and a chart should
        show a gap rather than a floor.
        """

        today = reader_today(today)
        window, class_series = await self._class_series(budget_id, months, today)
        axis = [month for month, _ in class_series]
        held = await held_by_month(self.session, budget_id, axis, today)
        series: list[dict] = []
        totals: dict[str, Decimal] = {}
        held_total = Decimal("0")
        for (month, buckets), month_held in zip(class_series, held, strict=True):
            running = window.is_running(month)
            month_figures = _rate_figures(figures(buckets, month_held))
            series.append({"month": month, "partial_month": running, **month_figures})
            # The headline is the complete months alone (`ReportWindow`): a
            # few days of a new month — the bills in, the pay not yet — turned
            # a +0.8% year into -1.8%.
            if running:
                continue
            held_total += month_held
            for cls, amount in buckets.items():
                totals[cls] = totals.get(cls, Decimal("0")) + amount

        return {
            "months": series,
            # The window the summary covers, served rather than rebuilt from
            # `months` on the client: the savings-rate dialog asks for the
            # contributors of exactly these rows. Complete months only, so it
            # ends on the last day of last month; empty (start after end) on a
            # budget whose history starts this month.
            "start_date": window.start,
            "end_date": window.complete_end,
            "summary": _rate_figures(figures(totals, held_total)),
        }

    # ─── Anomaly Detection ────────────────────────────────────────────────────

    async def anomalies_report(
        self,
        budget_id: uuid.UUID,
        months: int = 12,
        threshold: float = 2.0,
        today: date | None = None,
    ) -> dict:
        """Detect category-months with spending outside baseline z-score.

        Complete months make every baseline, and the month in progress is
        scored against them but flagged only when it is HIGH — the rule, and
        why it diverges, live at `report_stats.anomaly_scan`. The window
        therefore runs from the complete-month start through TODAY, not
        through last month's end.
        """
        today = reader_today(today)
        start_date, _ = await history_window(self.session, budget_id, months, today)
        ledger = await plan_ledger(self.session, budget_id, start_date, today, assignments=False)
        # A sinking fund is not tested: months of nothing and then the bill it
        # saved for is the plan working, and flagged as a spike it was the
        # most disciplined envelope in the budget reading as the least.
        tested = {cid: cat for cid, cat in ledger.items() if not cat.sinking_fund}
        skipped = sum(
            1
            for cat in ledger.values()
            if cat.sinking_fund and any(c.spent != 0 for c in cat.months.values())
        )
        scan = anomaly_scan(
            [
                (str(r.category_id), r.category_name, r.group_name, r.date, -r.amount)
                for r in ledger_rows(tested)
            ],
            months=month_starts(start_date, today),
            today=today,
            threshold=threshold,
        )
        return {
            "anomalies": scan.anomalies,
            "categories_seen": scan.categories,
            "categories_tested": scan.tested,
            "sinking_funds_skipped": skipped,
        }

    # ─── Payday Effect ─────────────────────────────────────────────────────────

    async def payday_effect(
        self,
        budget_id: uuid.UUID,
        window: int = 14,
        months: int = 12,
        today: date | None = None,
    ) -> dict:
        """Median discretionary spending on each of the N days after a payday,
        against the median day of the whole window.

        The window is the last `months` complete months PLUS the running
        month's days so far — a deliberate difference from the per-month
        averages, which leave the running month out. Every figure here is per
        DAY, over days that happened, so a partial month cannot drag it down;
        dropping it would only hide the newest paydays. It is served, so the
        page states the dates it read instead of "the last 12 months".

        **Discretionary spending only** (`DISCRETIONARY_ROW`), net of
        refunds. Rent, the mortgage and the utilities land on their own dates
        whatever the household does after being paid, so counting them made
        the report a picture of the billing calendar: a mortgage due two days
        after payday read as a splurge on day +2 every month. Subscriptions
        stay out for the same reason, tagged or not.

        **Medians, not means.** One large purchase three days after one of
        twenty-six paydays set day +3's mean above every other bar; the median
        is what a typical payday looked like. The baseline is the median day
        across the WHOLE window, paydays included, with its day count served:
        it once averaged only the days outside every payday window, which is
        no days at all for biweekly pay at a 14-day window, and a baseline
        that exists only for some pay schedules is not a baseline.
        """
        end_date = reader_today(today)
        start_date, _ = await history_window(self.session, budget_id, months, end_date)
        # From the first transaction, not the first of its month: every day
        # is a sample of the baseline here, and a day before the register
        # began is not a day with nothing spent. Zero-filling them told a
        # household on a ninety-day first sync, spending a flat 50 a day, that
        # a typical day cost nothing.
        earliest = await self.txns.earliest_date(budget_id)
        if earliest is not None:
            start_date = max(start_date, earliest)

        # CASH_FLOW_ROW keeps transfers out: a transfer into checking is not
        # a payday. The class keeps out what CASH_FLOW_ROW lets through — a
        # transfer IN from a savings account passed straight through and was
        # counted as a payday.
        #
        # Subscriptions are read from the CATEGORY: this asked
        # `get_payee_ids_by_system_keys` until migration b8e5d1c73a49 deleted
        # every payee-subscription row, and so excluded nothing at all.
        q = (
            select(
                Transaction.date,
                Transaction.amount,
                category_tagged("subscription").label("is_subscription"),
                DISCRETIONARY_ROW.label("discretionary"),
                ACTIVITY_CLASS.label("cls"),
                ON_CARD_ACCOUNT.label("on_card"),
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
        rows = (await self.session.execute(apply_class_joins(q))).all()

        # A payday is an INCOME-class inflow of at least PAYDAY_FLOOR into
        # cash. Never onto a card: a card payment whose cash leg was never
        # paired used to class INCOME, so every month the bill was paid read
        # as a second payday. The classifier no longer calls an unfiled card
        # credit income (`activity_class`, rule 10); this still keeps out one
        # someone filed as income — a rebate is not a payday. And not a
        # quantile: the P75 of every inflow let a relative threshold decide
        # which paydays existed, and a quartile of a varying wage discards
        # three quarters of them.
        paydays = sorted(
            {
                r.date
                for r in rows
                if r.cls == ActivityClass.INCOME.value
                and not r.on_card
                and r.amount >= PAYDAY_FLOOR
            }
        )

        by_day: dict[date, list[Decimal]] = {}
        for r in rows:
            if r.discretionary and not r.is_subscription:
                by_day.setdefault(r.date, []).append(r.amount)

        def day_spend(d: date) -> Decimal:
            return spent(by_day.get(d, ()))

        # A payday with nothing spent on its day+3 is a ZERO for that offset,
        # not an absent sample: dividing by "paydays that happened to have
        # spending" read one 300 purchase after one of six paydays as a 300
        # typical day. Days past `end_date` are skipped rather than
        # zero-filled — the newest payday's window may not have finished.
        per_offset: list[list[Decimal]] = [[] for _ in range(window)]
        for payday in paydays:
            for offset in range(window):
                d = payday + timedelta(days=offset)
                if d <= end_date:
                    per_offset[offset].append(day_spend(d))

        every_day = [
            day_spend(start_date + timedelta(days=i))
            for i in range((end_date - start_date).days + 1)
        ]
        return {
            "days": [
                {
                    "offset": offset,
                    "median_spend": quantize_cents(median(vals)) if vals else Decimal("0"),
                    "paydays": len(vals),
                }
                for offset, vals in enumerate(per_offset)
            ],
            "baseline_daily": quantize_cents(median(every_day)) if paydays else None,
            "baseline_days": len(every_day),
            "event_count": len(paydays),
            # Served so the panel can state the rule it applied.
            "payday_floor": PAYDAY_FLOOR,
            "window_start": start_date,
            "window_end": end_date,
        }

    # ─── Cash Projection ─────────────────────────────────────────────────────────

    async def cash_projection(
        self,
        budget_id: uuid.UUID,
        horizon_days: int = 90,
        today: date | None = None,
    ) -> dict:
        """Project future cash balances with uncertainty bands — the inputs
        gathered here, the simulation in `domain.cash_projection`.

        `today` is the reader's (`api/v1/params.ReaderToday`). The container's
        clock is UTC, so of an evening in the Americas it is already tomorrow:
        the path started a day late, and the history ended on a day the reader
        had not finished.
        """
        from igab.db.models import ScheduledTransaction

        today = reader_today(today)
        end_date = today + timedelta(days=horizon_days)

        # 1. Current balance: the budget's CASH (`sum_on_budget_balance` —
        # CASH_ACCOUNT, bounded to today). The old inline sum took every
        # on-budget account, which in this credit model includes cards, so
        # "Current Balance" read low by the whole card balance — cash minus
        # card debt, a figure with no name. Card spending and payments enter
        # the projection only through the cash they move (see the flow
        # queries below, which scope the same way).
        start_balance = await self.accounts.sum_on_budget_balance(budget_id, today)

        # 2. Scheduled transactions. The projection covers on-budget cash, so
        # schedules pointed at off-budget or closed accounts don't belong in
        # it. Every live schedule is read, not only those due inside the
        # horizon: a yearly bill next due after the horizon still tells the
        # subscription arm below not to infer its own copy of that bill.
        # The whole row: start_date and second_day_of_month are what let
        # next_occurrence re-anchor a monthly schedule and step a twice-monthly
        # one at all, and category and account identify the bill when there is
        # no payee — which IGAB's own schedule editor never sets.
        sched_q = (
            select(ScheduledTransaction, Payee.name.label("payee_name"))
            .join(Account, Account.id == ScheduledTransaction.account_id)
            .outerjoin(Payee, Payee.id == ScheduledTransaction.payee_id)
            .where(
                ScheduledTransaction.budget_id == budget_id,
                ScheduledTransaction.is_deleted == False,  # noqa: E712
                Account.is_closed == False,  # noqa: E712
                # Cash accounts only, matching the balance being projected.
                # A schedule pointed at a card does not move cash on its
                # date; the card payment (a cash-side transfer) is what does.
                CASH_ACCOUNT,
            )
        )
        sched_rows = (await self.session.execute(sched_q)).all()

        # Expand scheduled transactions into individual events.
        #
        # Stepping is `domain.schedule.next_occurrence`, the one home for it.
        # This method had a fourth copy with no `twice_monthly` branch: it
        # returned None, the loop read None as "schedule finished", and a
        # twice-monthly schedule contributed ONE occurrence to a 90-day
        # projection — including the demo budget's twice-monthly salary.
        #
        # Everything a schedule has due by today is one charge on today — see
        # `projected_occurrences`. Each schedule also yields the register rows
        # it stands in for (`reapplied_by_schedule`): those that booked an
        # event leave the sampled history, and every live one keeps the
        # subscription arm from inferring the same bill a second time.
        scheduled_events: list[tuple[date, str, Decimal]] = []
        projected_schedules: list[ColumnElement[bool]] = []
        live_schedules: list[ColumnElement[bool]] = []
        for sched, payee_name in sched_rows:
            amount = Decimal(str(sched.amount))
            dates, runs_on = projected_occurrences(sched, today=today, horizon_end=end_date)
            scheduled_events.extend((d, payee_name or "Scheduled", amount) for d in dates)
            covers = reapplied_by_schedule(sched)
            if dates:
                projected_schedules.append(covers)
            if dates or runs_on:
                live_schedules.append(covers)

        # 3. Recurring charges in categories tagged Subscription, by payee.
        #
        # Categories, not payees. This read `get_payee_ids_by_system_keys` —
        # and migration b8e5d1c73a49 deleted every payee-subscription row and
        # made the routes refuse new ones, so the set has been empty since
        # 2026-09-06 and this projection has quietly contributed nothing. The
        # Subscriptions report reads categories and groups the charges by
        # payee within them; this now asks the same question the same way.
        subscription_events: list[tuple[date, str, Decimal]] = []
        subscription_payee_ids: set[uuid.UUID] = set()
        # Last charge date and typical amount per payee inside those
        # categories — leaving out charges a live schedule already stands in
        # for. Both arms used to book those, so a subscription entered as a
        # schedule was charged to the projection twice; and the old check
        # matched on the schedule's payee, which a schedule made in IGAB's
        # editor never has.
        sub_q = (
            join_split_parent(
                select(
                    # By payee of record, as the Subscriptions report groups:
                    # a split charge's legs carry the service on the parent.
                    PAYEE_OF_RECORD.label("payee_id"),
                    Payee.name.label("payee_name"),
                    func.max(Transaction.date).label("last_date"),
                    func.min(Transaction.date).label("first_date"),
                    func.count(Transaction.id).label("charge_count"),
                    func.avg(Transaction.amount).label("avg_amount"),
                )
            )
            .join(Payee, Payee.id == PAYEE_OF_RECORD)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                POSTED,
                LEAF,
                SUBSCRIPTION_CHARGE,
                Account.is_closed == False,  # noqa: E712
                # Cash accounts only: a subscription charged to a card
                # consumes cash at payment time, not charge time.
                CASH_ACCOUNT,
                none_of(*live_schedules),
            )
            .group_by(PAYEE_OF_RECORD, Payee.name)
        )
        sub_rows = (await self.session.execute(sub_q)).all()

        for row in sub_rows:
            last_date: date = row.last_date
            avg_amount = Decimal(str(row.avg_amount))
            payee_name = row.payee_name or "Subscription"

            # Cadence and the missed-two-cycles rule both live in
            # domain.schedule, beside the recurrence stepping.
            occurrences = subscription_occurrences(
                row.first_date, last_date, row.charge_count, today, end_date
            )
            if not occurrences:
                continue
            if row.payee_id is not None:
                subscription_payee_ids.add(row.payee_id)
            subscription_events.extend((d, payee_name, avg_amount) for d in occurrences)

        # 4. Get historical daily net flows for stochastic layer — open CASH
        # accounts only, matching the balance being projected (a brokerage
        # swing is not a cash flow, and a card purchase moves no cash; the
        # cash leg of the card payment is already on the cash side).
        #
        # **Minus the flows the deterministic layer re-applies.** The two
        # layers have to partition the register: the deterministic events model
        # the known bills, the sampled history models only the variation left
        # over. Without the subtraction every scheduled bill and every
        # subscription charge landed in a simulated path TWICE — once sampled
        # out of its own history, once added from `det_by_date` — so p50 and
        # `goes_negative_date` were both biased by the whole recurring load.
        # R6 of docs/future-reports-roadmap.md specifies this as "trailing 180
        # days ... minus transactions of deterministic payees"; only the first
        # half was implemented.
        #
        # Exactly what the fixed layer re-applies, and nothing more: each
        # projected schedule's own rows and its bill, and each projected
        # subscription's charges (txn_filters' "what the fixed layer
        # re-applies"). This was `payee_id NOT IN (every deterministic payee)`,
        # which dropped every payee-less row — split lines included — the
        # moment one schedule had a payee, and took a subscription payee's
        # unrelated spending out of both layers.
        #
        # Every calendar day of the window, quiet ones included, and only from
        # the register's first row on (`history_window`, `zero_filled`). The
        # first row is read over the same accounts but before any exclusion:
        # it says when the register began, not what is sampled.
        first_row = (
            await self.session.execute(
                select(func.min(Transaction.date))
                .join(Account, Account.id == Transaction.account_id)
                .where(
                    Transaction.budget_id == budget_id,
                    NOT_DELETED,
                    POSTED,
                    Account.is_closed == False,  # noqa: E712
                    CASH_ACCOUNT,
                )
            )
        ).scalar_one_or_none()
        window = projection_history(today, first_row)
        history: list[Decimal] = []
        if window is not None:
            hist_q = (
                join_split_parent(
                    select(Transaction.date, func.sum(Transaction.amount).label("net"))
                )
                .join(Account, Account.id == Transaction.account_id)
                .where(
                    Transaction.budget_id == budget_id,
                    NOT_DELETED,
                    POSTED,
                    LEAF,
                    Transaction.date >= window.start,
                    Transaction.date <= window.end,
                    Account.is_closed == False,  # noqa: E712
                    CASH_ACCOUNT,
                    none_of(
                        *projected_schedules, reapplied_by_subscriptions(subscription_payee_ids)
                    ),
                    # Sampled, an account opened inside the window was a
                    # phantom deposit the size of its whole balance, replayed
                    # on every path that drew its day.
                    NOT_OPENING_BALANCE,
                )
                .group_by(Transaction.date)
            )
            hist_rows = (await self.session.execute(apply_class_joins(hist_q))).all()
            history = zero_filled(((r.date, r.net) for r in hist_rows), window)

        # 5. The fixed layer's net per day, and the simulation over both.
        det_by_date: dict[date, Decimal] = {}
        for d, _, amt in scheduled_events + subscription_events:
            det_by_date[d] = det_by_date.get(d, Decimal("0")) + amt

        projection = project(
            start_balance=start_balance,
            today=today,
            horizon_days=horizon_days,
            history=history,
            window=window,
            fixed=det_by_date,
        )
        points = [
            {
                "date": p.day,
                "p10": p.p10,
                "p25": p.p25,
                "p50": p.p50,
                "p75": p.p75,
                "p90": p.p90,
            }
            for p in projection.points
        ]

        # 6. Build events list (first 30 days only, for display)
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

        # 7. If income stopped: the runway at every choice the page offers,
        # each with its straight burn-down to zero or the horizon — the other
        # half of "how long does my money last", on the same axis as the
        # bands. It replaced a "Scheduled only" line (the fixed events alone),
        # which answered no question a household asks.
        stopped = await runway_read(self.session, budget_id, today)

        return {
            "start_balance": start_balance,
            "points": points,
            "events": events[:20],  # Limit to first 20 events
            "goes_negative_date": projection.goes_negative_date,
            "p10_negative_date": projection.p10_negative_date,
            "if_income_stopped": {
                "options": [
                    {
                        **asdict(option),
                        "line": [
                            {"date": point.day, "balance": point.balance}
                            for point in stopped.line(option, end_date)
                        ],
                    }
                    for option in stopped.options
                ],
                "default_spending": stopped.default.spending,
                "default_money": stopped.default.money,
                "fund_chosen": stopped.fund_chosen,
                "essentials_known": stopped.essentials_known,
                "window_start": stopped.window_start,
                "window_end": stopped.window_end,
            },
        }
