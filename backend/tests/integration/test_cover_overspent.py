"""Cover-overspent: distribute TBA onto overspent envelopes via preview/apply.

Apply routes every cover through move_money, so covers land in the
budget_moves audit trail as TBA → category and conserve money by
construction. Apply re-validates against fresh balances — a stale preview
can never over-assign.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_financial_invariants

MONTH = date(2026, 7, 1)
PREV_MONTH = date(2026, 6, 1)


async def _setup(db_session, *, income: str = "1000.00"):
    """Checking with income, groceries funded, dining and fun overspent.

    With income=1000: TBA 600, dining -60, fun -40 (full-cover scenario).
    With income=450:  TBA 50,  dining -60, fun -40 (partial-cover scenario).
    """
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    dining = await create_category(db_session, budget, everyday, "Dining")
    fun = await create_category(db_session, budget, everyday, "Fun")
    await create_transaction(
        db_session, budget, checking, income, date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("300.00"))
    await services.budgets.set_assignment(budget.id, dining.id, MONTH, Decimal("100.00"))
    await create_transaction(
        db_session, budget, checking, "-160.00", date(2026, 7, 10), category=dining
    )
    await create_transaction(
        db_session, budget, checking, "-40.00", date(2026, 7, 11), category=fun
    )
    return services, budget, checking, groceries, dining, fun


async def test_preview_full_cover(db_session):
    services, budget, *_ = await _setup(db_session)

    preview = await services.budgets.cover_overspent_preview(budget.id, MONTH)

    assert preview.total_overspent == Decimal("100.00")
    assert preview.total_addition == Decimal("100.00")
    assert preview.tba_before == Decimal("600.00")
    assert preview.tba_after == Decimal("500.00")
    by_name = {i.category_name: i for i in preview.items}
    assert by_name["Dining"].overspent == Decimal("60.00")
    assert by_name["Dining"].proposed_addition == Decimal("60.00")
    assert by_name["Dining"].remaining_after == Decimal("0.00")
    assert by_name["Fun"].proposed_addition == Decimal("40.00")


async def test_preview_partial_cover_sorted_by_proposed(db_session):
    services, budget, *_ = await _setup(db_session, income="450.00")

    preview = await services.budgets.cover_overspent_preview(budget.id, MONTH)

    # TBA 50 against 100 overspent → 50% coverage, largest proposal first
    assert preview.tba_before == Decimal("50.00")
    assert preview.total_addition == Decimal("50.00")
    assert [i.category_name for i in preview.items] == ["Dining", "Fun"]
    assert preview.items[0].proposed_addition == Decimal("30.00")
    assert preview.items[0].remaining_after == Decimal("30.00")
    assert preview.items[1].proposed_addition == Decimal("20.00")


async def test_preview_excludes_system_income_categories(db_session):
    """A spending transaction categorized into a system group must not appear
    as coverable overspending — system categories sit outside envelope math."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    misfiled = await create_category(db_session, budget, income_group, "Misfiled")
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=income_cat
    )
    await create_transaction(
        db_session, budget, checking, "-50.00", date(2026, 7, 5), category=misfiled
    )

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    preview = await services.budgets.cover_overspent_preview(budget.id, MONTH)

    assert summary.total_overspent == Decimal("0")
    assert preview.items == []
    assert preview.total_overspent == Decimal("0")


async def test_preview_includes_hidden_overspent_categories(db_session):
    """Hidden categories participate in TBA math, so leaving them out would
    leave TBA short after a 'full' cover."""
    services, budget, checking, groceries, dining, fun = await _setup(db_session)
    fun.is_archived = True
    await db_session.flush()

    preview = await services.budgets.cover_overspent_preview(budget.id, MONTH)

    assert {i.category_name for i in preview.items} == {"Dining", "Fun"}
    assert preview.total_overspent == Decimal("100.00")


async def test_apply_writes_budget_moves_audit_rows_from_tba(db_session):
    services, budget, checking, groceries, dining, fun = await _setup(db_session)
    preview = await services.budgets.cover_overspent_preview(budget.id, MONTH)

    await services.budgets.cover_overspent_apply(
        budget.id, MONTH, [(i.category_id, i.proposed_addition) for i in preview.items]
    )

    moves = await services.budgets.get_move_history(budget.id, MONTH)
    assert len(moves) == 2
    assert all(m.from_category_id is None for m in moves), "covers must draw from TBA"
    amounts = {m.to_category_id: m.amount for m in moves}
    assert amounts[dining.id] == Decimal("60.00")
    assert amounts[fun.id] == Decimal("40.00")


