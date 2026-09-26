"""The money a runway can count, read once (`domain.runway.Holdings`).

Wiring only: each figure is its own report's — the budget's cash is Ready to
Assign's balance term, the card debt is the budget page's card balances, the
fund is `services.emergency_fund`, and the savings accounts are the Savings
report's. The rule that composes them is `domain.runway.money_for`.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.domain.runway import Holdings, card_debt
from igab.repositories.account_repo import AccountRepository
from igab.services.emergency_fund import EmergencyFund
from igab.services.savings_report import saved_accounts_total

ZERO = Decimal("0")


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
        savings_accounts=await saved_accounts_total(session, budget_id),
    )
