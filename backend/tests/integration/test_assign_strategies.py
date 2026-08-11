"""Assign strategies (TBA hero dropdown): totals, previews, and apply.

The service promises three-way consistency — the dollar amount on a menu
row, the preview modal's table, and the applied result all come from the
same builder against live balances. Apply routes every delta through
move_money, so each bulk assign lands in the budget_moves audit trail and
conserves money by construction.
"""

import uuid
from datetime import date
from decimal import Decimal

from igab.repositories.target_repo import TargetRepository
from igab.services.assign_service import ASSIGN_STRATEGIES, AssignService
from igab.services.target_service import TargetService

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


def make_assign(db_session, services) -> AssignService:
    target_repo = TargetRepository(db_session)
    return AssignService(
        services.budgets,
        target_repo,
        TargetService(target_repo),
        services.category_repo,
        services.category_group_repo,
    )


async def _history_setup(db_session):
    """Two eligible categories with May/June history, viewed from July.

    Checking: +150 May, +500 June, +1000 July income; -50 May, -250/-80 June.
    Groceries: May assigned 100 spent 50; June assigned 300 spent 250; July assigned 100.
    Dining:    June assigned 120 spent 80; July assigned 0.

    July balances → Groceries available 200, Dining available 40, TBA 1030.
    History → Groceries last assigned 300 / spent 250, avg 200 / 150 (n=2);
              Dining   last assigned 120 / spent  80, avg 120 /  80 (n=1).
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

    await create_transaction(
        db_session, budget, checking, "150.00", date(2026, 5, 1), category=income_cat
    )
    await create_transaction(
        db_session, budget, checking, "500.00", date(2026, 6, 1), category=income_cat
    )
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=income_cat
    )
    await create_transaction(
        db_session, budget, checking, "-50.00", date(2026, 5, 10), category=groceries
    )
    await create_transaction(
        db_session, budget, checking, "-250.00", date(2026, 6, 10), category=groceries
    )
    await create_transaction(
        db_session, budget, checking, "-80.00", date(2026, 6, 12), category=dining
    )
    await services.budgets.set_assignment(budget.id, groceries.id, date(2026, 5, 1), Decimal("100.00"))
    await services.budgets.set_assignment(budget.id, groceries.id, PREV_MONTH, Decimal("300.00"))
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("100.00"))
    await services.budgets.set_assignment(budget.id, dining.id, PREV_MONTH, Decimal("120.00"))

    return services, budget, checking, groceries, dining


EXPECTED_HISTORY = {
    # strategy: (groceries_new, dining_new, to_assign, to_return, total_amount)
    "last_month_assigned": ("300.00", "120.00", "320.00", "0", "420.00"),
    "last_month_spent": ("250.00", "80.00", "230.00", "0", "330.00"),
    "average_assigned": ("200.00", "120.00", "220.00", "0", "320.00"),
    "average_spent": ("150.00", "80.00", "130.00", "0", "230.00"),
}


async def test_history_strategy_previews_hit_exact_values(db_session):
    services, budget, *_ = await _history_setup(db_session)
    assign = make_assign(db_session, services)

    for strategy, (g_new, d_new, to_assign, to_return, total) in EXPECTED_HISTORY.items():
        preview = await assign.preview(budget.id, MONTH, strategy)
        by_name = {i.category_name: i for i in preview.items}
        assert by_name["Groceries"].new_assigned == Decimal(g_new), strategy
        assert by_name["Dining"].new_assigned == Decimal(d_new), strategy
        assert preview.to_assign == Decimal(to_assign), strategy
        assert preview.to_return == Decimal(to_return), strategy
        assert preview.total_amount == Decimal(total), strategy
        assert preview.tba_before == Decimal("1030.00"), strategy
        assert preview.tba_after == Decimal("1030.00") - Decimal(to_assign), strategy


async def test_reset_available_and_reset_assigned_previews(db_session):
    services, budget, *_ = await _history_setup(db_session)
    assign = make_assign(db_session, services)

    reset_avail = await assign.preview(budget.id, MONTH, "reset_available")
    by_name = {i.category_name: i for i in reset_avail.items}
    # Groceries: assigned 100, available 200 → new assigned -100
    assert by_name["Groceries"].new_assigned == Decimal("-100.00")
    assert by_name["Groceries"].delta == Decimal("-200.00")
    # Dining: assigned 0, available 40 → new assigned -40
    assert by_name["Dining"].new_assigned == Decimal("-40.00")
    assert reset_avail.to_return == Decimal("240.00")
    assert reset_avail.tba_after == Decimal("1270.00")  # == account balance: all envelopes empty

    reset_assigned = await assign.preview(budget.id, MONTH, "reset_assigned")
    names = {i.category_name for i in reset_assigned.items}
    assert names == {"Groceries"}  # Dining's July assignment is already 0
    assert reset_assigned.items[0].new_assigned == Decimal("0")
    assert reset_assigned.to_return == Decimal("100.00")


async def test_menu_totals_preview_and_apply_agree(db_session):
    """Three-way consistency: the dropdown row == the modal == what applies."""
    services, budget, *_ = await _history_setup(db_session)
    assign = make_assign(db_session, services)

    totals = await assign.strategy_totals(budget.id, MONTH)
    assert [p.strategy for p in totals.strategies] == list(ASSIGN_STRATEGIES)
    assert totals.tba == Decimal("1030.00")

    strategy = "last_month_spent"
    total_row = next(p for p in totals.strategies if p.strategy == strategy)
    preview = await assign.preview(budget.id, MONTH, strategy)
    assert total_row.total_amount == preview.total_amount
    assert total_row.to_assign == preview.to_assign
    assert total_row.to_return == preview.to_return
    assert total_row.affected_count == preview.affected_count

    applied = await assign.apply(budget.id, MONTH, strategy)
    assert applied.to_assign == preview.to_assign
    assert applied.to_return == preview.to_return
    assert applied.affected_count == preview.affected_count

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    assert summary.to_be_assigned == preview.tba_after
    await assert_financial_invariants(db_session, budget.id)


async def test_set_strategy_returns_money_when_below_current(db_session):
    """Setting assigned below current sends the difference back to TBA."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    x = await create_category(db_session, budget, everyday, "X")
    y = await create_category(db_session, budget, everyday, "Y")
    await create_transaction(
        db_session, budget, checking, "500.00", date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, x.id, PREV_MONTH, Decimal("50.00"))
    await services.budgets.set_assignment(budget.id, y.id, PREV_MONTH, Decimal("100.00"))
    await services.budgets.set_assignment(budget.id, x.id, MONTH, Decimal("200.00"))
    assign = make_assign(db_session, services)

    applied = await assign.apply(budget.id, MONTH, "last_month_assigned")

    assert applied.to_return == Decimal("150.00")  # X: 200 → 50
    assert applied.to_assign == Decimal("100.00")  # Y: 0 → 100
    assert applied.affected_count == 2

    # Audit trail: X→TBA 150, TBA→Y 100
    moves = await services.budgets.get_move_history(budget.id, MONTH)
    assert len(moves) == 2
    directions = {
        (m.from_category_id, m.to_category_id): m.amount for m in moves
    }
    assert directions[(x.id, None)] == Decimal("150.00")
    assert directions[(None, y.id)] == Decimal("100.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_set_strategy_may_over_assign_into_negative_tba(db_session):
    """YNAB parity: history strategies may push TBA negative; no clamp."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    dining = await create_category(db_session, budget, everyday, "Dining")
    # June: fully assigned and fully spent (no carryover). July: only 100 income.
    await create_transaction(
        db_session, budget, checking, "500.00", date(2026, 6, 1), category=income_cat
    )
    await create_transaction(
        db_session, budget, checking, "-500.00", date(2026, 6, 15), category=dining
    )
    await services.budgets.set_assignment(budget.id, dining.id, PREV_MONTH, Decimal("500.00"))
    await create_transaction(
        db_session, budget, checking, "100.00", date(2026, 7, 2), category=income_cat
    )
    assign = make_assign(db_session, services)

    preview = await assign.preview(budget.id, MONTH, "last_month_assigned")
    assert preview.tba_before == Decimal("100.00")
    assert preview.to_assign == Decimal("500.00")
    assert preview.tba_after == Decimal("-400.00")

    applied = await assign.apply(budget.id, MONTH, "last_month_assigned")
    assert applied.tba_after == Decimal("-400.00")
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    assert summary.to_be_assigned == Decimal("-400.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_reset_available_apply_exact_and_idempotent(db_session):
    services, budget, checking, groceries, dining = await _history_setup(db_session)
    assign = make_assign(db_session, services)

    applied = await assign.apply(budget.id, MONTH, "reset_available")
    assert applied.to_return == Decimal("240.00")

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[groceries.id].available == Decimal("0")
    assert by_cat[dining.id].available == Decimal("0")
    assert summary.to_be_assigned == Decimal("1270.00")

    again = await assign.apply(budget.id, MONTH, "reset_available")
    assert again.affected_count == 0
    assert again.to_return == Decimal("0")
    await assert_financial_invariants(db_session, budget.id)


async def test_reset_available_leaves_overspent_categories_alone(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    funded = await create_category(db_session, budget, everyday, "Funded")
    overspent = await create_category(db_session, budget, everyday, "Overspent")
    await create_transaction(
        db_session, budget, checking, "300.00", date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, funded.id, MONTH, Decimal("100.00"))
    await services.budgets.set_assignment(budget.id, overspent.id, MONTH, Decimal("50.00"))
    await create_transaction(
        db_session, budget, checking, "-80.00", date(2026, 7, 10), category=overspent
    )
    assign = make_assign(db_session, services)

    applied = await assign.apply(budget.id, MONTH, "reset_available")

    assert applied.affected_count == 1
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[funded.id].available == Decimal("0")
    assert by_cat[overspent.id].available == Decimal("-30.00"), "overspend untouched"
    assert by_cat[overspent.id].assigned == Decimal("50.00")


async def test_reset_assigned_pulls_negative_assignment_from_tba(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    negative = await create_category(db_session, budget, everyday, "Negative")
    await create_transaction(
        db_session, budget, checking, "100.00", date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, negative.id, MONTH, Decimal("-25.00"))
    assign = make_assign(db_session, services)

    preview = await assign.preview(budget.id, MONTH, "reset_assigned")
    assert len(preview.items) == 1
    assert preview.items[0].delta == Decimal("25.00")
    assert preview.to_assign == Decimal("25.00")

    await assign.apply(budget.id, MONTH, "reset_assigned")
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[negative.id].assigned == Decimal("0")
    await assert_financial_invariants(db_session, budget.id)


async def test_system_and_hidden_categories_are_excluded(db_session):
    services, budget, checking, groceries, dining = await _history_setup(db_session)
    # Hide dining (it has June history that would otherwise re-fund it) and
    # give the system Inflow category a June assignment.
    dining.is_hidden = True
    categories = await services.category_repo.get_all(budget.id, include_hidden=True)
    inflow = next(c for c in categories if c.name == "Inflow")
    await services.budgets.set_assignment(budget.id, inflow.id, PREV_MONTH, Decimal("999.00"))
    await db_session.flush()
    assign = make_assign(db_session, services)

    for strategy in ASSIGN_STRATEGIES:
        preview = await assign.preview(budget.id, MONTH, strategy)
        names = {i.category_name for i in preview.items}
        assert "Inflow" not in names, strategy
        assert "Dining" not in names, strategy


async def _underfunded_setup(db_session, *, income: str):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    dining = await create_category(db_session, budget, everyday, "Dining")
    if Decimal(income) != 0:
        await create_transaction(
            db_session, budget, checking, income, date(2026, 7, 2), category=income_cat
        )
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("100.00"))
    target_service = TargetService(TargetRepository(db_session))
    await target_service.upsert(
        category_id=groceries.id, target_type="monthly_funding", target_amount=Decimal("500.00")
    )
    await target_service.upsert(
        category_id=dining.id, target_type="monthly_funding", target_amount=Decimal("100.00")
    )
    return services, budget, groceries, dining


async def test_underfunded_full_funding(db_session):
    services, budget, groceries, dining = await _underfunded_setup(db_session, income="1000.00")
    assign = make_assign(db_session, services)

    preview = await assign.preview(budget.id, MONTH, "underfunded")
    by_name = {i.category_name: i for i in preview.items}
    assert by_name["Groceries"].delta == Decimal("400.00")
    assert by_name["Dining"].delta == Decimal("100.00")
    assert preview.total_needed == Decimal("500.00")
    assert preview.to_assign == Decimal("500.00")
    assert preview.total_amount == Decimal("500.00")

    await assign.apply(budget.id, MONTH, "underfunded")
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[groceries.id].assigned == Decimal("500.00")
    assert by_cat[dining.id].assigned == Decimal("100.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_underfunded_clamps_proportionally_when_tba_short(db_session):
    services, budget, groceries, dining = await _underfunded_setup(db_session, income="300.00")
    assign = make_assign(db_session, services)

    preview = await assign.preview(budget.id, MONTH, "underfunded")
    # TBA 200 vs 500 needed → 40% each: 160 / 40
    by_name = {i.category_name: i for i in preview.items}
    assert preview.tba_before == Decimal("200.00")
    assert by_name["Groceries"].delta == Decimal("160.00")
    assert by_name["Dining"].delta == Decimal("40.00")
    assert preview.to_assign == Decimal("200.00")
    assert preview.total_needed == Decimal("500.00"), "reported unclamped"
    assert preview.tba_after == Decimal("0.00")


async def test_underfunded_with_no_tba_proposes_nothing(db_session):
    services, budget, groceries, dining = await _underfunded_setup(db_session, income="0")
    assign = make_assign(db_session, services)

    preview = await assign.preview(budget.id, MONTH, "underfunded")
    # TBA is -100 (assigned with no income): nothing assignable, need still shown
    assert preview.to_assign == Decimal("0")
    assert preview.affected_count == 0
    assert preview.total_needed == Decimal("500.00")
    assert {i.delta for i in preview.items} == {Decimal("0")}

    applied = await assign.apply(budget.id, MONTH, "underfunded")
    assert applied.affected_count == 0
    moves = await services.budgets.get_move_history(budget.id, MONTH)
    assert moves == []


async def test_underfunded_preview_via_api_pins_values(api_client, db_session):
    """API-level underfunded preview pins the fill-targets math exactly.

    (Numeric parity with the legacy /auto-assign/preview endpoint was
    verified before that endpoint was removed; these are the same numbers.)
    """
    services = make_services(db_session)
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    dining = await create_category(db_session, budget, everyday, "Dining")
    await create_transaction(
        db_session, budget, checking, "300.00", date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("100.00"))
    target_service = TargetService(TargetRepository(db_session))
    await target_service.upsert(
        category_id=groceries.id, target_type="monthly_funding", target_amount=Decimal("500.00")
    )
    await target_service.upsert(
        category_id=dining.id, target_type="monthly_funding", target_amount=Decimal("100.00")
    )

    resp = await api_client.get(
        f"/api/v1/{budget.id}/assign/preview",
        params={"month": "2026-07-01", "strategy": "underfunded"},
    )
    assert resp.status_code == 200
    body = resp.json()

    items = {i["category_name"]: i for i in body["items"]}
    # TBA 200 vs 500 needed → proportional: 160 / 40
    assert Decimal(str(items["Groceries"]["delta"])) == Decimal("160.00")
    assert Decimal(str(items["Groceries"]["new_assigned"])) == Decimal("260.00")
    assert Decimal(str(items["Dining"]["delta"])) == Decimal("40.00")
    assert Decimal(str(body["to_assign"])) == Decimal("200.00")
    assert Decimal(str(body["total_needed"])) == Decimal("500.00")
    assert Decimal(str(body["tba_after"])) == Decimal("0.00")


async def test_apply_into_prior_month(db_session):
    services, budget, checking, groceries, dining = await _history_setup(db_session)
    assign = make_assign(db_session, services)

    applied = await assign.apply(budget.id, PREV_MONTH, "reset_assigned")

    assert applied.affected_count == 2  # June: Groceries 300, Dining 120
    assert applied.to_return == Decimal("420.00")
    june = await services.budgets.get_budget_summary(budget.id, PREV_MONTH)
    by_cat = {b.category_id: b for b in june.category_balances}
    assert by_cat[groceries.id].assigned == Decimal("0")
    assert by_cat[dining.id].assigned == Decimal("0")
    moves = await services.budgets.get_move_history(budget.id, PREV_MONTH)
    assert len(moves) == 2
    await assert_financial_invariants(db_session, budget.id)


async def test_api_flow_totals_preview_apply(api_client, db_session):
    services = make_services(db_session)
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    await create_transaction(
        db_session, budget, checking, "800.00", date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, groceries.id, PREV_MONTH, Decimal("240.00"))

    totals = await api_client.get(
        f"/api/v1/{budget.id}/assign/strategies", params={"month": "2026-07-01"}
    )
    assert totals.status_code == 200
    body = totals.json()
    # June's unspent 240 carries into July's available, so TBA = 800 - 240
    assert Decimal(str(body["tba"])) == Decimal("560.00")
    row = next(s for s in body["strategies"] if s["strategy"] == "last_month_assigned")
    assert Decimal(str(row["to_assign"])) == Decimal("240.00")
    assert row["affected_count"] == 1

    apply_resp = await api_client.post(
        f"/api/v1/{budget.id}/assign/apply",
        json={"month": "2026-07-01", "strategy": "last_month_assigned"},
    )
    assert apply_resp.status_code == 200
    applied = apply_resp.json()
    assert Decimal(str(applied["to_assign"])) == Decimal("240.00")
    assert applied["categories_changed"] == 1
    assert Decimal(str(applied["tba_after"])) == Decimal("320.00")

    moves = await api_client.get(
        f"/api/v1/{budget.id}/budget/moves", params={"month": "2026-07-01"}
    )
    assert len(moves.json()) == 1


async def test_unknown_strategy_is_422(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    preview = await api_client.get(
        f"/api/v1/{budget.id}/assign/preview",
        params={"month": "2026-07-01", "strategy": "bogus"},
    )
    assert preview.status_code == 422

    apply_resp = await api_client.post(
        f"/api/v1/{budget.id}/assign/apply",
        json={"month": "2026-07-01", "strategy": "bogus"},
    )
    assert apply_resp.status_code == 422


async def test_ownership_404_on_all_routes(api_client, db_session):
    stranger = await create_user(db_session)
    other_budget = await create_budget(db_session, stranger)

    for method, url, kwargs in [
        ("get", f"/api/v1/{other_budget.id}/assign/strategies", {"params": {"month": "2026-07-01"}}),
        (
            "get",
            f"/api/v1/{other_budget.id}/assign/preview",
            {"params": {"month": "2026-07-01", "strategy": "reset_assigned"}},
        ),
        (
            "post",
            f"/api/v1/{other_budget.id}/assign/apply",
            {"json": {"month": "2026-07-01", "strategy": "reset_assigned"}},
        ),
    ]:
        resp = await getattr(api_client, method)(url, **kwargs)
        assert resp.status_code == 404, url

    missing = uuid.uuid4()
    resp = await api_client.get(
        f"/api/v1/{missing}/assign/strategies", params={"month": "2026-07-01"}
    )
    assert resp.status_code == 404


# ─── Reduce Overfunding ──────────────────────────────────────────────────────


async def _overfunded_setup(db_session):
    """Four categories exercising every reduce_overfunded eligibility case.

    Income 1000. Groceries target 200 assigned 350 (overfunded), Dining
    target 100 assigned 100 (exactly at target), Fun no target assigned 50,
    Rent target 100 assigned 150 with 400 spent (overfunded AND overspent —
    available is deeply negative but assigned still exceeds the target).
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
    rent = await create_category(db_session, budget, everyday, "Rent")

    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=income_cat
    )
    await create_transaction(
        db_session, budget, checking, "-400.00", date(2026, 7, 5), category=rent
    )
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("350.00"))
    await services.budgets.set_assignment(budget.id, dining.id, MONTH, Decimal("100.00"))
    await services.budgets.set_assignment(budget.id, fun.id, MONTH, Decimal("50.00"))
    await services.budgets.set_assignment(budget.id, rent.id, MONTH, Decimal("150.00"))

    target_service = TargetService(TargetRepository(db_session))
    await target_service.upsert(
        category_id=groceries.id, target_type="monthly_funding", target_amount=Decimal("200.00")
    )
    await target_service.upsert(
        category_id=dining.id, target_type="monthly_funding", target_amount=Decimal("100.00")
    )
    await target_service.upsert(
        category_id=rent.id, target_type="monthly_funding", target_amount=Decimal("100.00")
    )
    return services, budget, groceries, dining, fun, rent