async def test_apply_then_preview_is_empty(db_session):
    services, budget, checking, groceries, dining, fun = await _setup(db_session)
    preview = await services.budgets.cover_overspent_preview(budget.id, MONTH)

    await services.budgets.cover_overspent_apply(
        budget.id, MONTH, [(i.category_id, i.proposed_addition) for i in preview.items]
    )

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[dining.id].available == Decimal("0")
    assert by_cat[fun.id].available == Decimal("0")
    assert summary.to_be_assigned == Decimal("500.00")
    assert summary.total_overspent == Decimal("0")

    again = await services.budgets.cover_overspent_preview(budget.id, MONTH)
    assert again.items == []
    assert again.total_addition == Decimal("0")


async def test_partial_apply_conserves_money(db_session):
    services, budget, checking, groceries, dining, fun = await _setup(db_session, income="450.00")
    preview = await services.budgets.cover_overspent_preview(budget.id, MONTH)

    await services.budgets.cover_overspent_apply(
        budget.id, MONTH, [(i.category_id, i.proposed_addition) for i in preview.items]
    )

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert summary.to_be_assigned == Decimal("0.00"), "partial cover drains TBA exactly"
    assert by_cat[dining.id].available == Decimal("-30.00")
    assert by_cat[fun.id].available == Decimal("-20.00")
    assert summary.total_overspent == Decimal("50.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_apply_rejects_stale_amount_exceeding_shortfall(db_session):
    services, budget, checking, groceries, dining, fun = await _setup(db_session)

    with pytest.raises(InvariantViolation, match="overspending"):
        await services.budgets.cover_overspent_apply(
            budget.id, MONTH, [(dining.id, Decimal("60.01"))]
        )

    # A category that is not overspent at all is equally stale
    with pytest.raises(InvariantViolation, match="overspending"):
        await services.budgets.cover_overspent_apply(
            budget.id, MONTH, [(groceries.id, Decimal("10.00"))]
        )


async def test_apply_rejects_sum_exceeding_tba(db_session):
    services, budget, checking, groceries, dining, fun = await _setup(db_session, income="450.00")

    # Individually valid shortfall amounts, but 60 + 40 > TBA of 50
    with pytest.raises(InvariantViolation, match="Ready to Assign"):
        await services.budgets.cover_overspent_apply(
            budget.id,
            MONTH,
            [(dining.id, Decimal("60.00")), (fun.id, Decimal("40.00"))],
        )

    # Nothing was applied — validation happens before any mutation
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    assert summary.to_be_assigned == Decimal("50.00")
    moves = await services.budgets.get_move_history(budget.id, MONTH)
    assert moves == []


async def test_prior_month_overspend_not_double_covered(db_session):
    """June overspending is absorbed by TBA at the month boundary (carryover
    floors at zero) — July's preview must not offer to cover it again."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    dining = await create_category(db_session, budget, everyday, "Dining")
    await create_transaction(
        db_session, budget, checking, "500.00", date(2026, 6, 1), category=income_cat
    )
    await create_transaction(
        db_session, budget, checking, "-80.00", date(2026, 6, 15), category=dining
    )

    june = await services.budgets.cover_overspent_preview(budget.id, PREV_MONTH)
    assert june.total_overspent == Decimal("80.00")

    july = await services.budgets.cover_overspent_preview(budget.id, MONTH)
    assert july.items == []
    assert july.total_overspent == Decimal("0")


async def test_months_endpoint_total_overspent_matches_preview(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    dining = await create_category(db_session, budget, everyday, "Dining")
    await create_transaction(
        db_session, budget, checking, "200.00", date(2026, 7, 2), category=income_cat
    )
    await create_transaction(
        db_session, budget, checking, "-45.50", date(2026, 7, 10), category=dining
    )

    resp = await api_client.get(f"/api/v1/{budget.id}/months/2026-07-01")
    assert resp.status_code == 200
    month_data = resp.json()
    assert Decimal(str(month_data["total_overspent"])) == Decimal("45.50")

    resp = await api_client.get(
        f"/api/v1/{budget.id}/cover-overspent/preview", params={"month": "2026-07-01"}
    )
    assert resp.status_code == 200
    preview = resp.json()
    assert Decimal(str(preview["total_overspent"])) == Decimal("45.50")
    assert len(preview["items"]) == 1
    assert preview["items"][0]["category_name"] == "Dining"

    # Apply through the API and confirm the audit trail + rejection path
    resp = await api_client.post(
        f"/api/v1/{budget.id}/cover-overspent/apply",
        json={
            "month": "2026-07-01",
            "items": [
                {
                    "category_id": preview["items"][0]["category_id"],
                    "proposed_addition": preview["items"][0]["proposed_addition"],
                }
            ],
        },
    )
    assert resp.status_code == 200
    # The moves are one change-log batch, handed back so the client can undo it
    assert resp.json()["batch_id"]

    resp = await api_client.post(
        f"/api/v1/{budget.id}/cover-overspent/apply",
        json={
            "month": "2026-07-01",
            "items": [{"category_id": str(dining.id), "proposed_addition": "45.50"}],
        },
    )
    assert resp.status_code == 400, "re-applying a consumed preview must be rejected"
