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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Liability
from igab.domain.dates import add_months
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.amortization import (
    AmortizationResult,
    LiveProjection,
    PromoOutlook,
    amortization_schedule,
    amortization_schedule_with_promo,
    average_recent_payment,
    project_payoff,
    promo_outlook,
    quantize_cents,
)
from igab.utils.clock import today_utc

ZERO = Decimal("0")

PAYMENT_LOOKBACK_MONTHS = 6

BalanceSource = Literal["ledger", "manual", "manual_fallback"]

LIABILITY_CLASSIFICATION = "liability"


async def ensure_for_account(session: AsyncSession, account: Account) -> Liability | None:
    """Guarantee the companion Liability for a liability-classified account.

    The invariant every consumer downstream of this leans on: if an account
    classifies as a liability, a Liability row is attached to it. Without it,
    creating a Loan account gets you a working ledger and none of the loan
    features — no APR, no amortization, no payoff estimate — with nothing in
    the product saying a second record is what's missing. That dead end is what
    this closes, and it closes by construction rather than by prompting.

    The row is created with NO terms. It contributes no numbers: `manual_balance`
    is authoritative only when unlinked, and this row is linked, so its balance
    comes from the account's ledger exactly as the account's own balance does.
    Nothing is computed from the absent terms (see `get_status`). It is inert
    until someone fills it in.

    Idempotent, and it adopts a soft-deleted companion rather than inserting
    beside it — `liabilities.linked_account_id` is plainly unique, so a deleted
    row still occupies the slot. Reviving is also the truthful outcome: the
    account still exists and still classifies as debt, so the companion should,
    and the user's own terms come back with it.

    Returns the row it created or revived, and None when there was nothing to
    do — the account is not a liability, or its companion already stands. So
    callers may fire and forget, and a caller that is counting what it made
    can branch on the result without double-counting rows it did not create.
    """
    if account.classification != LIABILITY_CLASSIFICATION or account.is_deleted:
        return None

    # No is_deleted filter: the unique constraint does not have one either.
    existing = (
        await session.execute(select(Liability).where(Liability.linked_account_id == account.id))
    ).scalar_one_or_none()
    if existing is not None:
        if not existing.is_deleted:
            return None
        existing.is_deleted = False
        await session.flush()
        return existing

    # No stored type: a linked liability reads its account's, so storing one
    # would be the duplicated field this model set out to remove.
    liability = Liability(
        budget_id=account.budget_id,
        name=account.name,
        liability_type=None,
        linked_account_id=account.id,
        interest_rate=None,
        minimum_payment=None,
    )
    session.add(liability)
    await session.flush()
    return liability


