"""The money a runway can count, read once (`domain.runway.Holdings`).

Wiring only: each figure is its own report's — the budget's cash is Ready to
Assign's balance term, the card debt is the budget page's card balances, the
fund is `services.emergency_fund`, and the savings accounts are the Savings
report's that hold cash (`txn_filters.CASH_SAVINGS_ACCOUNT`). The rule that
composes them is `domain.runway.money_for`.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account
from igab.domain.runway import Holdings, card_debt
from igab.repositories.account_repo import AccountRepository
from igab.repositories.txn_filters import CASH_SAVINGS_ACCOUNT, EMERGENCY_FUND_ACCOUNT
from igab.services.emergency_fund import EmergencyFund

ZERO = Decimal("0")


async def _cash_savings(accounts: AccountRepository, budget_id: uuid.UUID) -> Decimal:
    """Every savings account that holds cash, and the fund's marked accounts
    whatever their type, at their balance. The fund's accounts are in because
    the person chose them as money to live on, and so that "+ savings
    accounts" never counts less than "+ emergency fund" beside it."""
    ids = (
        (
            await accounts.session.execute(
                select(Account.id).where(
                    Account.budget_id == budget_id,
                    or_(CASH_SAVINGS_ACCOUNT, EMERGENCY_FUND_ACCOUNT),
                )
            )
        )
        .scalars()
        .all()
    )
    return sum((await accounts.balances_for(list(ids))).values(), ZERO)


async def holdings(
    session: AsyncSession, budget_id: uuid.UUID, today: date, fund: EmergencyFund
) -> Holdings:
    """What the budget holds and owes on the reader's `today`.

    Cash and cards through the same day (`sum_on_budget_balance`,
    `card_balances`), so the two partition the on-budget balance and a
    future-dated payment moves neither. The fund is the caller's, read once
    for the report that also quotes it.
    """
    accounts = AccountRepository(session)
    return Holdings(
        cash=await accounts.sum_on_budget_balance(budget_id, today),
        card_debt=card_debt((await accounts.card_balances(budget_id, today)).values()),
        fund=fund.total,
        fund_accounts=sum((p.balance for p in fund.accounts), ZERO),
        declared=fund.external.amount or ZERO,
        savings_accounts=await _cash_savings(accounts, budget_id),
    )
