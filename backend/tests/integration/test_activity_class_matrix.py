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
    # Other Asset defaults to not counting as savings — the car.
    vehicle = await create_account(
        db_session, budget, "Second Car", account_type="other_asset", on_budget=False
    )
    # The same type, marked as savings — crypto someone saves into.
    crypto = await create_account(
        db_session,
        budget,
        "Crypto Wallet",
        account_type="other_asset",
        on_budget=False,
        counts_as_savings=True,
    )
    # An investment someone marked as not savings — the flag is the account's.
    art = await create_account(
        db_session,
        budget,
        "Art Collection",
        account_type="investment",
        on_budget=False,
        counts_as_savings=False,
    )
    # The flag on a liability means nothing: debt stays debt.
    flagged_loan = await create_account(
        db_session,
        budget,
        "Boat Loan",
        account_type="loan",
        on_budget=False,
        counts_as_savings=False,
    )
    inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
    rta = await create_category(db_session, budget, inflow, "Ready to Assign")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    fund = await create_category(db_session, budget, everyday, "Car Replacement")
    payoff = await create_category(db_session, budget, everyday, "Debt Payoff")
    sinking = await create_category(db_session, budget, everyday, "Property Tax")

    repo = TagRepository(db_session)
    tags = {t.system_key: t for t in await repo.list_for_budget(budget.id)}
    for cat, key in (
        (fund, "savings"),
        (payoff, "debt_principal"),
        (sinking, "long_term_expense"),
    ):
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
        vehicle=vehicle,
        crypto=crypto,
        art=art,
        flagged_loan=flagged_loan,
        rta=rta,
        groceries=groceries,
        fund=fund,
        payoff=payoff,
        sinking=sinking,
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
    # The matrix had no long_term_expense line at all, which is how the tag
    # spent a release classifying a property-tax bill as money saved. A
    # sinking fund's payout is SPENDING; only where the money actually went
    # can make it saving.
    ("long-term-expense-tagged payout", "checking", "-2340.00", "sinking", None, SPENDING),
    (
        "long-term-expense-tagged, to a tracked asset",
        "checking",
        "-195.00",
        "sinking",
        "brokerage",
        SAVINGS,
    ),
    # ─ transfers, by where they point ────────────────────────────────────
    ("to a tracked asset, categorized", "checking", "-500.00", "groceries", "brokerage", SAVINGS),
    ("to a tracked asset, uncategorized", "checking", "-500.00", None, "brokerage", SAVINGS),
    ("to a tracked debt, categorized", "checking", "-275.00", "groceries", "loan", DEBT),
    ("to a tracked debt, uncategorized", "checking", "-275.00", None, "loan", DEBT),
    ("between two on-budget accounts", "checking", "-300.00", None, "on_budget_savings", INTERNAL),
    # Categorized, the same leg falls past every transfer rule to the spending
    # default — and a long-term-expense tag no longer catches it first. Pinned
    # in report figures by test_activity_class.py's
    # TestACategorizedOnBudgetLegIsSpending.
    (
        "between two on-budget accounts, categorized",
        "checking",
        "-300.00",
        "groceries",
        "on_budget_savings",
        SPENDING,
    ),
    (
        "between two on-budget accounts, from a sinking fund",
        "checking",
        "-195.00",
        "sinking",
        "on_budget_savings",
        SPENDING,
    ),
    ("to an on-budget credit card", "checking", "-200.00", None, "credit", INTERNAL),
    # ─ tracked assets that do and do not count as savings ────────────────
    # A savings asset is saving both ways: money out of it un-saves.
    ("from a tracked asset, uncategorized", "checking", "500.00", None, "brokerage", SAVINGS),
    ("from a tracked asset, categorized", "checking", "500.00", "groceries", "brokerage", SAVINGS),
    ("to an Other Asset marked savings", "checking", "-500.00", None, "crypto", SAVINGS),
    ("from an Other Asset marked savings", "checking", "500.00", None, "crypto", SAVINGS),
    # A non-savings asset is an outside payee on the budget side. Buying the
    # car is spending, selling it is income — categorized or not.
    ("buying a car, uncategorized", "checking", "-9000.00", None, "vehicle", SPENDING),
    ("buying a car, categorized", "checking", "-9000.00", "groceries", "vehicle", SPENDING),
    ("selling a car, uncategorized", "checking", "4500.00", None, "vehicle", INCOME),
    ("selling a car, to the income group", "checking", "4500.00", "rta", "vehicle", INCOME),
    # A categorized inflow to an ordinary category nets against its spending,
    # exactly as a refund from an outside payee does.
    (
        "selling a car, to an ordinary category",
        "checking",
        "4500.00",
        "groceries",
        "vehicle",
        SPENDING,
    ),
    ("to an investment marked not savings", "checking", "-800.00", None, "art", SPENDING),
    ("from an investment marked not savings", "checking", "800.00", None, "art", INCOME),
    # The brokerage's leg of buying a car with it: rule 5 without the carve-out,
    # which is for on-budget legs only. (The car's leg of the same move is
    # rule 3, which does not ask which side of the budget the leg is on, and
    # is not pinned here.)
    ("brokerage to a car", "brokerage", "-4500.00", None, "vehicle", INTERNAL),
    # The flag is read for assets only.
    (
        "to a debt marked not savings, uncategorized",
        "checking",
        "-275.00",
        None,
        "flagged_loan",
        DEBT,
    ),
    (
        "to a debt marked not savings, categorized",
        "checking",
        "-275.00",
        "groceries",
        "flagged_loan",
        DEBT,
    ),
    ("from a debt marked not savings", "checking", "1000.00", None, "flagged_loan", DEBT),
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

    @pytest.mark.parametrize("amount", ["-500.00", "500.00"], ids=["into", "out-of"])
    @pytest.mark.parametrize("target", ["brokerage", "loan", "vehicle", "crypto", "art"])
    async def test_tracked_side_is_internal(self, db_session, target, amount):
        """Including a car's side of its own sale. The on-budget leg's carve-out
        from rule 5 must not reach this leg: it would fall to rule 6 and call
        the sale an investment loss inside the vehicle account."""
        w = await _world(db_session)
        out = await _linked(db_session, w, w.checking, getattr(w, target), amount)
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
        "target,amount,expected",
        [
            ("brokerage", "-500.00", SAVINGS),
            ("loan", "-500.00", DEBT),
            ("vehicle", "-500.00", SPENDING),
            ("vehicle", "500.00", INCOME),
        ],
        ids=["asset", "debt", "non-savings-asset-out", "non-savings-asset-in"],
    )
    async def test_orphan_matches_linked(self, db_session, target, amount, expected):
        w = await _world(db_session)
        account = getattr(w, target)
        payee = await create_payee(
            db_session, w.budget, f"Transfer : {account.name}", transfer_account_id=account.id
        )
        orphan = await create_transaction(
            db_session, w.budget, w.checking, amount, TODAY, payee=payee
        )
        await db_session.flush()

        assert await _classify(db_session, orphan) == expected.value