async def test_reduce_overfunded_preview_exact_values(db_session):
    services, budget, *_ = await _overfunded_setup(db_session)
    assign = make_assign(db_session, services)

    preview = await assign.preview(budget.id, MONTH, "reduce_overfunded")
    by_name = {i.category_name: i for i in preview.items}

    # Only categories assigned beyond their target appear; at-target and
    # target-less categories are untouched.
    assert set(by_name) == {"Groceries", "Rent"}
    assert by_name["Groceries"].delta == Decimal("-150.00")
    assert by_name["Groceries"].new_assigned == Decimal("200.00")
    # Overspent + overfunded: available is -250 but assigned 150 > target 100
    assert by_name["Rent"].delta == Decimal("-50.00")
    assert by_name["Rent"].new_assigned == Decimal("100.00")

    assert preview.to_assign == Decimal("0")
    assert preview.to_return == Decimal("200.00")
    assert preview.total_amount == Decimal("200.00")  # net returned to TBA
    assert preview.affected_count == 2
    # TBA 1000 - 650 assigned = 350; excess of 200 comes back
    assert preview.tba_before == Decimal("350.00")
    assert preview.tba_after == Decimal("550.00")


async def test_reduce_overfunded_apply_exact_and_idempotent(db_session):
    services, budget, groceries, dining, fun, rent = await _overfunded_setup(db_session)
    assign = make_assign(db_session, services)

    applied = await assign.apply(budget.id, MONTH, "reduce_overfunded")
    assert applied.to_return == Decimal("200.00")

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[groceries.id].assigned == Decimal("200.00")
    assert by_cat[rent.id].assigned == Decimal("100.00")
    assert by_cat[dining.id].assigned == Decimal("100.00")
    assert by_cat[fun.id].assigned == Decimal("50.00")
    assert summary.to_be_assigned == Decimal("550.00")
    moves = await services.budgets.get_move_history(budget.id, MONTH)
    assert len(moves) == 2
    await assert_financial_invariants(db_session, budget.id)

    # Everything now sits at its target: a second apply moves nothing.
    again = await assign.apply(budget.id, MONTH, "reduce_overfunded")
    assert again.affected_count == 0
    moves = await services.budgets.get_move_history(budget.id, MONTH)
    assert len(moves) == 2


async def test_reduce_overfunded_nothing_over_target_is_noop(db_session):
    """Underfunded and exactly-funded categories produce an empty preview."""
    services, budget, groceries, dining = await _underfunded_setup(db_session, income="1000.00")
    assign = make_assign(db_session, services)

    preview = await assign.preview(budget.id, MONTH, "reduce_overfunded")
    assert preview.items == []
    assert preview.affected_count == 0
    assert preview.tba_after == preview.tba_before
