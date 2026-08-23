"""Every classifier input crossed against its expected class.

`assert_activity_class_partition` passed on all four classification bugs found
in review, and it was right to: a misclassified row still lands in exactly one
class and the sums still conserve. Totality and conservation are necessary and
nowhere near sufficient — the missing property is that a row lands in the
class it *belongs* in.

So this is an explicit table. Each row states a situation and the answer, and
the dimensions are the ones that actually broke: whether a payee exists at
all, whether `classification` is NULL, whether the leg was categorized, which
way the money moved, and which side of the budget the accounts sit on.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from igab.db.models import Transaction
from igab.domain.activity_class import ACTIVITY_CLASS, ActivityClass, apply_class_joins
from igab.repositories.tag_repo import TagRepository

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_tag,
    create_transaction,
    create_user,
)

TODAY = date.today()

# (case, own account, amount, category, counterpart, expected class)
SPENDING = ActivityClass.SPENDING
INCOME = ActivityClass.INCOME
SAVINGS = ActivityClass.SAVINGS
DEBT = ActivityClass.DEBT_PRINCIPAL
INTERNAL = ActivityClass.TRANSFER_INTERNAL
RETURN = ActivityClass.INVESTMENT_RETURN
INTEREST = ActivityClass.DEBT_INTEREST


class World:
    """Accounts and categories covering every axis the rules read."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


