"""The probe's inflow-kind classification, against a real database.

`_SQL_INFLOW_KINDS` has no repository original — it exists so the report can
say HOW a residual stream's money arrived, and the CASE arms are the whole
content: a categorized transfer leg from an off-budget account is the shape
that reads as residual instead of a payment (YNAB forces a category onto that
leg), and mislabeling it as 'plain' would send the reader hunting refunds
that do not exist. Every row matches exactly one arm, so the buckets
partition the pair's inflows; this suite pins where each arm lands.
"""

import importlib.util
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
    create_user,
)

_PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "card_reserve_probe.py"
_spec = importlib.util.spec_from_file_location("card_reserve_probe", _PROBE_PATH)
assert _spec is not None and _spec.loader is not None
probe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = probe
_spec.loader.exec_module(probe)

RECENT = date.today() - timedelta(days=10)


async def _kinds(db_session, budget) -> dict[tuple[str, str], dict[str, tuple[int, Decimal]]]:
    """The query, gathered exactly the way `read_db` gathers it."""
    result = await db_session.execute(text(probe._SQL_INFLOW_KINDS), {"b": budget.id})
    out: dict[tuple[str, str], dict[str, tuple[int, Decimal]]] = {}
    for r in result:
        pair = (str(r.category_id), str(r.account_id))
        out.setdefault(pair, {})[str(r.kind)] = (int(r.n), Decimal(str(r.net)))
    return out


async def test_each_arrival_shape_lands_in_its_own_bucket(db_session):
    """One of each: a plain refund, and categorized transfer legs from a
    tracking account, from budget cash, and from another card. The tracking
    one is the diagnosis this query exists for."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    savings_offbudget = await create_account(
        db_session, budget, "Old Brokerage", account_type="investment", on_budget=False
    )
    card = await create_account(
        db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
    )
    other_card = await create_account(
        db_session, budget, "Nordvik Store Card", account_type="credit_card", on_budget=True
    )
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")

    await create_transaction(db_session, budget, card, "40.00", RECENT, category=cat)
    for source, amount in (
        (savings_offbudget, "100.00"),
        (checking, "25.00"),
        (other_card, "10.00"),
    ):
        _from, to_leg = await create_transfer(db_session, budget, source, card, amount, RECENT)
        to_leg.category_id = cat.id
    # Excluded shapes: an uncategorized inflow, and a charge (not an inflow).
    await create_transaction(db_session, budget, card, "5.00", RECENT)
    await create_transaction(db_session, budget, card, "-60.00", RECENT, category=cat)
    await db_session.flush()

    kinds = (await _kinds(db_session, budget)).get((str(cat.id), str(card.id)), {})
    assert kinds == {
        "plain": (1, Decimal("40.00")),
        "transfer_tracking": (1, Decimal("100.00")),
        "transfer_cash": (1, Decimal("25.00")),
        "transfer_card": (1, Decimal("10.00")),
    }
    # The partition: the buckets account for every categorized inflow once.
    total = sum((net for _n, net in kinds.values()), Decimal("0"))
    assert total == Decimal("175.00")

    # The gross charge side of the same pair: the -60 charge, sign flipped.
    result = await db_session.execute(text(probe._SQL_CHARGE_ROWS), {"b": budget.id})
    charges = {
        (str(r.category_id), str(r.account_id)): (int(r.n), Decimal(str(r.gross))) for r in result
    }
    assert charges[(str(cat.id), str(card.id))] == (1, Decimal("60.00"))


async def test_a_transfer_leg_whose_partner_account_is_gone_reads_unlinked(db_session):
    """A leg pointing at a deleted account can name no counterpart; it must
    say so rather than borrow the nearest bucket."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    doomed = await create_account(db_session, budget, "Closed Checking")
    card = await create_account(
        db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
    )
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")

    _from, to_leg = await create_transfer(db_session, budget, doomed, card, "75.00", RECENT)
    to_leg.category_id = cat.id
    doomed.is_deleted = True
    await db_session.flush()

    kinds = (await _kinds(db_session, budget)).get((str(cat.id), str(card.id)), {})
    assert kinds == {"transfer_unlinked": (1, Decimal("75.00"))}
