"""Debt balance resolution, payment-history derivation, and payoff status.

A debt's current balance and payment history come from one of three places,
in priority order:

- managed (linked account): balance from the account ledger; monthly
  payments are the account's net balance movement per month.
- unmanaged + linked category: balance from manual_balance; payments are
  the category's monthly outflows.
- unmanaged + snapshots only: balance from manual_balance; payments are
  interpolated from balance drops between consecutive snapshots.

Every payment path floors months at zero — a balance increase is not a
negative payment. Balances are always "amount owed", positive.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from igab.db.models import Debt
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.debt_repo import DebtRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.debt_math import (
    AmortizationResult,
    LiveProjection,
    add_months,
    amortization_schedule,
    project_payoff,
    quantize_cents,
)
from igab.utils.clock import today_utc

ZERO = Decimal("0")

PAYMENT_LOOKBACK_MONTHS = 6


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_index(d: date) -> int:
    return d.year * 12 + (d.month - 1)


@dataclass
class DebtStatus:
    debt: Debt
    mode: str  # 'managed' | 'unmanaged'
    current_balance: Decimal  # owed, positive
    baseline: AmortizationResult  # contractual schedule at minimum_payment
    live: LiveProjection | None  # None: not enough payment history
    recent_payments: list[Decimal]


class DebtService:
    def __init__(
        self,
        debt_repo: DebtRepository,
        account_repo: AccountRepository,
        category_repo: CategoryRepository,
        transaction_repo: TransactionRepository,
    ) -> None:
        self.debt_repo = debt_repo
        self.account_repo = account_repo
        self.category_repo = category_repo
        self.transaction_repo = transaction_repo

    @staticmethod
    def mode(debt: Debt) -> str:
        return "managed" if debt.linked_account_id is not None else "unmanaged"

    async def get_balance(self, debt: Debt) -> Decimal:
        """Amount currently owed, positive; zero when fully paid."""
        if debt.linked_account_id is not None:
            account_balance = await self.account_repo.get_balance(debt.linked_account_id)
            return max(ZERO, quantize_cents(-account_balance))
        return max(ZERO, quantize_cents(debt.manual_balance or ZERO))

    async def get_recent_monthly_payments(
        self,
        debt: Debt,
        months: int = PAYMENT_LOOKBACK_MONTHS,
        as_of: date | None = None,
    ) -> list[Decimal]:
        """Per-month payments for the trailing `months` COMPLETE months,
        oldest first. Months without evidence contribute 0."""
        as_of = as_of or today_utc()
        current = _month_start(as_of)
        window = [add_months(current, -i) for i in range(months, 0, -1)]
        last_complete_end = current  # exclusive upper bound: 1st of current month

        if debt.linked_account_id is not None:
            by_month = await self.transaction_repo.sum_by_account_by_month(
                debt.linked_account_id, end_date=last_complete_end
            )
            # A loan account's balance rises toward zero as it's paid: the
            # month's net movement IS the paydown.
            return [max(ZERO, by_month.get(m, ZERO)) for m in window]

        category = await self.category_repo.get_by_linked_debt(debt.id)
        if category is not None:
            by_month = await self.transaction_repo.sum_category_outflows_by_month(
                category.id, end_date=last_complete_end
            )
            return [max(ZERO, -by_month.get(m, ZERO)) for m in window]

        return self._payments_from_snapshots(await self.debt_repo.get_snapshots(debt.id), window)

    @staticmethod
    def _payments_from_snapshots(snapshots, window: list[date]) -> list[Decimal]:
        """Spread each consecutive balance drop evenly across the months the
        pair spans; balance increases contribute nothing."""
        by_month: dict[date, Decimal] = {}
        for prev, nxt in zip(snapshots, snapshots[1:], strict=False):
            drop = prev.balance - nxt.balance
            if drop <= ZERO:
                continue
            span = max(1, _month_index(nxt.date) - _month_index(prev.date))
            per_month = quantize_cents(drop / span)
            for i in range(span):
                m = add_months(_month_start(prev.date), i + 1)
                by_month[m] = by_month.get(m, ZERO) + per_month
        return [max(ZERO, by_month.get(m, ZERO)) for m in window]

    async def get_status(self, debt: Debt, as_of: date | None = None) -> DebtStatus:
        as_of = as_of or today_utc()
        balance = await self.get_balance(debt)
        baseline = amortization_schedule(balance, debt.interest_rate, debt.minimum_payment, as_of)
        payments = await self.get_recent_monthly_payments(debt, as_of=as_of)
        live = project_payoff(balance, debt.interest_rate, payments, as_of)
        return DebtStatus(
            debt=debt,
            mode=self.mode(debt),
            current_balance=balance,
            baseline=baseline,
            live=live,
            recent_payments=payments,
        )

    async def get_balance_history(
        self, debt: Debt, as_of: date | None = None
    ) -> list[tuple[date, Decimal]]:
        """Actual owed-balance points over time (the chart's solid segment).

        Managed: monthly cumulated account movement from the first ledger
        month through today. Unmanaged: the raw balance snapshots.
        """
        as_of = as_of or today_utc()
        if debt.linked_account_id is not None:
            by_month = await self.transaction_repo.sum_by_account_by_month(
                debt.linked_account_id, end_date=as_of
            )
            if not by_month:
                return []
            points: list[tuple[date, Decimal]] = []
            running = ZERO
            month = min(by_month)
            current = _month_start(as_of)
            while month <= current:
                running += by_month.get(month, ZERO)
                points.append((month, max(ZERO, quantize_cents(-running))))
                month = add_months(month, 1)
            return points
        snapshots = await self.debt_repo.get_snapshots(debt.id)
        return [(s.date, max(ZERO, quantize_cents(s.balance))) for s in snapshots]

    async def unmanaged_total(self, budget_id: uuid.UUID) -> Decimal:
        """Total owed across unmanaged debts — the net-worth bucket for
        liabilities that have no Account and would otherwise vanish."""
        total = ZERO
        for debt in await self.debt_repo.get_all(budget_id):
            if debt.linked_account_id is None:
                total += await self.get_balance(debt)
        return total

    async def debts_report(
        self,
        budget_id: uuid.UUID,
        *,
        debt_type: str | None = None,
        mode: str | None = None,
        as_of: date | None = None,
    ) -> dict:
        """Cross-debt rollup: per-debt status rows, totals, and a monthly
        balance-over-time series (forward-filled between sparse points) for
        the consolidated Debts report. No new math — pure aggregation."""
        as_of = as_of or today_utc()
        debts = await self.debt_repo.get_all(budget_id)
        if debt_type is not None:
            debts = [d for d in debts if d.debt_type == debt_type]
        if mode is not None:
            debts = [d for d in debts if self.mode(d) == mode]

        items: list[dict] = []
        per_debt_monthly: dict[str, dict[date, Decimal]] = {}
        current_month = _month_start(as_of)

        for debt in debts:
            status = await self.get_status(debt, as_of=as_of)
            never = status.live.never_pays_off if status.live else status.baseline.never_pays_off
            items.append(
                {
                    "debt_id": debt.id,
                    "name": debt.name,
                    "debt_type": debt.debt_type,
                    "mode": status.mode,
                    "current_balance": status.current_balance,
                    "interest_rate": debt.interest_rate,
                    "baseline_payoff_date": status.baseline.payoff_date,
                    "live_payoff_date": status.live.payoff_date if status.live else None,
                    "total_interest_remaining": status.baseline.total_interest,
                    "never_pays_off": never,
                }
            )
            monthly: dict[date, Decimal] = {}
            for point_date, balance in await self.get_balance_history(debt, as_of=as_of):
                monthly[_month_start(point_date)] = balance  # last point in a month wins
            monthly[current_month] = status.current_balance
            per_debt_monthly[str(debt.id)] = monthly

        total_balance = sum((i["current_balance"] for i in items), ZERO)
        total_interest = sum((i["total_interest_remaining"] for i in items), ZERO)

        points: list[dict] = []
        if per_debt_monthly:
            first_month = min(m for monthly in per_debt_monthly.values() for m in monthly)
            last_known: dict[str, Decimal] = {}
            month = first_month
            while month <= current_month:
                per_debt: dict[str, Decimal] = {}
                for key, monthly in per_debt_monthly.items():
                    if month in monthly:
                        last_known[key] = monthly[month]
                    if key in last_known:
                        per_debt[key] = last_known[key]
                points.append(
                    {
                        "date": month,
                        "per_debt": per_debt,
                        "total": sum(per_debt.values(), ZERO),
                    }
                )
                month = add_months(month, 1)

        return {
            "items": items,
            "total_balance": total_balance,
            "total_interest_remaining": total_interest,
            "balance_over_time": points,
        }
