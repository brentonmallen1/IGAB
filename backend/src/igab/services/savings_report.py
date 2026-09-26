"""The Savings report, in three parts.

- **Saved** — what is set aside and stays set aside: the kept-here Savings and
  Emergency fund envelopes (`category_filters.HOLDS_SAVINGS`) and the
  off-budget accounts that count as savings (`txn_filters.SAVINGS_ACCOUNT`).
- **On the way to savings** — what sent-out Savings envelopes
  (`category_filters.SENDS_SAVINGS`) hold until the money leaves. It counts as
  saved when it is sent (the classifier's rule 2), so it is shown beside Saved
  and never added to it.
- **Sinking funds** — Long-term expense envelopes that are not savings
  (`category_filters.IS_SINKING_FUND`), with their target progress. Spoken for
  by a planned bill: never savings, never added to Saved.

**No double count between an envelope and an account.** A kept-here envelope
that moves $300 to a tracked savings account loses $300 of Available and the
account gains $300: Saved does not move, the same way `domain/savings.py` nets
held against moved. **On-budget accounts are never listed** — their money is
already in the envelopes, and adding the account would count it twice.

Envelope balances come from the Budget page's own walk
(`BudgetService.envelope_series`); nothing here decides money the budget page
does not already show. Every section total counts an envelope at its
carryover-floored Available (`domain.carryover.next_carryover`), the floor the
held figure uses: an overspent envelope was covered from Ready to Assign and
holds nothing. The rows themselves state the page's Available unfloored.

**Drains** — "What pulled from savings" — are budget moves out of any Savings
or Emergency fund envelope, kept here or sent out, a since-deleted one
included. A move out of a sinking fund is re-planning a bill, not dissaving,
and is not listed.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Budget, Category, CategoryGroup, CategoryTarget
from igab.domain.carryover import next_carryover
from igab.domain.dates import add_months, clamped_month_end, report_months
from igab.domain.drains import drains_total, shape_drains
from igab.domain.enums import TargetStatus, TargetType
from igab.repositories.account_repo import AccountRepository
from igab.repositories.budget_move_repo import BudgetMoveRepository
from igab.repositories.category_filters import (
    BUDGETED_ENVELOPE,
    HOLDS_SAVINGS,
    IS_SINKING_FUND,
    SAVINGS_CATEGORY_KEYS,
    SENDS_SAVINGS,
)
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.tag_repo import TagRepository
from igab.repositories.target_repo import TargetRepository
from igab.repositories.txn_filters import SAVINGS_ACCOUNT
from igab.services.target_service import TargetService

if TYPE_CHECKING:
    from igab.services.budget_service import EnvelopeSeries

ZERO = Decimal("0")
PROGRESS_PLACES = Decimal("0.0001")


class SavingsTarget(TypedDict):
    type: str
    amount: Decimal
    target_date: date | None
    #: The Budget page's pill for the current month (`TargetService.calculate_status`).
    status: TargetStatus
    #: Available ÷ amount for a savings-balance target, floored at 0 and not
    #: capped; None for a funding target, which asks for a pace, not a balance.
    progress: Decimal | None


class SavingsEnvelope(TypedDict):
    category_id: str
    category_name: str
    group_name: str
    monthly_balances: list[Decimal | None]
    current_balance: Decimal
    total_inflow: Decimal
    target: SavingsTarget | None


class SavingsAccountRow(TypedDict):
    account_id: str
    name: str
    account_type: str
    #: Balance through each month's end, the running month through today.
    #: None before the account's first row: not a zero tile.
    monthly_balances: list[Decimal | None]
    current_balance: Decimal


def _progress(target: CategoryTarget, available: Decimal) -> Decimal | None:
    if target.target_type != TargetType.SAVINGS_BALANCE or target.target_amount <= 0:
        return None
    return max(ZERO, available / target.target_amount).quantize(PROGRESS_PLACES)


async def _saved_accounts(
    session: AsyncSession, budget_id: uuid.UUID, month_list: list[date], today: date
) -> list[SavingsAccountRow]:
    rows = (
        await session.execute(
            select(Account.id, Account.name, Account.account_type, Account.is_closed)
            .where(Account.budget_id == budget_id, SAVINGS_ACCOUNT)
            .order_by(Account.sort_order, Account.name)
        )
    ).all()
    if not rows:
        return []
    repo = AccountRepository(session)
    current = await repo.balances_for([r.id for r in rows])
    through = await repo.balances_through(
        budget_id, [clamped_month_end(m, today) for m in month_list]
    )
    out: list[SavingsAccountRow] = []
    for r in rows:
        first, balances = through.get(r.id, (len(month_list), []))
        monthly: list[Decimal | None] = [
            balances[i] if i >= first else None for i in range(len(month_list))
        ]
        # A closed account that held nothing in the window is history, not a row.
        if r.is_closed and not current[r.id] and not any(b for b in monthly if b):
            continue
        out.append(
            {
                "account_id": str(r.id),
                "name": r.name,
                "account_type": r.account_type,
                "monthly_balances": monthly,
                "current_balance": current[r.id],
            }
        )
    out.sort(key=lambda a: a["current_balance"], reverse=True)
    return out


def _section_total(envelopes: list[SavingsEnvelope]) -> Decimal:
    """What a section's envelopes hold, each at its carryover-floored Available."""
    return sum((next_carryover(e["current_balance"]) for e in envelopes), ZERO)