async def release_for_account(session: AsyncSession, account: Account) -> None:
    """An account has stopped classifying as a liability — retyped to an asset.

    Only the empty case is handled here, and only because it is unambiguous:
    a companion nobody filled in has nothing to lose, which is the same test
    the delete flow applies. A companion carrying real terms, snapshots or a
    linked category is a conversion — managed debt becoming manually tracked
    debt — and converting silently is exactly what this work decided not to do.
    That belongs with the account-deletion dialog that already asks the
    question, so a populated companion is left linked here.

    Left linked, it reads $0 owed rather than a wrong number: a managed balance
    is `max(0, -account_balance)`, and an asset account in credit negates to
    nothing.
    """
    companion = (
        await session.execute(
            select(Liability).where(
                Liability.linked_account_id == account.id,
                Liability.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if companion is None:
        return
    untouched = (
        companion.interest_rate is None
        and companion.minimum_payment is None
        and companion.origination_date is None
        and companion.original_principal is None
        and companion.promo_end_date is None
        and companion.term_months is None
    )
    if untouched:
        companion.is_deleted = True
        await session.flush()


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
    # Whether interest_rate and minimum_payment are both set. False leaves
    # every contract-derived field below at None: see get_status.
    terms_complete: bool
    # Contractual schedule at minimum_payment. None when the terms are unset.
    baseline: AmortizationResult | None
    live: LiveProjection | None  # None: not enough payment history, or no terms
    recent_payments: list[Decimal]
    # Pace from observed history, independent of the contract — so it survives
    # when there are no terms to project against.
    average_payment: Decimal | None
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

    async def resolve_type(self, liability: Liability) -> str:
        """What kind of debt this is, from whichever side is authoritative.

        Same rule the model already applies to `manual_balance` — the stored
        column speaks only when `linked_account_id IS NULL`. A managed
        liability's kind is its account's type, because the account is the
        thing the user actually picked a type for, and keeping a second answer
        beside it is how the two drift apart.

        The account-type registry was made specific enough to carry this
        (`mortgage`, `auto_loan`, `student_loan` alongside `credit_card` and a
        generic `loan`), so deriving loses nothing that was there before. A
        custom liability-classified type answers as itself, which is why there
        is no mapping table here and a user's "HELOC" reads as HELOC.
        """
        if liability.linked_account_id is None:
            return liability.liability_type or "other"
        account = await self.account_repo.get(liability.linked_account_id)
        if account is None:
            # The link outlived its account. Fall back rather than invent.
            return liability.liability_type or "other"
        return account.account_type

    @staticmethod
    def terms_complete(liability: Liability) -> bool:
        """Whether the contract terms every projection needs are known.

        Both or neither: a rate without a payment cannot produce a schedule and
        neither can a payment without a rate, so one flag answers the only
        question a consumer has. A companion liability created with its account
        starts False and stays there until someone fills the terms in.
        """
        return liability.interest_rate is not None and liability.minimum_payment is not None

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
        """Everything known about a liability right now.

        Balance and payment history are observed — they hold whether or not the
        contract terms are on file. The schedule, the live projection and the
        promo outlook are all derived FROM those terms, so without them there is
        nothing to derive and each is returned as None. They are not computed at
        zero: `amortization_schedule` treats a payment that fails to cover the
        month's interest as proof the debt never retires, so zero terms would
        report `never_pays_off=True` — a fabricated claim that rides into the
        Liabilities report's interest total, not merely a label on a page.
        """
        as_of = as_of or today_utc()
        balance, balance_source = await self.get_balance_with_source(liability)
        payments = await self.get_recent_monthly_payments(liability, as_of=as_of)
        average = average_recent_payment(payments)

        rate = liability.interest_rate
        minimum = liability.minimum_payment
        baseline: AmortizationResult | None = None
        live: LiveProjection | None = None
        promo: PromoOutlook | None = None

        if rate is not None and minimum is not None:
            if liability.promo_end_date is not None:
                baseline = amortization_schedule_with_promo(
                    balance, rate, minimum, as_of, liability.promo_end_date
                )
            else:
                baseline = amortization_schedule(balance, rate, minimum, as_of)
            # Live projection stays at the contract rate even during a promo —
            # a conservative date beats an optimistic one that assumes the
            # balance clears before interest starts.
            live = project_payoff(balance, rate, payments, as_of)
            if liability.promo_end_date is not None and balance > ZERO:
                promo = promo_outlook(
                    balance,
                    rate,
                    minimum,
                    average,
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
            terms_complete=rate is not None and minimum is not None,
            baseline=baseline,
            live=live,
            recent_payments=payments,
            average_payment=average,
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
        resolved_types = {item.id: await self.resolve_type(item) for item in liabilities}
        # Filter on what the report SHOWS. Filtering the stored column instead
        # would hide rows whose visible type matches and surface ones whose
        # does not — the pre-derivation column is not what anyone is reading.
        if liability_type is not None:
            liabilities = [
                item for item in liabilities if resolved_types[item.id] == liability_type
            ]
        if mode is not None:
            liabilities = [item for item in liabilities if self.mode(item) == mode]

        items: list[dict] = []
        per_liability_monthly: dict[str, dict[date, Decimal]] = {}
        current_month = _month_start(as_of)

        for liability in liabilities:
            status = await self.get_status(liability, as_of=as_of)
            baseline = status.baseline
            # Unknown is not "never". Without terms there is no schedule to ask,
            # and answering True would assert something about the user's debt
            # that nobody has told us.
            if status.live is not None:
                never = status.live.never_pays_off
            elif baseline is not None:
                never = baseline.never_pays_off
            else:
                never = False
            items.append(
                {
                    "liability_id": liability.id,
                    "name": liability.name,
                    "liability_type": resolved_types[liability.id],
                    "mode": status.mode,
                    "current_balance": status.current_balance,
                    "interest_rate": liability.interest_rate,
                    "baseline_payoff_date": baseline.payoff_date if baseline else None,
                    "live_payoff_date": status.live.payoff_date if status.live else None,
                    "total_interest_remaining": baseline.total_interest if baseline else None,
                    "never_pays_off": never,
                    "terms_complete": status.terms_complete,
                }
            )
            monthly: dict[date, Decimal] = {}
            for point_date, balance in await self.get_balance_history(liability, as_of=as_of):
                monthly[_month_start(point_date)] = balance  # last point in a month wins
            monthly[current_month] = status.current_balance
            per_liability_monthly[str(liability.id)] = monthly

        total_balance = sum((i["current_balance"] for i in items), ZERO)
        # Only rows with terms contribute interest, so the total is a floor
        # rather than a full figure whenever some are unset. `missing_terms`
        # travels with it so the report can say so instead of quietly
        # under-reporting — a balance is still a balance either way.
        total_interest = sum(
            (
                i["total_interest_remaining"]
                for i in items
                if i["total_interest_remaining"] is not None
            ),
            ZERO,
        )
        missing_terms = sum(1 for i in items if not i["terms_complete"])

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
            "liabilities_missing_terms": missing_terms,
            "balance_over_time": points,
        }
