"""The Savings report: envelope balances over time for the categories tagged
Savings or Long-term expense, and what was moved out of them.

Split from report_service.py, which is over the file-length budget and may
only shrink. Balances come from the Budget page's own walk
(`BudgetService.envelope_series`) and nothing here decides money the budget
page does not already show.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, CategoryGroup
from igab.domain.dates import add_months, report_months
from igab.domain.drains import drains_total, shape_drains
from igab.domain.money import quantize_cents
from igab.repositories.budget_move_repo import BudgetMoveRepository
from igab.repositories.category_filters import BUDGETED_ENVELOPE
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.tag_repo import TagRepository


class SavingsCategory(TypedDict):
    category_id: str
    category_name: str
    group_name: str
    monthly_balances: list[Decimal | None]
    current_balance: Decimal
    target_balance: Decimal | None
    total_inflow: Decimal


async def savings_report(session: AsyncSession, budget_id: uuid.UUID, months: int = 12) -> dict:
    """Aggregate categories tagged with 'savings' or 'long_term_expense'."""
    tag_repo = TagRepository(session)

    # Get category IDs tagged with savings or long_term_expense
    savings_cat_ids = await tag_repo.get_category_ids_by_system_keys(
        budget_id, ["savings", "long_term_expense"]
    )
    # No early return, tagged or not: two returned two empties (`months`
    # [] beside the window) and one dropped the drains this path keeps.

    # Date range
    end_date = date.today()
    month_list = report_months(end_date, months)
    start_date = month_list[0]

    # What pulled from savings: moves out of every tagged envelope in the
    # window, a since-deleted one included (the move happened), named on
    # both sides. The same rows the wishlist reads for its envelopes.
    moves = await BudgetMoveRepository(session).outflows_from(
        budget_id, list(savings_cat_ids), start_date, end_date
    )
    every_category = await CategoryRepository(session).get_all(budget_id, include_archived=True)
    all_names = {c.id: c.name for c in every_category}
    shaped = shape_drains(moves, all_names)
    drains = {
        "total": drains_total(shaped),
        "moves": [d.__dict__ for d in shaped],
    }

    # Get category info and current balances
    cat_info_q = (
        select(
            Category.id,
            Category.name,
            CategoryGroup.name.label("group_name"),
        )
        .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
        .where(
            Category.id.in_(savings_cat_ids),
            # A tag outlives the category it was on. Without these the
            # report drew a row for a soft-deleted envelope, gave it the
            # assignments it once held as a "balance", and counted it in
            # category_count. SPENT_ENVELOPE is the wrong rule here: this
            # is a question about where money IS, not where it went.
            BUDGETED_ENVELOPE,
        )
    )
    cat_info_rows = (await session.execute(cat_info_q)).all()
    cat_info = {str(r.id): {"name": r.name, "group_name": r.group_name} for r in cat_info_rows}
    # Everything below walks only the envelopes that survived that filter.
    savings_cat_ids = [c for c in savings_cat_ids if str(c) in cat_info]

    # Available from the Budget page's own walk (`envelope_series`), never
    # a copy of it. This method once kept a running total — carrying an
    # overspend forward forever where the walk floors it between months —
    # and then a re-assembly that skipped the card correction, so a card
    # charge refunded to the envelope read $100 here and $0 on the page.
    # Assignments go unbounded below: a pre-window overspend is floored
    # where it happened. On an imported budget the months before the
    # import are walked back from YNAB's figure; an envelope whose history
    # cannot reproduce it starts late, and `unrecovered` says so.
    from igab.guide.detection import budget_service_from

    series = await budget_service_from(session).envelope_series(
        budget_id, list(savings_cat_ids), month_list
    )
    categories: list[SavingsCategory] = []
    unrecovered: list[dict] = []
    for cid in savings_cat_ids:
        info, s = cat_info[str(cid)], series[cid]
        if s.unrecovered_through is not None:
            unrecovered.append(
                {
                    "category_id": str(cid),
                    "category_name": info["name"],
                    "starts_from": add_months(s.unrecovered_through, 1),
                }
            )
        categories.append(
            {
                "category_id": str(cid),
                "category_name": info["name"],
                "group_name": info["group_name"],
                "monthly_balances": s.available,
                "current_balance": s.latest(),
                "target_balance": None,  # Could fetch from category targets
                "total_inflow": sum((a for a in s.assigned if a > 0), Decimal("0")),
            }
        )

    # Sort by current balance descending
    categories.sort(key=lambda x: x["current_balance"], reverse=True)

    # Summary
    total_balance = sum((c["current_balance"] for c in categories), Decimal("0"))
    total_inflow = sum((c["total_inflow"] for c in categories), Decimal("0"))
    # Every month in the window, the one in progress included — a
    # deliberate difference from the spending averages, which divide by
    # COMPLETE months (`domain.dates.complete_month_window`).
    #
    # Inflow here is ASSIGNED money, and assigning is a monthly act rather
    # than something that accrues by the day: an envelope funded on the
    # 1st has this month's whole inflow on record. Excluding the running
    # month would understate a household that has already budgeted it.
    avg_monthly = total_inflow / len(month_list) if month_list else Decimal("0")

    return {
        "categories": categories,
        "summary": {
            "total_balance": total_balance,
            "total_inflow": total_inflow,
            "avg_monthly_inflow": quantize_cents(avg_monthly),
            "category_count": len(categories),
        },
        "months": month_list,
        "drains": drains,
        "unrecovered": unrecovered,
    }
