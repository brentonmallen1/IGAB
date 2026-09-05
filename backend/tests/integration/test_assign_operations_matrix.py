"""Every money-moving operation on the TBA hero, against every budget shape.

Written after two of these shipped wrong in ways their own tests asserted as
correct:

- Cover Overspending withheld the card-ridden part of each red envelope, and
  a test named `..._offers_the_cash_part_and_not_the_credit_part` pinned it.
- Reduce Overfunding pulled $50 back out of an envelope holding $20, leaving
  it $30 in the red, and a test asserted that exact delta.

Both were example tests: fixture in, expected numbers out, expectations
written by the same reading that produced the bug. What neither could catch is
an operation whose *outcome* contradicts what the button claims — so this
suite asserts outcomes instead, over a matrix of budget shapes, and derives
almost nothing from the code under test.

    STATES × OPERATIONS, and for each pair:
      · money is conserved and every financial invariant still holds
      · the preview and the apply agree, to the cent
      · an operation that only RETURNS money never pushes an envelope red
      · an operation that claims to clear red, clears it
      · undo puts every assignment back

`may_push_red` is the one thing a human declares per operation, and it is the
question both bugs got wrong. Adding an operation without answering it fails
here rather than shipping unexamined.

Amounts are invented and round; the shapes are what matter.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from igab.repositories.target_repo import TargetRepository
from igab.services.assign_service import ASSIGN_STRATEGIES, AssignService
from igab.services.card_payment import ensure_payment_category
from igab.services.target_service import TargetService
from igab.services.undo_service import UndoService

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
PREV = date(2026, 6, 1)
D = Decimal


# ─── The operations, and the one claim each makes about red ──────────────────


@dataclass(frozen=True)
class Operation:
    name: str
    #: True when unfunding money already spent is the POINT of the operation:
    #: the history strategies set assigned to a past figure and Reset Assigned
    #: zeroes it, so an envelope that has spent more than that goes red. False
    #: means the operation claims to hand back surplus or add money, and an
    #: envelope it pushes red is a defect — the Reduce Overfunding bug.
    may_push_red: bool
    #: True only for Cover Overspending: with enough Ready to Assign, nothing
    #: is left red afterwards. The claim the whole dialog is named for.
    clears_red: bool = False


OPERATIONS: tuple[Operation, ...] = (
    Operation("cover_overspent", may_push_red=False, clears_red=True),
    Operation("underfunded", may_push_red=False),
    Operation("reduce_overfunded", may_push_red=False),
    Operation("reset_available", may_push_red=False),
    Operation("reset_assigned", may_push_red=True),
    Operation("last_month_assigned", may_push_red=True),
    Operation("last_month_spent", may_push_red=True),
    Operation("average_assigned", may_push_red=True),
    Operation("average_spent", may_push_red=True),
)


def test_every_strategy_is_in_the_matrix():
    """A new strategy joins this suite or fails here — the point is that no
    operation reaches the hero without someone answering `may_push_red`."""
    named = {op.name for op in OPERATIONS} - {"cover_overspent"}
    assert named == set(ASSIGN_STRATEGIES)


# ─── The budget shapes ───────────────────────────────────────────────────────


@dataclass
class Shape:
    """A budget, plus the envelope ids worth looking at."""

    services: object
    assign: AssignService
    budget: object
    categories: dict[str, uuid.UUID]


async def _base(db_session, *, with_card: bool = False):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    await create_transaction(
        db_session, budget, checking, "800.00", date(2026, 6, 2), category=inflow
    )
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=inflow
    )
    card = None
    if with_card:
        card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
        await ensure_payment_category(db_session, card)
    target_repo = TargetRepository(db_session)
    assign = AssignService(
        services.budgets,
        target_repo,
        TargetService(target_repo),
        services.category_repo,
        services.category_group_repo,
    )
    return services, budget, checking, everyday, card, assign


async def _target(db_session, category, amount: str) -> None:
    await TargetService(TargetRepository(db_session)).upsert(
        category_id=category.id, target_type="monthly_funding", target_amount=D(amount)
    )


async def shape_untouched(db_session) -> Shape:
    """Nothing assigned, nothing spent — every operation's no-op case."""
    services, budget, checking, group, _, assign = await _base(db_session)
    idle = await create_category(db_session, budget, group, "Idle")
    await db_session.flush()
    return Shape(services, assign, budget, {"Idle": idle.id})


