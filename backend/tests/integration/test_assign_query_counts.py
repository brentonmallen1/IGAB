"""The assign buttons cost the same however many envelopes they touch.

Measured against the generated sample budget (seventy envelopes) before this
ratchet existed:

    inspector Assigned Last Month, all envelopes   737 statements
    inspector Target Amount, one envelope          227
    dropdown totals / any preview                  227
    dropdown Apply, a history strategy             588
    batch history                                  205

Every one of them was a loop over the envelopes — a history read per
category, a get-or-create-update-reselect per category, a budget move with
its own flush per category — so the count was a multiple of the envelope
count and the button got slower as the budget grew. They are now one pass
each. This suite builds the same budget at two sizes and requires the same
count at both: a cost that should be flat and starts to grow names itself
here (see `statement_counts.py` for why counts rather than timings).
"""

from datetime import date
from decimal import Decimal as D

import pytest

from igab.repositories.target_repo import TargetRepository
from igab.services.target_service import TargetService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
)
from .statement_counts import count_call

MONTH = date(2026, 7, 1)


async def _budget(db_session, api_client, envelopes: int):
    """`envelopes` categories, each with three months of history and a
    monthly target, and Ready to Assign to spare."""
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    group = await create_category_group(db_session, budget, "Everyday")
    await create_transaction(
        db_session, budget, checking, "90000.00", date(2026, 4, 1), category=inflow
    )
    targets = TargetService(TargetRepository(db_session))
    cats = []
    for i in range(envelopes):
        cat = await create_category(db_session, budget, group, f"Envelope {i}")
        cats.append(cat)
        for month in (4, 5, 6):
            await create_budget_assignment(db_session, budget, cat, date(2026, month, 1), "100")
            await create_transaction(
                db_session, budget, checking, "-60.00", date(2026, month, 5), category=cat
            )
        await targets.upsert(
            category_id=cat.id, target_type="monthly_funding", target_amount=D("150")
        )
    await db_session.flush()
    return budget, [str(c.id) for c in cats]


def _calls(budget, ids):
    """(name, method, path, kwargs) for every assign path the budget page uses."""
    b, m = budget.id, MONTH.isoformat()
    auto = f"/api/v1/{b}/categories/auto-assign"
    return [
        ("history batch", "POST", f"/api/v1/{b}/categories/history/batch",
         {"params": {"month": m}, "json": {"category_ids": ids}}),
        ("dropdown totals", "GET", f"/api/v1/{b}/assign/strategies", {"params": {"month": m}}),
        ("preview, history strategy", "GET", f"/api/v1/{b}/assign/preview",
         {"params": {"month": m, "strategy": "average_spent"}}),
        ("preview, target strategy", "GET", f"/api/v1/{b}/assign/preview",
         {"params": {"month": m, "strategy": "target_amount"}}),
        ("inspector Target Amount", "POST", auto,
         {"json": {"month": m, "action": "target_amount", "category_ids": ids}}),
        ("inspector Assigned Last Month", "POST", auto,
         {"json": {"month": m, "action": "last_month_assigned", "category_ids": ids}}),
        ("inspector Reset", "POST", auto,
         {"json": {"month": m, "action": "reset", "category_ids": ids}}),
        ("dropdown Apply, history strategy", "POST", f"/api/v1/{b}/assign/apply",
         {"json": {"month": m, "strategy": "average_assigned"}}),
        ("dropdown Apply, underfunded", "POST", f"/api/v1/{b}/assign/apply",
         {"json": {"month": m, "strategy": "underfunded"}}),
    ]  # fmt: skip


async def _counts(api_client, db_session, envelopes: int) -> dict[str, int]:
    budget, ids = await _budget(db_session, api_client, envelopes)
    counts = {}
    for name, method, path, kwargs in _calls(budget, ids):
        counter = await count_call(api_client, db_session, method, path, **kwargs)
        counts[name] = len(counter.statements)
    return counts


async def test_no_assign_path_costs_a_statement_per_envelope(api_client, db_session):
    small = await _counts(api_client, db_session, 3)
    large = await _counts(api_client, db_session, 12)
    grew = {name: (small[name], large[name]) for name in small if large[name] != small[name]}
    assert not grew, f"statement count grew with the envelope count (3 → 12): {grew}"


@pytest.mark.parametrize("ceiling", [40])
async def test_the_inspector_buttons_stay_cheap(api_client, db_session, ceiling):
    """Flat is the contract; this bounds what flat is, so a fixed cost that
    creeps up (a second summary per request, say) shows too. The summary the
    target and preview paths read is most of it."""
    counts = await _counts(api_client, db_session, 5)
    assert max(counts.values()) <= ceiling, counts
