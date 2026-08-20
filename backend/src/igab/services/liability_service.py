"""Liability balance resolution, payment-history derivation, and payoff status.

A liability's current balance and payment history come from one of three places,
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
from typing import Literal

from igab.db.models import Liability
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.amortization import (
    AmortizationResult,
    LiveProjection,
    PromoOutlook,
    add_months,
    amortization_schedule,
    amortization_schedule_with_promo,
    project_payoff,
    promo_outlook,
    quantize_cents,
)
from igab.utils.clock import today_utc

ZERO = Decimal("0")

PAYMENT_LOOKBACK_MONTHS = 6

BalanceSource = Literal["ledger", "manual", "manual_fallback"]


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_index(d: date) -> int:
    return d.year * 12 + (d.month - 1)


@dataclass
class LiabilityStatus:
    liability: Liability
    mode: str  # 'managed' | 'unmanaged'
    current_balance: Decimal  # owed, positive
    # Where current_balance came from
    balance_source: BalanceSource
    baseline: AmortizationResult  # contractual schedule at minimum_payment
    live: LiveProjection | None  # None: not enough payment history
    recent_payments: list[Decimal]
    promo: PromoOutlook | None = None  # set when the liability has a promo window


class LiabilityService:
    def __init__(
        self,
        liability_repo: LiabilityRepository,
        account_repo: AccountRepository,
        category_repo: CategoryRepository,
        transaction_repo: TransactionRepository,
    ) -> None:
        self.liability_repo = liability_repo
        self.account_repo = account_repo
        self.category_repo = category_repo
        self.transaction_repo = transaction_repo

    @staticmethod
    def mode(liability: Liability) -> str:
        return "managed" if liability.linked_account_id is not None else "unmanaged"

    async def get_balance(self, liability: Liability) -> Decimal:
        """Amount currently owed, positive; zero when fully paid."""
        balance, _ = await self.get_balance_with_source(liability)
        return balance

    async def get_balance_with_source(self, liability: Liability) -> tuple[Decimal, BalanceSource]:
        """(amount owed, where it came from).

        Managed liabilities read their linked account's ledger — except when
        that register is EMPTY and a manual balance survives from before
        linking: a mortgage freshly linked to a transaction-less account must
        not report $0 owed ("Paid off") until the user seeds the register.
        """
        if liability.linked_account_id is not None:
            if liability.manual_balance is not None:
                txn_count = await self.transaction_repo.count_for_account(
                    liability.linked_account_id
                )
                if txn_count == 0:
                    return max(ZERO, quantize_cents(liability.manual_balance)), "manual_fallback"
            account_balance = await self.account_repo.get_balance(liability.linked_account_id)
            return max(ZERO, quantize_cents(-account_balance)), "ledger"
        return max(ZERO, quantize_cents(liability.manual_balance or ZERO)), "manual"

    async def get_recent_monthly_payments(
        self,
        liability: Liability,
        months: int = PAYMENT_LOOKBACK_MONTHS,
        as_of: date | None = None,
    ) -> list[Decimal]:
        """Per-month payments for the trailing `months` COMPLETE months,
        oldest first. Months without evidence contribute 0."""
        as_of = as_of or today_utc()
        current = _month_start(as_of)
        window = [add_months(current, -i) for i in range(months, 0, -1)]
        last_complete_end = current  # exclusive upper bound: 1st of current month

        if liability.linked_account_id is not None:
            by_month = await self.transaction_repo.sum_by_account_by_month(
                liability.linked_account_id, end_date=last_complete_end
            )
            # A loan account's balance rises toward zero as it's paid: the
            # month's net movement IS the paydown.
            return [max(ZERO, by_month.get(m, ZERO)) for m in window]

        category = await self.category_repo.get_by_linked_liability(liability.id)
        if category is not None:
            by_month = await self.transaction_repo.sum_category_outflows_by_month(
                category.id, end_date=last_complete_end
            )
            return [max(ZERO, -by_month.get(m, ZERO)) for m in window]

        return self._payments_from_snapshots(
            await self.liability_repo.get_snapshots(liability.id), window
        )

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

    async def get_status(self, liability: Liability, as_of: date | None = None) -> LiabilityStatus:
        as_of = as_of or today_utc()
        balance, balance_source = await self.get_balance_with_source(liability)
        if liability.promo_end_date is not None:
            baseline = amortization_schedule_with_promo(
                balance,
                liability.interest_rate,
                liability.minimum_payment,
                as_of,
                liability.promo_end_date,
            )
        else:
            baseline = amortization_schedule(
                balance, liability.interest_rate, liability.minimum_payment, as_of
            )
        payments = await self.get_recent_monthly_payments(liability, as_of=as_of)
        # Live projection stays at the contract rate even during a promo —
        # a conservative date beats an optimistic one that assumes the
        # balance clears before interest starts.
        live = project_payoff(balance, liability.interest_rate, payments, as_of)
        promo: PromoOutlook | None = None
        if liability.promo_end_date is not None and balance > ZERO:
            promo = promo_outlook(
                balance,
                liability.interest_rate,
                liability.minimum_payment,
                live.average_payment if live else None,
                as_of,
                liability.promo_end_date,
                liability.promo_deferred_interest,
                liability.origination_date,
                liability.original_principal,
            )
        return LiabilityStatus(
            liability=liability,
            mode=self.mode(liability),
            current_balance=balance,
            balance_source=balance_source,
            baseline=baseline,
            live=live,
            recent_payments=payments,
            promo=promo,
        )

    async def get_balance_history(
        self, liability: Liability, as_of: date | None = None
    ) -> list[tuple[date, Decimal]]:
        """Actual owed-balance points over time (the chart's solid segment).

        Managed: monthly cumulated account movement from the first ledger
        month through today. Unmanaged: the raw balance snapshots.
        """
        as_of = as_of or today_utc()
        if liability.linked_account_id is not None:
            by_month = await self.transaction_repo.sum_by_account_by_month(
                liability.linked_account_id, end_date=as_of
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
        snapshots = await self.liability_repo.get_snapshots(liability.id)
        return [(s.date, max(ZERO, quantize_cents(s.balance))) for s in snapshots]

    async def unmanaged_total(self, budget_id: uuid.UUID) -> Decimal:
        """Total owed across unmanaged liabilities — the net-worth bucket for
        liabilities that have no Account and would otherwise vanish."""
        total = ZERO
        for liability in await self.liability_repo.get_all(budget_id):
            if liability.linked_account_id is None:
                total += await self.get_balance(liability)
        return total

    async def liabilities_report(
        self,
        budget_id: uuid.UUID,
        *,
        liability_type: str | None = None,
        mode: str | None = None,
        as_of: date | None = None,
    ) -> dict:
        """Cross-liability rollup: per-liability status rows, totals, and a monthly
        balance-over-time series (forward-filled between sparse points) for
        the consolidated Liabilities report. No new math — pure aggregation."""
        as_of = as_of or today_utc()
        liabilities = await self.liability_repo.get_all(budget_id)
        if liability_type is not None:
            liabilities = [item for item in liabilities if item.liability_type == liability_type]
        if mode is not None:
            liabilities = [item for item in liabilities if self.mode(item) == mode]

        items: list[dict] = []
        per_liability_monthly: dict[str, dict[date, Decimal]] = {}
        current_month = _month_start(as_of)

        for liability in liabilities:
            status = await self.get_status(liability, as_of=as_of)
            never = status.live.never_pays_off if status.live else status.baseline.never_pays_off
            items.append(
                {
                    "liability_id": liability.id,
                    "name": liability.name,
                    "liability_type": liability.liability_type,
                    "mode": status.mode,
                    "current_balance": status.current_balance,
                    "interest_rate": liability.interest_rate,
                    "baseline_payoff_date": status.baseline.payoff_date,
                    "live_payoff_date": status.live.payoff_date if status.live else None,
                    "total_interest_remaining": status.baseline.total_interest,
                    "never_pays_off": never,
                }
            )
            monthly: dict[date, Decimal] = {}
            for point_date, balance in await self.get_balance_history(liability, as_of=as_of):
                monthly[_month_start(point_date)] = balance  # last point in a month wins
            monthly[current_month] = status.current_balance
            per_liability_monthly[str(liability.id)] = monthly

        total_balance = sum((i["current_balance"] for i in items), ZERO)
        total_interest = sum((i["total_interest_remaining"] for i in items), ZERO)

        points: list[dict] = []
        if per_liability_monthly:
            first_month = min(m for monthly in per_liability_monthly.values() for m in monthly)
            last_known: dict[str, Decimal] = {}
            month = first_month
            while month <= current_month:
                per_liability: dict[str, Decimal] = {}
                for key, monthly in per_liability_monthly.items():
                    if month in monthly:
                        last_known[key] = monthly[month]
                    if key in last_known:
                        per_liability[key] = last_known[key]
                points.append(
                    {
                        "date": month,
                        "per_liability": per_liability,
                        "total": sum(per_liability.values(), ZERO),
                    }
                )
                month = add_months(month, 1)

        return {
            "items": items,
            "total_balance": total_balance,
            "total_interest_remaining": total_interest,
            "balance_over_time": points,
        }