async def shape_surplus(db_session) -> Shape:
    """Assigned 200, spent nothing, target 100 — genuinely overfunded."""
    services, budget, checking, group, _, assign = await _base(db_session)
    fun = await create_category(db_session, budget, group, "Fun")
    await services.budgets.set_assignment(budget.id, fun.id, MONTH, D("200.00"))
    await _target(db_session, fun, "100.00")
    await db_session.flush()
    return Shape(services, assign, budget, {"Fun": fun.id})


async def shape_spent_down(db_session) -> Shape:
    """Assigned 150, spent 130, target 100: over target, but only 20 is left.

    The Reduce Overfunding bug lived here.
    """
    services, budget, checking, group, _, assign = await _base(db_session)
    dining = await create_category(db_session, budget, group, "Dining")
    await services.budgets.set_assignment(budget.id, dining.id, MONTH, D("150.00"))
    await create_transaction(
        db_session, budget, checking, "-130.00", date(2026, 7, 10), category=dining
    )
    await _target(db_session, dining, "100.00")
    await db_session.flush()
    return Shape(services, assign, budget, {"Dining": dining.id})


async def shape_cash_overspent(db_session) -> Shape:
    """Assigned 100, spent 130 in cash — 30 red, none of it on a card."""
    services, budget, checking, group, _, assign = await _base(db_session)
    fuel = await create_category(db_session, budget, group, "Fuel")
    await services.budgets.set_assignment(budget.id, fuel.id, MONTH, D("100.00"))
    await create_transaction(
        db_session, budget, checking, "-130.00", date(2026, 7, 11), category=fuel
    )
    await db_session.flush()
    return Shape(services, assign, budget, {"Fuel": fuel.id})


async def shape_card_ridden(db_session) -> Shape:
    """Nothing assigned, 80 swiped on a card — red entirely on credit.

    Cover Overspending offered nothing at all here until 2026-09-05.
    """
    services, budget, checking, group, card, assign = await _base(db_session, with_card=True)
    groceries = await create_category(db_session, budget, group, "Groceries")
    await create_transaction(
        db_session, budget, card, "-80.00", date(2026, 7, 9), category=groceries
    )
    await db_session.flush()
    return Shape(services, assign, budget, {"Groceries": groceries.id})


async def shape_mixed_red(db_session) -> Shape:
    """Assigned 100; 130 spent in cash and 20 swiped on the card.

    30 cash-short, 20 ridden, 50 red. The shape both cover bugs turned on.
    """
    services, budget, checking, group, card, assign = await _base(db_session, with_card=True)
    groceries = await create_category(db_session, budget, group, "Groceries")
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, D("100.00"))
    await create_transaction(
        db_session, budget, checking, "-130.00", date(2026, 7, 8), category=groceries
    )
    await create_transaction(
        db_session, budget, card, "-20.00", date(2026, 7, 9), category=groceries
    )
    await db_session.flush()
    return Shape(services, assign, budget, {"Groceries": groceries.id})


async def shape_history(db_session) -> Shape:
    """June assigned 300 spent 250; July assigned 400 spent 380.

    Every history strategy has something to say, and each would unfund money
    already spent — the legitimate `may_push_red` case.
    """
    services, budget, checking, group, _, assign = await _base(db_session)
    dining = await create_category(db_session, budget, group, "Dining")
    await services.budgets.set_assignment(budget.id, dining.id, PREV, D("300.00"))
    await create_transaction(
        db_session, budget, checking, "-250.00", date(2026, 6, 10), category=dining
    )
    await services.budgets.set_assignment(budget.id, dining.id, MONTH, D("400.00"))
    await create_transaction(
        db_session, budget, checking, "-380.00", date(2026, 7, 10), category=dining
    )
    await db_session.flush()
    return Shape(services, assign, budget, {"Dining": dining.id})