async def _world(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    checking = await create_account(db_session, budget, "Checking", on_budget=True)
    on_budget_savings = await create_account(db_session, budget, "Cash Savings", on_budget=True)
    credit = await create_account(
        db_session, budget, "Visa", account_type="credit_card", on_budget=True
    )
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    loan = await create_account(
        db_session, budget, "Car Loan", account_type="loan", on_budget=False
    )
    inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
    rta = await create_category(db_session, budget, inflow, "Ready to Assign")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    fund = await create_category(db_session, budget, everyday, "Car Replacement")
    payoff = await create_category(db_session, budget, everyday, "Debt Payoff")

    repo = TagRepository(db_session)
    tags = {t.system_key: t for t in await repo.list_for_budget(budget.id)}
    for cat, key in ((fund, "savings"), (payoff, "debt_principal")):
        tag = tags.get(key) or await create_tag(db_session, budget, key, system_key=key)
        await repo.set_category_tags(cat.id, [tag.id])

    await db_session.flush()
    return World(
        budget=budget,
        checking=checking,
        on_budget_savings=on_budget_savings,
        credit=credit,
        brokerage=brokerage,
        loan=loan,
        rta=rta,
        groceries=groceries,
        fund=fund,
        payoff=payoff,
    )


async def _classify(db_session, txn) -> str:
    # Transaction.id is not wanted; the class joins chain from it.
    return (
        await db_session.execute(
            apply_class_joins(
                select(Transaction.id, ACTIVITY_CLASS).where(Transaction.id == txn.id)
            )
        )
    ).one()[1]


async def _linked(db_session, w, src, dst, amount, category=None):
    out = await create_transaction(db_session, w.budget, src, amount, TODAY, category=category)
    into = await create_transaction(db_session, w.budget, dst, str(-Decimal(amount)), TODAY)
    out.transfer_id, into.transfer_id = into.id, out.id
    await db_session.flush()
    return out


CASES = [
    # ─ plain rows on an on-budget account ────────────────────────────────
    ("plain outflow", "checking", "-50.00", "groceries", None, SPENDING),
    ("plain outflow, no category", "checking", "-50.00", None, None, SPENDING),
    ("plain outflow, no payee at all", "checking", "-50.00", None, None, SPENDING),
    ("uncategorized inflow", "checking", "900.00", None, None, INCOME),
    ("inflow to the income group", "checking", "900.00", "rta", None, INCOME),
    ("NEGATIVE row in the income group", "checking", "-900.00", "rta", None, INCOME),
    ("refund to an ordinary category", "checking", "25.00", "groceries", None, SPENDING),
    # ─ tag overrides beat everything ─────────────────────────────────────
    ("savings-tagged, no transfer", "checking", "-500.00", "fund", None, SAVINGS),
    ("debt-tagged, no transfer", "checking", "-275.00", "payoff", None, DEBT),
    # ─ transfers, by where they point ────────────────────────────────────
    ("to a tracked asset, categorized", "checking", "-500.00", "groceries", "brokerage", SAVINGS),
    ("to a tracked asset, uncategorized", "checking", "-500.00", None, "brokerage", SAVINGS),
    ("to a tracked debt, categorized", "checking", "-275.00", "groceries", "loan", DEBT),
    ("to a tracked debt, uncategorized", "checking", "-275.00", None, "loan", DEBT),
    ("between two on-budget accounts", "checking", "-300.00", None, "on_budget_savings", INTERNAL),
    ("to an on-budget credit card", "checking", "-200.00", None, "credit", INTERNAL),
    # ─ activity inside tracked accounts ──────────────────────────────────
    ("dividend on a brokerage", "brokerage", "125.00", None, None, RETURN),
    ("fee on a brokerage", "brokerage", "-25.00", None, None, RETURN),
    ("interest on a tracked loan", "loan", "-40.00", None, None, INTEREST),
]


@pytest.mark.parametrize(
    "case,account,amount,category,counterpart,expected",
    CASES,
    ids=[c[0] for c in CASES],
)
async def test_classification_matrix(
    db_session, case, account, amount, category, counterpart, expected
):
    w = await _world(db_session)
    cat = getattr(w, category) if category else None

    if counterpart:
        txn = await _linked(
            db_session, w, getattr(w, account), getattr(w, counterpart), amount, cat
        )
    else:
        txn = await create_transaction(
            db_session, w.budget, getattr(w, account), amount, TODAY, category=cat
        )
        await db_session.flush()

    assert await _classify(db_session, txn) == expected.value, case


class TestTheFarSideOfATransferIsNeverDoubleCounted:
    """Only the on-budget leg of an out-of-budget transfer represents money
    leaving. Counting the tracked side too would double it."""

    @pytest.mark.parametrize("target", ["brokerage", "loan"])
    async def test_tracked_side_is_internal(self, db_session, target):
        w = await _world(db_session)
        out = await _linked(db_session, w, w.checking, getattr(w, target), "-500.00")
        partner = (
            await db_session.execute(select(Transaction).where(Transaction.id == out.transfer_id))
        ).scalar_one()

        assert await _classify(db_session, partner) == INTERNAL.value


class TestATransferLegAlwaysHasACounterpartToRead:
    """Replaces the two retired NULL-classification cases.

    `Account.classification` is NOT NULL as of b8c3e5a71f42, so the only way
    left to fail to read a counterpart's classification is to have no
    counterpart. These pin the structural reason that cannot happen — the same
    reason `_counterpart_is_liability`'s coalesce is defence in depth rather
    than load-bearing. If either guarantee is ever relaxed, both transfer arms
    start declining on UNKNOWN and transfers quietly become spending.
    """

    async def test_deleting_the_partner_unlinks_rather_than_dangles(self, db_session):
        """ondelete=SET NULL on transfer_id. A leg cannot point at nothing: it
        stops being a transfer leg instead, and classifies on its own terms."""
        w = await _world(db_session)
        out = await _linked(db_session, w, w.checking, w.brokerage, "-500.00")
        partner_id = out.transfer_id

        await db_session.execute(delete(Transaction).where(Transaction.id == partner_id))
        await db_session.flush()
        await db_session.refresh(out)

        assert out.transfer_id is None
        assert await _classify(db_session, out) == SPENDING.value

    async def test_a_soft_deleted_partner_still_resolves(self, db_session):
        """Soft deletion does not sever the link, so the surviving leg keeps
        describing the money movement it always did."""
        w = await _world(db_session)
        out = await _linked(db_session, w, w.checking, w.brokerage, "-500.00")
        partner = (
            await db_session.execute(select(Transaction).where(Transaction.id == out.transfer_id))
        ).scalar_one()
        partner.is_deleted = True
        await db_session.flush()

        assert await _classify(db_session, out) == SAVINGS.value


class TestOrphanedLegsClassifyLikeLinkedOnes:
    """A leg whose partner never imported is recognised by its transfer payee.
    It must reach the same class as the linked equivalent, or a YNAB import
    and a native transfer disagree about identical money."""

    @pytest.mark.parametrize(
        "target,expected", [("brokerage", SAVINGS), ("loan", DEBT)], ids=["asset", "debt"]
    )
    async def test_orphan_matches_linked(self, db_session, target, expected):
        w = await _world(db_session)
        account = getattr(w, target)
        payee = await create_payee(
            db_session, w.budget, f"Transfer : {account.name}", transfer_account_id=account.id
        )
        orphan = await create_transaction(
            db_session, w.budget, w.checking, "-500.00", TODAY, payee=payee
        )
        await db_session.flush()

        assert await _classify(db_session, orphan) == expected.value
