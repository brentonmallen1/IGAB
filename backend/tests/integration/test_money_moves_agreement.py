"""The Guide's money explorer, held to what really happens.

`domain/money_moves.py` answers two questions about a move nobody made:

- **its class**, by handing `activity_class._rules` literal booleans
  (`leg_facts`). The rules cannot disagree with themselves, but the booleans
  can be wrong — a counterpart read as tracked when it is not — so here every
  leg is also written for real and classified by the shipped ACTIVITY_CLASS;
- **which budget figure moves**, which is prose about `BudgetService` and
  cannot be evaluated over literals at all. Here every move is booked into a
  budget in `ASSUMPTION`'s situation and the served terms must equal the
  month's actual deltas, exactly: no term missing, none extra.

Every shape pair crossed with every category kind the pair may carry, plus
every plain transaction. A combination the explorer offers and this file does
not build is a combination nobody checked.
"""

import itertools
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import Transaction
from igab.domain.activity_class import ACTIVITY_CLASS, ACTIVITY_REASON, apply_class_joins
from igab.domain.money_moves import (
    AccountShape,
    BudgetTerm,
    CategoryKind,
    Direction,
    LegRole,
    Move,
    MoveKind,
    category_role,
)
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.card_payment import ensure_payment_category
from igab.services.money_moves_service import MoneyMovesService
from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()
MONTH = TODAY.replace(day=1)
AMOUNT = Decimal("1000")

#: shape name -> (domain shape, how the factory builds one)
SHAPES: dict[str, tuple[AccountShape, dict]] = {
    "cash": (AccountShape(False, True), {"account_type": "checking", "on_budget": True}),
    "card": (AccountShape(True, True), {"account_type": "credit_card", "on_budget": True}),
    "saving": (
        AccountShape(False, False, True),
        {"account_type": "investment", "on_budget": False, "counts_as_savings": True},
    ),
    "keeping": (
        AccountShape(False, False, False),
        {"account_type": "other_asset", "on_budget": False, "counts_as_savings": False},
    ),
    "debt": (AccountShape(True, False), {"account_type": "loan", "on_budget": False}),
}


def _moves() -> list[tuple[str, Move]]:
    cases: list[tuple[str, Move]] = []
    for frm, to in itertools.product(SHAPES, SHAPES):
        for kind in CategoryKind:
            move = Move(MoveKind.TRANSFER, SHAPES[frm][0], AMOUNT, kind, to_account=SHAPES[to][0])
            if kind is not CategoryKind.NONE and category_role(move) is None:
                continue
            cases.append((f"{frm}->{to}:{kind.value}", move))
    for name, direction in itertools.product(SHAPES, Direction):
        for kind in CategoryKind:
            move = Move(MoveKind.TRANSACTION, SHAPES[name][0], AMOUNT, kind, direction=direction)
            if kind is not CategoryKind.NONE and category_role(move) is None:
                continue
            cases.append((f"{name}:{direction.value}:{kind.value}", move))
    return cases


MOVES = _moves()


async def _account(db_session, budget, name: str, label: str):
    account = await create_account(db_session, budget, label, **SHAPES[name][1])
    if SHAPES[name][0].is_card:
        await ensure_payment_category(db_session, account)
    return account


def _shape_name(shape: AccountShape) -> str:
    return next(name for name, (s, _) in SHAPES.items() if s == shape)


async def _snapshot(services, budget, envelope):
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    env = next(b for b in summary.category_balances if b.category_id == envelope.id)
    return {
        BudgetTerm.READY_TO_ASSIGN: summary.to_be_assigned,
        BudgetTerm.ENVELOPE: env.available,
        BudgetTerm.CARD_SET_ASIDE: sum((c.set_aside for c in summary.cards), Decimal("0")),
        BudgetTerm.CARD_UNCOVERED: sum((c.uncovered for c in summary.cards), Decimal("0")),
    }


@pytest.mark.parametrize(("name", "move"), MOVES, ids=[name for name, _ in MOVES])
async def test_the_served_answer_is_what_the_budget_and_the_classifier_do(db_session, name, move):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await seed_system_tags(db_session, budget.id)

    # ASSUMPTION's situation: money in the budget, the envelope funded, and
    # any card owing nothing.
    base = await create_account(db_session, budget, "Base Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    group = await create_category_group(db_session, budget, "Everyday")
    envelope = await create_category(db_session, budget, group, "Envelope")
    if move.category.value in ("savings", "debt_principal"):
        tags = TagRepository(db_session)
        tag = await tags.get_system_tag(budget.id, move.category.value)
        assert tag is not None
        await tags.set_category_tags(envelope.id, [tag.id])
    await create_transaction(db_session, budget, base, "10000", TODAY, category=inflow)
    await create_budget_assignment(db_session, budget, envelope, MONTH, "5000")
    category = {
        CategoryKind.NONE: None,
        CategoryKind.INCOME: inflow,
    }.get(move.category, envelope)

    source = await _account(db_session, budget, _shape_name(move.account), "Move From")
    target = None
    if move.to_account is not None:
        target = await _account(db_session, budget, _shape_name(move.to_account), "Move To")
    await db_session.flush()

    before = await _snapshot(services, budget, envelope)
    if move.kind is MoveKind.TRANSFER:
        assert target is not None
        created = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=source.id,
                date=TODAY,
                amount=-AMOUNT,
                transfer_account_id=target.id,
                category_id=category.id if category else None,
                cleared="cleared",
                auto_categorize=False,
            ),
        )
        partner = await db_session.get(Transaction, created.transfer_id)
        rows = {LegRole.FROM: created.id, LegRole.TO: partner.id}
    else:
        sign = 1 if move.direction is Direction.IN else -1
        row = await create_transaction(
            db_session, budget, source, sign * AMOUNT, TODAY, category=category
        )
        rows = {LegRole.ACCOUNT: row.id}
    await db_session.flush()
    after = await _snapshot(services, budget, envelope)

    explanation = await MoneyMovesService(db_session).explain(move)

    actual_terms = {t: after[t] - before[t] for t in BudgetTerm if after[t] != before[t]}
    assert explanation.budget_terms == actual_terms, (
        f"{name}: the explorer says {explanation.budget_terms}, the budget moved {actual_terms}"
    )

    classified = {
        r.id: (r.cls, r.reason)
        for r in (
            await db_session.execute(
                apply_class_joins(
                    select(
                        Transaction.id,
                        ACTIVITY_CLASS.label("cls"),
                        ACTIVITY_REASON.label("reason"),
                    ).where(Transaction.id.in_(list(rows.values())))
                )
            )
        ).all()
    }
    for leg in explanation.legs:
        assert (leg.cls.value, leg.reason.value) == classified[rows[leg.role]], (
            f"{name}: the {leg.role.value} leg is served as {leg.cls}/{leg.reason} but the "
            f"shipped classifier says {classified[rows[leg.role]]}"
        )


def test_every_move_the_explorer_can_offer_is_built():
    """25 transfer pairs, 10 account-and-direction transactions, each with
    every category kind its category leg allows. A shape added to the domain
    without one here would leave its answers unchecked."""
    transfers = [m for _, m in MOVES if m.kind is MoveKind.TRANSFER]
    plain = [m for _, m in MOVES if m.kind is MoveKind.TRANSACTION]
    # on<->off pairs carry five kinds, everything else only NONE: 12 pairs x 5
    # plus 13 pairs x 1; on-budget transactions carry five, off-budget one.
    assert len(transfers) == 12 * 5 + 13
    assert len(plain) == 4 * 5 + 6