async def shape_hidden_overspent(db_session) -> Shape:
    """A hidden envelope, overspent. Hidden rows still hold money and still
    take part in the TBA arithmetic, so every operation must see them."""
    services, budget, checking, group, _, assign = await _base(db_session)
    old = await create_category(db_session, budget, group, "Old Subscription")
    await services.budgets.set_assignment(budget.id, old.id, MONTH, D("20.00"))
    await create_transaction(
        db_session, budget, checking, "-70.00", date(2026, 7, 12), category=old
    )
    old.is_hidden = True
    await db_session.flush()
    return Shape(services, assign, budget, {"Old Subscription": old.id})


async def shape_many(db_session) -> Shape:
    """Four envelopes at once — surplus, spent-down, red, and untouched — so
    an operation is exercised where it must act on some rows and not others."""
    services, budget, checking, group, _, assign = await _base(db_session)
    surplus = await create_category(db_session, budget, group, "Surplus")
    spent = await create_category(db_session, budget, group, "Spent")
    red = await create_category(db_session, budget, group, "Red")
    idle = await create_category(db_session, budget, group, "Idle")
    await services.budgets.set_assignment(budget.id, surplus.id, MONTH, D("200.00"))
    await services.budgets.set_assignment(budget.id, spent.id, MONTH, D("150.00"))
    await services.budgets.set_assignment(budget.id, red.id, MONTH, D("50.00"))
    await create_transaction(
        db_session, budget, checking, "-130.00", date(2026, 7, 10), category=spent
    )
    await create_transaction(
        db_session, budget, checking, "-90.00", date(2026, 7, 11), category=red
    )
    for cat in (surplus, spent, red):
        await _target(db_session, cat, "100.00")
    await db_session.flush()
    return Shape(
        services,
        assign,
        budget,
        {"Surplus": surplus.id, "Spent": spent.id, "Red": red.id, "Idle": idle.id},
    )


SHAPES: dict[str, Callable] = {
    "untouched": shape_untouched,
    "surplus": shape_surplus,
    "spent-down": shape_spent_down,
    "cash-overspent": shape_cash_overspent,
    "card-ridden": shape_card_ridden,
    "mixed-red": shape_mixed_red,
    "history": shape_history,
    "hidden-overspent": shape_hidden_overspent,
    "many": shape_many,
}


# ─── Reading a budget's state ────────────────────────────────────────────────


@dataclass
class Snapshot:
    tba: Decimal
    assigned: dict[uuid.UUID, Decimal]
    available: dict[uuid.UUID, Decimal]
    red_total: Decimal

    def red(self) -> set[uuid.UUID]:
        return {cat for cat, value in self.available.items() if value < 0}


async def _snapshot(shape: Shape) -> Snapshot:
    summary = await shape.services.budgets.get_budget_summary(shape.budget.id, MONTH)
    rows = [b for b in summary.category_balances if not b.in_system_group]
    return Snapshot(
        tba=summary.to_be_assigned,
        assigned={b.category_id: b.assigned for b in rows},
        available={b.category_id: b.available for b in rows},
        red_total=summary.total_overspent,
    )


async def _run(shape: Shape, operation: str):
    """Preview an operation and apply it. Returns (preview, applied deltas)."""
    if operation == "cover_overspent":
        preview = await shape.services.budgets.cover_overspent_preview(shape.budget.id, MONTH)
        deltas = {i.category_id: i.proposed_addition for i in preview.items}
        await shape.services.budgets.cover_overspent_apply(
            shape.budget.id, MONTH, list(deltas.items())
        )
        return preview, deltas
    preview = await shape.assign.preview(shape.budget.id, MONTH, operation)
    deltas = {i.category_id: i.delta for i in preview.items}
    await shape.assign.apply(shape.budget.id, MONTH, operation)
    return preview, deltas


