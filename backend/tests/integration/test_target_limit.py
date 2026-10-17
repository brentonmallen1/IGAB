"""A monthly target with a stop: "$100 a month, stop at $1,000".

Served end to end: the month endpoint's pill, Fill Underfunded, Target
amount and Reduce Overfunded all read `TargetService` with the month's served
assigned, activity and available, and the stop is measured from what the
month carried in. The pure arithmetic is pinned in
tests/unit/test_target_service.py (`TestTargetLimit`); these say every
caller hands it the same three figures.

Amounts are invented and round: a $100 rate toward a $1,000 stop.
"""

from datetime import date
from decimal import Decimal

from igab.repositories.target_repo import TargetRepository
from igab.services.target_service import TargetService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    make_services,
)
from .invariants import assert_financial_invariants
from .test_assign_strategies import make_assign

PREV = date(2026, 7, 1)
MONTH = date(2026, 8, 1)
D = Decimal


async def _world(db_session, user):
    services = make_services(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income = await create_category(db_session, budget, income_group, "Inflow")
    await create_transaction(db_session, budget, checking, "5000.00", PREV, category=income)
    group = await create_category_group(db_session, budget, "Buffers")
    return services, budget, checking, group


async def _capped(db_session, budget, group, name, *, carried_in, assigned="0", spent=None):
    """A $100/mo, stop-at-$1,000 envelope that carries `carried_in` into
    MONTH (assigned in PREV) and is assigned `assigned` in MONTH."""
    services = make_services(db_session)
    category = await create_category(db_session, budget, group, name)
    await TargetService(TargetRepository(db_session)).upsert(
        category.id, "monthly_funding", D("100.00"), target_limit=D("1000.00")
    )
    if D(carried_in):
        await services.budgets.set_assignment(budget.id, category.id, PREV, D(carried_in))
    if D(assigned):
        await services.budgets.set_assignment(budget.id, category.id, MONTH, D(assigned))
    return category


async def _month(api_client, budget):
    resp = await api_client.get(f"/api/v1/{budget.id}/months/{MONTH.isoformat()}")
    assert resp.status_code == 200, resp.text
    return {b["category_id"]: b for b in resp.json()["category_balances"]}


class TestTheServedVerdict:
    async def test_the_month_endpoint_measures_from_what_was_carried_in(
        self, db_session, api_client
    ):
        services, budget, checking, group = await _world(db_session, api_client.test_user)
        short = await _capped(db_session, budget, group, "Short", carried_in="500.00")
        close = await _capped(db_session, budget, group, "Close", carried_in="960.00")
        full = await _capped(db_session, budget, group, "Full", carried_in="1000.00")
        over = await _capped(
            db_session, budget, group, "Over", carried_in="900.00", assigned="300.00"
        )
        # Carried in at the stop, then spent 300 this month: still funded —
        # spending does not reopen a month's ask.
        spent = await _capped(db_session, budget, group, "Spent", carried_in="1000.00")
        await create_transaction(db_session, budget, checking, "-300.00", MONTH, category=spent)

        rows = await _month(api_client, budget)

        def row(c):
            r = rows[str(c.id)]
            return r["target_status"], D(str(r["needed_this_month"])), D(str(r["target_assigned"]))

        assert row(short) == ("underfunded", D("100.00"), D("100.00"))
        assert row(close) == ("underfunded", D("40.00"), D("40.00"))
        assert row(full) == ("funded", D("0"), D("0"))
        # 1,200 against the 1,000 stop: overfunded, and Target amount brings
        # it back to the stop — 100 assigned, not 0.
        assert row(over) == ("overfunded", D("0"), D("100.00"))
        assert row(spent) == ("funded", D("0"), D("0"))

    async def test_the_target_endpoint_serves_the_stop(self, db_session, api_client):
        services, budget, checking, group = await _world(db_session, api_client.test_user)
        category = await create_category(db_session, budget, group, "Buffer")
        resp = await api_client.post(
            f"/api/v1/categories/{category.id}/target",
            json={"target_type": "monthly_funding", "target_amount": "100", "target_limit": "1000"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["target_limit"] == 1000.0
        listed = (await api_client.get(f"/api/v1/{budget.id}/targets")).json()
        assert [t["target_limit"] for t in listed] == [1000.0]

    async def test_a_stop_on_a_savings_balance_is_refused_in_words(self, db_session, api_client):
        services, budget, checking, group = await _world(db_session, api_client.test_user)
        category = await create_category(db_session, budget, group, "Goal")
        url = f"/api/v1/categories/{category.id}/target"
        resp = await api_client.post(
            url,
            json={"target_type": "savings_balance", "target_amount": "100", "target_limit": "50"},
        )
        assert resp.status_code in (400, 409, 422), resp.text
        assert "monthly or weekly" in resp.text
        resp = await api_client.post(
            url,
            json={"target_type": "monthly_funding", "target_amount": "100", "target_limit": "0"},
        )
        assert resp.status_code in (400, 409, 422), resp.text
        assert "more than zero" in resp.text


class TestTheStrategiesStopAtTheStop:
    async def test_fill_underfunded_moves_only_the_gap(self, db_session, api_client):
        services, budget, checking, group = await _world(db_session, api_client.test_user)
        close = await _capped(db_session, budget, group, "Close", carried_in="960.00")
        full = await _capped(db_session, budget, group, "Full", carried_in="1000.00")
        assign = make_assign(db_session, services)

        preview = await assign.preview(budget.id, MONTH, "underfunded")
        by_id = {i.category_id: i for i in preview.items}
        assert by_id[close.id].delta == D("40.00")
        assert full.id not in by_id

        await assign.apply(budget.id, MONTH, "underfunded")
        rows = await _month(api_client, budget)
        assert D(str(rows[str(close.id)]["available"])) == D("1000.00")
        assert rows[str(close.id)]["target_status"] == "funded"
        await assert_financial_invariants(db_session, budget.id)

    async def test_target_amount_and_reduce_overfunded_never_go_below_the_stop(
        self, db_session, api_client
    ):
        """Carried in 900, 300 assigned: 1,200. Without the stop, both would
        bring assigned down to the $100 rate and leave 1,000 — the same here
        by coincidence — so the second envelope is the one that tells: 1,200
        assigned from nothing would come down to 100 and leave 100."""
        services, budget, checking, group = await _world(db_session, api_client.test_user)
        topped = await _capped(
            db_session, budget, group, "Topped", carried_in="900.00", assigned="300.00"
        )
        lump = await _capped(db_session, budget, group, "Lump", carried_in="0", assigned="1200.00")
        assign = make_assign(db_session, services)

        for strategy in ("target_amount", "reduce_overfunded"):
            preview = await assign.preview(budget.id, MONTH, strategy)
            by_id = {i.category_id: i for i in preview.items}
            assert by_id[topped.id].new_assigned == D("100.00"), strategy
            assert by_id[lump.id].new_assigned == D("1000.00"), strategy

        await assign.apply(budget.id, MONTH, "reduce_overfunded")
        rows = await _month(api_client, budget)
        for c in (topped, lump):
            assert D(str(rows[str(c.id)]["available"])) == D("1000.00"), c.name
            assert rows[str(c.id)]["target_status"] == "funded", c.name
        await assert_financial_invariants(db_session, budget.id)

    async def test_money_on_its_way_to_the_stop_is_left_alone(self, db_session, api_client):
        services, budget, checking, group = await _world(db_session, api_client.test_user)
        ahead = await _capped(db_session, budget, group, "Ahead", carried_in="0", assigned="300.00")
        assign = make_assign(db_session, services)

        for strategy in ("underfunded", "target_amount", "reduce_overfunded"):
            preview = await assign.preview(budget.id, MONTH, strategy)
            assert ahead.id not in {i.category_id for i in preview.items}, strategy
        assert (await _month(api_client, budget))[str(ahead.id)]["target_status"] == "funded"