async def savings_report(session: AsyncSession, budget_id: uuid.UUID, months: int = 12) -> dict:
    """Saved, On the way to savings and Sinking funds over the last `months`."""
    # No early return, tagged or not: two returned two empties (`months`
    # [] beside the window) and one dropped the drains this path keeps.
    end_date = date.today()
    month_list = report_months(end_date, months)
    start_date = month_list[0]

    # What pulled from savings: moves out of every Savings or Emergency fund
    # envelope in the window, a since-deleted one included (the move
    # happened), named on both sides. The same rows the wishlist reads for its
    # envelopes.
    savings_ids = await TagRepository(session).get_category_ids_by_system_keys(
        budget_id, SAVINGS_CATEGORY_KEYS
    )
    moves = await BudgetMoveRepository(session).outflows_from(
        budget_id, list(savings_ids), start_date, end_date
    )
    every_category = await CategoryRepository(session).get_all(budget_id, include_archived=True)
    shaped = shape_drains(moves, {c.id: c.name for c in every_category})
    drains = {"total": drains_total(shaped), "moves": [d.__dict__ for d in shaped]}

    # Which envelope sits in which section. A category is in at most one: the
    # three predicates are disjoint (kept here, sent out, not savings at all).
    # BUDGETED_ENVELOPE: a tag outlives the category it was on, and a
    # soft-deleted envelope is not a row.
    rows = (
        await session.execute(
            select(
                Category.id,
                Category.name,
                CategoryGroup.name.label("group_name"),
                HOLDS_SAVINGS.label("holds"),
                SENDS_SAVINGS.label("sends"),
            )
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Category.budget_id == budget_id,
                BUDGETED_ENVELOPE,
                or_(HOLDS_SAVINGS, SENDS_SAVINGS, IS_SINKING_FUND),
            )
        )
    ).all()
    ids = [r.id for r in rows]

    # Available from the Budget page's own walk (`envelope_series`), never a
    # copy of it: floored between months, card-corrected, and on an imported
    # budget walked back from YNAB's figure — an envelope whose history cannot
    # reproduce it starts late, and `unrecovered` says so.
    from igab.guide.detection import budget_service_from

    series: dict[uuid.UUID, EnvelopeSeries] = (
        await budget_service_from(session).envelope_series(budget_id, ids, month_list)
        if ids
        else {}
    )
    targets = {t.category_id: t for t in await TargetRepository(session).get_by_category_ids(ids)}
    budget = await session.get(Budget, budget_id)
    funding_day = budget.funding_day if budget else 1
    target_math = TargetService(TargetRepository(session))

    saved: list[SavingsEnvelope] = []
    on_the_way: list[SavingsEnvelope] = []
    sinking: list[SavingsEnvelope] = []
    unrecovered: list[dict] = []
    for r in rows:
        s = series[r.id]
        if s.unrecovered_through is not None:
            unrecovered.append(
                {
                    "category_id": str(r.id),
                    "category_name": r.name,
                    "starts_from": add_months(s.unrecovered_through, 1),
                }
            )
        available = s.latest()
        target: SavingsTarget | None = None
        if (t := targets.get(r.id)) is not None:
            target = {
                "type": t.target_type,
                "amount": t.target_amount,
                "target_date": t.target_date,
                # Same composition as the budget month endpoint, so the status
                # here is the pill the Budget page shows this month.
                "status": target_math.calculate_status(
                    t,
                    s.assigned[-1],
                    available,
                    month=month_list[-1],
                    today=end_date,
                    funding_day=funding_day,
                ),
                "progress": _progress(t, available),
            }
        envelope: SavingsEnvelope = {
            "category_id": str(r.id),
            "category_name": r.name,
            "group_name": r.group_name,
            "monthly_balances": s.available,
            "current_balance": available,
            "total_inflow": sum((a for a in s.assigned if a > 0), ZERO),
            "target": target,
        }
        (saved if r.holds else on_the_way if r.sends else sinking).append(envelope)

    for section in (saved, on_the_way, sinking):
        section.sort(key=lambda e: e["current_balance"], reverse=True)

    accounts = await _saved_accounts(session, budget_id, month_list, end_date)
    envelopes_total = _section_total(saved)
    accounts_total = sum((a["current_balance"] for a in accounts), ZERO)
    monthly_totals = [
        sum(
            (next_carryover(e["monthly_balances"][i] or ZERO) for e in saved),
            ZERO,
        )
        + sum((a["monthly_balances"][i] or ZERO for a in accounts), ZERO)
        for i in range(len(month_list))
    ]

    return {
        "saved": {
            "total": envelopes_total + accounts_total,
            "envelopes_total": envelopes_total,
            "accounts_total": accounts_total,
            "monthly_totals": monthly_totals,
            "envelopes": saved,
            "accounts": accounts,
        },
        "on_the_way": {"total": _section_total(on_the_way), "envelopes": on_the_way},
        "sinking_funds": {"total": _section_total(sinking), "envelopes": sinking},
        "months": month_list,
        "drains": drains,
        "unrecovered": unrecovered,
    }