# ─── The matrix ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("shape_name", list(SHAPES))
@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.name)
async def test_operation_on_shape(db_session, shape_name: str, operation: Operation):
    shape = await SHAPES[shape_name](db_session)
    before = await _snapshot(shape)

    preview, deltas = await _run(shape, operation.name)
    await db_session.flush()
    after = await _snapshot(shape)

    # 1. The books still balance, on every axis the app has an opinion about.
    await assert_financial_invariants(db_session, shape.budget.id)

    # 2. Money is conserved between Ready to Assign and the envelopes: what
    #    left one arrived in the others, to the cent. An operation that fails
    #    this has invented or destroyed money.
    moved_into_envelopes = sum(
        (after.assigned[cat] - before.assigned.get(cat, Decimal("0")) for cat in after.assigned),
        Decimal("0"),
    )
    assert before.tba - after.tba == moved_into_envelopes, (
        f"{operation.name} on {shape_name}: TBA moved {before.tba - after.tba} "
        f"but envelopes took {moved_into_envelopes}"
    )

    # 3. The preview told the truth. Every row it named moved by exactly the
    #    delta it showed, and every row it did not name did not move.
    for cat, expected in deltas.items():
        actual = after.assigned[cat] - before.assigned.get(cat, Decimal("0"))
        assert actual == expected, (
            f"{operation.name} on {shape_name}: previewed {expected} for {cat}, applied {actual}"
        )
    for cat, assigned_before in before.assigned.items():
        if cat not in deltas:
            assert after.assigned[cat] == assigned_before, (
                f"{operation.name} on {shape_name}: moved {cat} without previewing it"
            )

    # 4. The claim each operation makes about red envelopes.
    newly_red = after.red() - before.red()
    if not operation.may_push_red:
        assert not newly_red, (
            f"{operation.name} on {shape_name} pushed {len(newly_red)} envelope(s) into the red — "
            "it hands money back or adds it, so it can only have returned money already spent"
        )
    # Deepening an existing red is the same defect wearing a different hat.
    if not operation.may_push_red:
        for cat in before.red():
            assert after.available[cat] >= before.available[cat], (
                f"{operation.name} on {shape_name} made {cat} more overspent"
            )

    if operation.clears_red and before.tba >= before.red_total:
        assert after.red() == set(), (
            f"{operation.name} on {shape_name} left {len(after.red())} envelope(s) red with "
            f"{before.tba} of Ready to Assign against {before.red_total} of red"
        )

    # 5. Nothing is ever assigned beyond what Ready to Assign held.
    if before.tba >= 0:
        assert after.tba >= 0 or operation.may_push_red, (
            f"{operation.name} on {shape_name} drove Ready to Assign to {after.tba}"
        )


@pytest.mark.parametrize("shape_name", list(SHAPES))
@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.name)
async def test_operation_undoes_completely(db_session, shape_name: str, operation: Operation):
    """Every one of these is offered with an undo toast. The undo has to put
    the budget back exactly — assignment by assignment, not approximately."""
    shape = await SHAPES[shape_name](db_session)
    before = await _snapshot(shape)

    _, deltas = await _run(shape, operation.name)
    await db_session.flush()
    if not deltas or all(d == 0 for d in deltas.values()):
        pytest.skip("nothing moved, nothing to undo")

    _, undone = await UndoService(db_session).undo_latest(shape.budget.id)
    assert undone.undone and not undone.skipped
    await db_session.flush()

    after = await _snapshot(shape)
    assert after.assigned == before.assigned
    assert after.available == before.available
    assert after.tba == before.tba
    await assert_financial_invariants(db_session, shape.budget.id)
