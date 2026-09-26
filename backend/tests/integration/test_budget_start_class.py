"""History from before an account's budget start is opening position, and money
arriving on a card with no category is never income.

A card linked with three months of bank history keeps those rows in its
register, uncategorized on purpose: the first sync files nothing dated before
`Account.budget_start_date`, and `NEEDS_CATEGORY` stops asking about them. The
reports did not agree. Every swipe in those months counted as spending —
beside the checking account's payments of the same bills, filed to the
categories they paid, so the money was spent twice — and the card's side of
each payment, a credit with no category, counted as income. On the budget
this was found in, a card-payment payee was one of the top income sources.

After the start date a card credit with no category still read as income:
the card's side of a payment whose checking side was never linked, or a
refund nobody filed. A card is paid down, not paid.

What this pins, in order:

- rule 4 (BEFORE_BUDGET_START), read by both implementations: every shape it
  reaches, the date boundary, what it must not reach — a row someone filed, a
  NULL start date, a tracked account, the far leg — and where it sits;
- rule 10 (UNFILED_CARD_CREDIT): the card credits it reaches and the inflows
  it leaves alone;
- the reports that stopped counting both, by hand-written figure;
- that the budget never reads a class: moving the start date moves no figure
  on the budget page, no account balance and no net worth, while it changes
  the class of every row it crosses.

Every amount is invented and round enough to check on paper.
"""

from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import Payee, Transaction
from igab.domain.activity_class import (
    INCOME_ROW,
    ActivityClass,
    ActivityReason,
    LegFacts,
    apply_class_joins,
    rule_ladder,
)
from igab.domain.dates import add_months, month_end
from igab.domain.payee_names import RECONCILIATION_ADJUSTMENT_PAYEE, STARTING_BALANCE_PAYEE
from igab.repositories.account_repo import AccountRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.card_payment import ensure_payment_category
from igab.services.money_moves_service import MoneyMovesService
from igab.services.report_basics import discretionary, income_by_source, means_months
from igab.services.report_service import ReportService

from .class_agreement import classes_of
from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_transfer,
    create_user,
    make_services,
    tag_with_system_tags,
)
from .invariants import assert_activity_class_partition

D = Decimal
OPENING = (ActivityClass.OPENING_BALANCE.value, ActivityReason.BEFORE_BUDGET_START.value)
UNFILED_CREDIT = (
    ActivityClass.TRANSFER_INTERNAL.value,
    ActivityReason.UNFILED_CARD_CREDIT.value,
)

#: The classifier reads no clock, so the rules are pinned on fixed dates.
START = date(2026, 6, 15)
BEFORE = START - timedelta(days=1)
AFTER = START + timedelta(days=10)


class World:
    def __init__(self, **kw):
        self.__dict__.update(kw)


async def _world(db_session):
    """Every account shape a pre-start row can sit on. The card and the late
    checking account joined the budget on START; the other checking account
    and the tracked accounts never answered (NULL), except the loan, which
    carries a start date to show a tracked account ignores one."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
    everyday = await create_category_group(db_session, budget, "Everyday")
    w = World(
        budget=budget,
        card=await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
        ),
        late=await create_account(db_session, budget, "Harborstone Checking"),
        cash=await create_account(db_session, budget, "Cascade Point Checking"),
        brokerage=await create_account(
            db_session,
            budget,
            "Cascade Point Brokerage",
            account_type="investment",
            on_budget=False,
        ),
        loan=await create_account(
            db_session, budget, "Harborstone Auto Loan", account_type="auto_loan", on_budget=False
        ),
        # Other Asset defaults to not counting as savings — the car.
        car=await create_account(
            db_session, budget, "Second Car", account_type="other_asset", on_budget=False
        ),
        ready=await create_category(db_session, budget, inflow, "Ready to Assign"),
        dining=await create_category(db_session, budget, everyday, "Dining Out"),
        investing=await create_category(db_session, budget, everyday, "Investing"),
    )
    for account in (w.card, w.late, w.loan):
        account.budget_start_date = START
    await db_session.flush()
    return w


async def _row(db_session, w, shape: str, when: date, *, category=None) -> Transaction:
    """The row a shape names, dated `when`, on the account with the start
    date. A transfer shape builds both legs, linked, and returns the near one;
    the far account never answered, so its leg is counted as it always was."""
    plain = {
        "card purchase": (w.card, "-60.00"),
        "card credit": (w.card, "500.00"),
        "paycheck": (w.late, "3000.00"),
        "checking purchase": (w.late, "-40.00"),
    }
    if shape in plain:
        account, amount = plain[shape]
        return await create_transaction(
            db_session, w.budget, account, amount, when, category=category
        )
    if shape == "reconciliation":
        # Payee names are unique per budget, and a test may ask twice.
        payee = (
            await db_session.execute(
                select(Payee).where(
                    Payee.budget_id == w.budget.id, Payee.name == RECONCILIATION_ADJUSTMENT_PAYEE
                )
            )
        ).scalar_one_or_none() or await create_payee(
            db_session, w.budget, RECONCILIATION_ADJUSTMENT_PAYEE
        )
        return await create_transaction(db_session, w.budget, w.late, "-35.00", when, payee=payee)
    linked = {
        "to a brokerage": (w.late, w.brokerage, "1000.00", 0),
        "to a tracked loan": (w.late, w.loan, "800.00", 0),
        "buying a car": (w.late, w.car, "4000.00", 0),
        "selling a car": (w.car, w.late, "4000.00", 1),
        "a linked card payment": (w.cash, w.card, "500.00", 1),
    }
    src, dst, amount, near = linked[shape]
    legs = await create_transfer(db_session, w.budget, src, dst, amount, when, category=category)
    return legs[near]


#: (shape, the class the same row takes on or after the start date). The
#: second column is what every one of these rows counted as before rule 4 —
#: except the card credit, which rule 10 has also taken out of income.
SHAPES = [
    pytest.param("card purchase", ActivityClass.SPENDING, id="card purchase"),
    pytest.param("card credit", ActivityClass.TRANSFER_INTERNAL, id="card side of a payment"),
    pytest.param("paycheck", ActivityClass.INCOME, id="uncategorized paycheck"),
    pytest.param("checking purchase", ActivityClass.SPENDING, id="checking purchase"),
    pytest.param("reconciliation", ActivityClass.SPENDING, id="reconciliation adjustment"),
    pytest.param("to a brokerage", ActivityClass.SAVINGS, id="move to a brokerage"),
    pytest.param("to a tracked loan", ActivityClass.DEBT_PRINCIPAL, id="loan payment"),
    pytest.param("buying a car", ActivityClass.SPENDING, id="car bought"),
    pytest.param("selling a car", ActivityClass.INCOME, id="car sold"),
    pytest.param(
        "a linked card payment", ActivityClass.TRANSFER_INTERNAL, id="linked card payment"
    ),
]


# ─── Rule 4: before the budget start ─────────────────────────────────────────


class TestBeforeTheStart:
    @pytest.mark.parametrize(("shape", "otherwise"), SHAPES)
    async def test_an_unfiled_row_before_the_start_is_an_opening(
        self, db_session, shape, otherwise
    ):
        w = await _world(db_session)
        row = await _row(db_session, w, shape, BEFORE)
        assert await classes_of(db_session, row) == OPENING

    @pytest.mark.parametrize(("shape", "otherwise"), SHAPES)
    async def test_the_start_date_itself_is_the_budgets(self, db_session, shape, otherwise):
        """The first day counts: `dated_from_budget_start` is `>=`, as the
        register's needs-a-category rule has always read it."""
        w = await _world(db_session)
        row = await _row(db_session, w, shape, START)
        assert (await classes_of(db_session, row))[0] == otherwise.value

    @pytest.mark.parametrize(("shape", "otherwise"), SHAPES)
    async def test_no_start_date_changes_nothing(self, db_session, shape, otherwise):
        """NULL is every account until someone answers: the same row, years
        back, takes the class its shape gives it."""
        w = await _world(db_session)
        for account in (w.card, w.late, w.loan):
            account.budget_start_date = None
        await db_session.flush()
        row = await _row(db_session, w, shape, date(2020, 1, 6))
        assert (await classes_of(db_session, row))[0] == otherwise.value

    async def test_the_date_is_read_never_stored(self, db_session):
        """Nothing is written when an account's start moves, so nothing can go
        stale: the same row is an opening, then a purchase, then an opening
        again."""
        w = await _world(db_session)
        row = await _row(db_session, w, "card purchase", BEFORE)
        assert await classes_of(db_session, row) == OPENING
        w.card.budget_start_date = BEFORE
        await db_session.flush()
        assert (await classes_of(db_session, row))[0] == ActivityClass.SPENDING.value
        w.card.budget_start_date = AFTER
        await db_session.flush()
        assert await classes_of(db_session, row) == OPENING

    async def test_the_partition_stays_total(self, db_session):
        w = await _world(db_session)
        for shape, _ in [p.values for p in SHAPES]:
            await _row(db_session, w, shape, BEFORE)
            await _row(db_session, w, shape, AFTER)
        await assert_activity_class_partition(db_session, w.budget.id)


class TestWhatRuleFourMustNotReach:
    @pytest.mark.parametrize(
        ("shape", "category", "expected"),
        [
            ("card purchase", "dining", ActivityClass.SPENDING),
            # A refund someone filed nets against the category, as ever.
            ("card credit", "dining", ActivityClass.SPENDING),
            ("paycheck", "ready", ActivityClass.INCOME),
            # A filed move to a tracked savings account is saving by where it
            # went (rule 5), whatever the category is called.
            ("to a brokerage", "investing", ActivityClass.SAVINGS),
        ],
        ids=["card purchase", "card refund", "paycheck", "move to a brokerage"],
    )
    async def test_a_row_someone_filed_counts_as_its_category_says(
        self, db_session, shape, category, expected
    ):
        """The escape hatch the sync's own docstring promises: anyone who wants
        a pre-start row in their reports can file it by hand."""
        w = await _world(db_session)
        row = await _row(db_session, w, shape, BEFORE, category=getattr(w, category))
        assert (await classes_of(db_session, row))[0] == expected.value

    async def test_a_starting_balance_keeps_its_own_reason(self, db_session):
        """The first sync anchors an account the day before its oldest row —
        before any start date. Rule 1 comes first and names it more exactly;
        either way it is an opening."""
        w = await _world(db_session)
        starting = await create_payee(db_session, w.budget, STARTING_BALANCE_PAYEE)
        row = await create_transaction(
            db_session, w.budget, w.card, "-1200.00", BEFORE, payee=starting
        )
        assert await classes_of(db_session, row) == (
            ActivityClass.OPENING_BALANCE.value,
            ActivityReason.STARTING_BALANCE.value,
        )

    @pytest.mark.parametrize(
        ("account", "amount", "expected"),
        [
            ("loan", "-20.00", ActivityClass.DEBT_INTEREST),
            ("brokerage", "40.00", ActivityClass.INVESTMENT_RETURN),
        ],
        ids=["tracked loan interest", "tracked brokerage growth"],
    )
    async def test_a_tracked_account_ignores_its_start_date(
        self, db_session, account, amount, expected
    ):
        """On budget only, as `NEEDS_CATEGORY` is: a tracked account's rows are
        never filed, and rules 8 and 9 already keep them out of income and
        spending."""
        w = await _world(db_session)
        w.brokerage.budget_start_date = START
        await db_session.flush()
        row = await create_transaction(db_session, w.budget, getattr(w, account), amount, BEFORE)
        assert (await classes_of(db_session, row))[0] == expected.value

    @pytest.mark.parametrize(
        ("shape", "far_class"),
        [
            ("to a brokerage", ActivityClass.TRANSFER_INTERNAL),
            ("a linked card payment", ActivityClass.TRANSFER_INTERNAL),
            ("selling a car", ActivityClass.TRANSFER_INTERNAL),
        ],
        ids=["brokerage leg", "checking leg of a card payment", "car's leg"],
    )
    async def test_the_far_leg_keeps_its_own_accounts_reading(self, db_session, shape, far_class):
        """The rule reads the row's own account. The far account never
        answered, so its leg is counted exactly as it always was."""
        w = await _world(db_session)
        near = await _row(db_session, w, shape, BEFORE)
        far = (
            await db_session.execute(select(Transaction).where(Transaction.id == near.transfer_id))
        ).scalar_one()
        assert await classes_of(db_session, near) == OPENING
        assert (await classes_of(db_session, far))[0] == far_class.value


# ─── Rule 10: a card is never paid income ────────────────────────────────────


class TestACardCreditIsNeverIncome:
    @pytest.mark.parametrize(
        ("account_type", "when"),
        [
            ("credit_card", AFTER),
            ("credit_card", START),
            # A line of credit kept on budget is a card to the budget
            # (`txn_filters.CARD_ACCOUNT`), and to this rule.
            ("loan", AFTER),
        ],
        ids=["after the start", "on the start", "on-budget line of credit"],
    )
    async def test_an_unfiled_credit_on_a_card_is_a_transfer(self, db_session, account_type, when):
        w = await _world(db_session)
        card = await create_account(
            db_session, w.budget, "Harborstone Line", account_type=account_type, on_budget=True
        )
        card.budget_start_date = START
        row = await create_transaction(db_session, w.budget, card, "500.00", when)
        assert await classes_of(db_session, row) == UNFILED_CREDIT

    async def test_with_no_start_date_too(self, db_session):
        w = await _world(db_session)
        w.card.budget_start_date = None
        await db_session.flush()
        row = await create_transaction(db_session, w.budget, w.card, "500.00", AFTER)
        assert await classes_of(db_session, row) == UNFILED_CREDIT

    async def test_a_car_sold_straight_onto_the_card(self, db_session):
        """The one transfer leg that reaches rule 10: rule 7's carve-out would
        call the sale income, but the money lowered a debt and reached no
        envelope."""
        w = await _world(db_session)
        _, onto_card = await create_transfer(db_session, w.budget, w.car, w.card, "4000.00", AFTER)
        assert await classes_of(db_session, onto_card) == UNFILED_CREDIT

    @pytest.mark.parametrize(
        ("account", "amount", "category", "expected"),
        [
            # A rewards credit someone filed as income is income: they said so.
            ("card", "25.00", "ready", (ActivityClass.INCOME, ActivityReason.UNCATEGORIZED_INFLOW)),
            # A refund filed to its envelope nets against it.
            ("card", "25.00", "dining", (ActivityClass.SPENDING, ActivityReason.DEFAULT_SPENDING)),
            # Nothing arriving is not an inflow.
            ("card", "0.00", None, (ActivityClass.SPENDING, ActivityReason.DEFAULT_SPENDING)),
            ("card", "-60.00", None, (ActivityClass.SPENDING, ActivityReason.DEFAULT_SPENDING)),
            # Cash accounts: an unfiled inflow is still ready to assign.
            ("cash", "3000.00", None, (ActivityClass.INCOME, ActivityReason.UNCATEGORIZED_INFLOW)),
            # A tracked debt's own rows are rule 9's, whichever way they move.
            (
                "loan",
                "300.00",
                None,
                (ActivityClass.DEBT_INTEREST, ActivityReason.TRACKED_DEBT_ACTIVITY),
            ),
        ],
        ids=[
            "card credit filed to Ready to Assign",
            "card refund filed",
            "zero on a card",
            "card purchase",
            "paycheck on checking",
            "credit on a tracked loan",
        ],
    )
    async def test_what_it_leaves_alone(self, db_session, account, amount, category, expected):
        w = await _world(db_session)
        row = await create_transaction(
            db_session,
            w.budget,
            getattr(w, account),
            amount,
            AFTER,
            category=getattr(w, category) if category else None,
        )
        assert await classes_of(db_session, row) == (expected[0].value, expected[1].value)

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("cash", (ActivityClass.TRANSFER_INTERNAL, ActivityReason.INTERNAL_TRANSFER)),
            # Money drawn back out of savings onto the card.
            ("brokerage", (ActivityClass.SAVINGS, ActivityReason.TRANSFER_TO_TRACKED_ASSET)),
        ],
        ids=["linked payment from checking", "paid from a brokerage"],
    )
    async def test_a_linked_payment_keeps_the_transfer_rules(self, db_session, source, expected):
        w = await _world(db_session)
        _, onto_card = await create_transfer(
            db_session, w.budget, getattr(w, source), w.card, "500.00", AFTER
        )
        assert await classes_of(db_session, onto_card) == (expected[0].value, expected[1].value)

    async def test_the_register_still_asks_about_it(self, db_session):
        """Only the class moved. An unfiled card credit after the start is
        still unfiled work — link it or file it — and one before the start
        still is not."""
        w = await _world(db_session)
        await create_transaction(db_session, w.budget, w.card, "500.00", AFTER)
        await create_transaction(db_session, w.budget, w.card, "200.00", BEFORE)
        counts = await AccountRepository(db_session).uncategorized_counts_for([w.card.id])
        assert counts == {w.card.id: 1}


class TestWhereTheySit:
    async def test_the_ladder(self):
        """Rule 4 after the tags, which it can never meet, and ahead of every
        transfer rule; rule 10 straight ahead of the sign rule it overrides."""
        ladder = [(r.cls, r.reason) for r in rule_ladder()]
        assert ladder[3] == (ActivityClass.OPENING_BALANCE, ActivityReason.BEFORE_BUDGET_START)
        assert ladder[4][1] is ActivityReason.TRANSFER_TO_TRACKED_ASSET
        assert ladder[9:11] == [
            (ActivityClass.TRANSFER_INTERNAL, ActivityReason.UNFILED_CARD_CREDIT),
            (ActivityClass.INCOME, ActivityReason.UNCATEGORIZED_INFLOW),
        ]
        assert rule_ladder()[3].tag_key is None

    async def test_the_guide_asks_the_same_ladder(self, db_session):
        """The explorer's FROM-less CASE over literal facts."""
        service = MoneyMovesService(db_session)
        card_credit = LegFacts(
            own_on_budget=True,
            own_is_liability=True,
            transfer_leg=False,
            starting_balance=False,
            before_budget_start=False,
            tracked_counterpart=False,
            counterpart_is_liability=False,
            counterpart_counts_as_savings=True,
            categorized=False,
            savings_sent_out=False,
            tagged_debt=False,
            in_system_group=False,
            amount_positive=True,
        )
        assert await service.classify(card_credit) == (
            ActivityClass.TRANSFER_INTERNAL,
            ActivityReason.UNFILED_CARD_CREDIT,
        )
        pre_start = replace(card_credit, own_is_liability=False, before_budget_start=True)
        assert await service.classify(pre_start) == (
            ActivityClass.OPENING_BALANCE,
            ActivityReason.BEFORE_BUDGET_START,
        )
        tracked = replace(pre_start, own_on_budget=False)
        assert await service.classify(tracked) == (
            ActivityClass.INVESTMENT_RETURN,
            ActivityReason.TRACKED_ASSET_ACTIVITY,
        )


# ─── The reports that stopped counting them ──────────────────────────────────


def _month() -> date:
    """The last complete month, whatever today is: every report below can
    read it, the averaging ones included."""
    return add_months(date.today().replace(day=1), -1)


def _day(n: int) -> date:
    return _month().replace(day=n)


async def _household(db_session):
    """Sapphire Visa joined the budget on the 10th of the month, with the
    bank's history from the 1st.

    Counted:
      - a 3,000 paycheck into checking;
      - the checking side of the card's pre-start payment, 500, filed to the
        Card Bill envelope — before the card joined, the only record of that
        spending;
      - an 80 dinner on the card before the start, filed by hand;
      - after the start, 400 of Groceries (Essential) and 150 of Dining Out.

    Opening position, counted nowhere: a 600 purchase at Hardware Barn and
    the card's 500 side of that payment, both before the start and unfiled.

    Not income: a 50 refund from Hardware Barn after the start, not yet filed.
    """
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    card = await create_account(
        db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
    )
    card.budget_start_date = _day(10)
    inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
    everyday = await create_category_group(db_session, budget, "Everyday")
    ready = await create_category(db_session, budget, inflow, "Ready to Assign")
    bill = await create_category(db_session, budget, everyday, "Card Bill")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    dining = await create_category(db_session, budget, everyday, "Dining Out")
    await tag_with_system_tags(db_session, groceries, "essential")

    employer = await create_payee(db_session, budget, "Northwind Payserv")
    hardware = await create_payee(db_session, budget, "Hardware Barn")
    thanks = await create_payee(db_session, budget, "Payment Thank You")
    visa = await create_payee(db_session, budget, "Sapphire Visa")
    grocer = await create_payee(db_session, budget, "Corner Market")
    bistro = await create_payee(db_session, budget, "Thai Garden")

    async def row(account, amount, day, payee, category=None):
        return await create_transaction(
            db_session, budget, account, amount, _day(day), payee=payee, category=category
        )

    await row(checking, "3000.00", 5, employer, ready)
    uncounted = [
        await row(card, "-600.00", 3, hardware),
        await row(card, "500.00", 4, thanks),
        await row(card, "50.00", 20, hardware),
    ]
    await row(checking, "-500.00", 4, visa, bill)
    await row(card, "-80.00", 6, bistro, dining)
    await row(card, "-400.00", 15, grocer, groceries)
    await row(card, "-150.00", 16, bistro, dining)
    await db_session.flush()
    return budget, uncounted


INCOME = D("3000.00")
#: Card Bill 500 + Dining Out 80 + 150 + Groceries 400. With the pre-start
#: purchase this read 1,730.
SPENDING = D("1130.00")
#: Groceries is Essential. The pre-start purchase was a 600 Uncategorized line.
DISCRETIONARY = D("730.00")


class TestTheReports:
    async def test_the_classes_the_household_rests_on(self, db_session):
        _, (purchase, payment_side, refund) = await _household(db_session)
        assert await classes_of(db_session, purchase) == OPENING
        assert await classes_of(db_session, payment_side) == OPENING
        assert await classes_of(db_session, refund) == UNFILED_CREDIT

    async def test_income_vs_expenses(self, db_session):
        budget, _ = await _household(db_session)
        rows = await ReportService(db_session).income_vs_expense(budget.id, months=2)
        month = next(r for r in rows if r["month"] == _month())
        assert month["income"] == INCOME, "the card's credits read as income"
        assert month["expenses"] == SPENDING, "the card's pre-start purchase read as spending"

    async def test_the_overview_and_burn_rate(self, db_session):
        budget, _ = await _household(db_session)
        reports = ReportService(db_session)
        end = month_end(_month())
        cards = await reports.dashboard_metrics(budget.id, _month(), end, end)
        assert cards["income_this_month"] == INCOME
        assert cards["expenses_this_month"] == SPENDING
        assert cards["burn_rate_30"] == SPENDING
        burn = await reports.burn_rate(budget.id, months=2)
        assert next(b for b in burn if b["date"] == _month())["rolling_30"] == SPENDING

    async def test_income_by_source(self, db_session):
        budget, _ = await _household(db_session)
        report = await income_by_source(db_session, budget.id, months=1)
        assert {s["payee_name"]: s["total"] for s in report["sources"]} == {
            "Northwind Payserv": INCOME
        }, "the card's side of a payment, and an unfiled refund, were income sources"
        assert report["total"] == INCOME

    async def test_income_rows(self, db_session):
        """`INCOME_ROW` is what Income by Source and both Sankey modes read."""
        budget, uncounted = await _household(db_session)
        rows = (
            await db_session.execute(
                apply_class_joins(
                    select(Transaction.id).where(Transaction.budget_id == budget.id, INCOME_ROW)
                )
            )
        ).all()
        assert len(rows) == 1
        assert not {r.id for r in rows} & {u.id for u in uncounted}

    async def test_the_savings_rate_divides_by_real_income(self, db_session):
        budget, _ = await _household(db_session)
        rate = await ReportService(db_session).savings_rate(budget.id, months=2)
        assert rate["summary"]["income"] == INCOME
        assert rate["summary"]["spending"] == SPENDING

    async def test_the_sankey(self, db_session):
        budget, _ = await _household(db_session)
        sankey = await ReportService(db_session).cash_flow_sankey(
            budget.id, _month(), month_end(_month())
        )
        assert sankey["total_income"] == INCOME
        assert sankey["total_expense"] == SPENDING
        assert sankey["total_spending"] == SPENDING
        names = {n["name"] for n in sankey["nodes"]}
        assert not names & {"Payment Thank You", "Hardware Barn", "Uncategorized"}

    async def test_spending_breakdown(self, db_session):
        """The Breakdown reads categories, so it never drew the unfiled
        purchase. What this pins is the other half: the dinner filed by hand
        before the start is in Dining Out."""
        budget, _ = await _household(db_session)
        categories, total = await ReportService(db_session).spending_by_category(
            budget.id, _month(), month_end(_month())
        )
        assert {c["name"]: c["total"] for c in categories} == {
            "Card Bill": D("500.00"),
            "Groceries": D("400.00"),
            "Dining Out": D("230.00"),
        }
        assert total == SPENDING

    async def test_payee_analysis(self, db_session):
        budget, _ = await _household(db_session)
        report = await ReportService(db_session).payee_analysis(
            budget.id, _month(), month_end(_month())
        )
        assert {p["payee_name"] for p in report["payees"]} == {
            "Sapphire Visa",
            "Corner Market",
            "Thai Garden",
        }
        assert (report["total"], report["payee_count"]) == (SPENDING, 3)

    async def test_day_patterns(self, db_session):
        """And the note under it names no opening as left out: its remedy,
        "Include savings & debt payments", could never add one back."""
        budget, _ = await _household(db_session)
        report = await ReportService(db_session).day_patterns(
            budget.id, _month(), month_end(_month())
        )
        assert sum(d["count"] for d in report["days"]) == 4
        assert abs(sum(d["total"] for d in report["days"])) == SPENDING
        assert report["class_excluded"] is None

    async def test_discretionary_has_no_uncategorized_line(self, db_session):
        budget, uncounted = await _household(db_session)
        report = await discretionary(ReportService(db_session), budget.id, 1)
        assert report["tagged"] is True
        assert report["total"] == DISCRETIONARY
        assert report["spending_total"] == SPENDING
        assert {g["group_name"]: g["total"] for g in report["groups"]} == {
            "Everyday": DISCRETIONARY
        }, "the card's pre-start purchase was an Uncategorized line here"
        drill = {
            "start_date": report["window_start"],
            "end_date": report["window_end"],
            "scope": "leaf",
            "posted_only": True,
            "cash_flow_only": True,
            "discretionary": True,
        }
        repo = TransactionRepository(db_session)
        rows, count, total = await repo.list_for_budget(budget.id, **drill)
        assert (count, -total) == (3, DISCRETIONARY)
        assert not {r.id for r in rows} & {u.id for u in uncounted}
        _, count, _ = await repo.list_for_budget(budget.id, no_category=True, **drill)
        assert count == 0

    async def test_the_means_trend(self, db_session):
        budget, _ = await _household(db_session)
        rows = await means_months(ReportService(db_session), budget.id, date.today())
        month = next(r for r in rows if r["month"] == _month())
        assert month["income"] == INCOME
        assert month["outflows"] == SPENDING


# ─── The budget never reads a class ──────────────────────────────────────────

JUN, JUL, AUG = (date(2026, m, 1) for m in (6, 7, 8))


class TestTheBudgetNeverReadsTheClass:
    async def test_moving_the_start_date_moves_no_budget_figure(self, db_session):
        """Ready to Assign, every envelope and the card walk are summed from
        rows, assignments and the card model — never from the class — and
        net worth from balances. So taking the card's start date away changes
        the class of its June rows and nothing on the budget page, no balance
        and no net worth, in the month they land or any after.

        The household: a 3,000 paycheck in June. Sapphire Visa joins on
        July 1 with June's history: a 600 purchase, and the card's 200 side of
        a payment whose checking side was filed to Card Bill (200 assigned).
        In July, 600 assigned to Groceries, 300 of groceries on the card, 300
        assigned to the card, a 400 payment from checking, and a 50 refund
        onto the card nobody filed.
        """
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Harborstone Checking")
        card = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
        )
        card.budget_start_date = JUL
        card_envelope = await ensure_payment_category(db_session, card)
        assert card_envelope is not None
        inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
        everyday = await create_category_group(db_session, budget, "Everyday")
        ready = await create_category(db_session, budget, inflow, "Ready to Assign")
        bill = await create_category(db_session, budget, everyday, "Card Bill")
        groceries = await create_category(db_session, budget, everyday, "Groceries")

        await create_transaction(
            db_session, budget, checking, "3000.00", date(2026, 6, 1), category=ready
        )
        june = [
            await create_transaction(db_session, budget, card, "-600.00", date(2026, 6, 10)),
            await create_transaction(db_session, budget, card, "200.00", date(2026, 6, 20)),
        ]
        await create_budget_assignment(db_session, budget, bill, JUN, "200.00")
        await create_transaction(
            db_session, budget, checking, "-200.00", date(2026, 6, 20), category=bill
        )
        await create_budget_assignment(db_session, budget, groceries, JUL, "600.00")
        await create_transaction(
            db_session, budget, card, "-300.00", date(2026, 7, 10), category=groceries
        )
        await create_budget_assignment(db_session, budget, card_envelope, JUL, "300.00")
        await create_transfer(db_session, budget, checking, card, "400.00", date(2026, 7, 20))
        refund = await create_transaction(db_session, budget, card, "50.00", date(2026, 7, 25))
        await db_session.flush()

        async def ledger() -> dict:
            services = make_services(db_session)
            accounts = AccountRepository(db_session)
            return {
                "budget": [
                    asdict(await services.budgets.get_budget_summary(budget.id, month))
                    for month in (JUN, JUL, AUG)
                ],
                "balances": [
                    await accounts.get_balance(checking.id),
                    await accounts.get_balance(card.id),
                ],
                "net_worth": await ReportService(db_session).net_worth_history(budget.id, 6),
            }

        before = await ledger()
        assert [await classes_of(db_session, r) for r in june] == [OPENING, OPENING]
        assert await classes_of(db_session, refund) == UNFILED_CREDIT

        card.budget_start_date = None
        await db_session.flush()

        assert [(await classes_of(db_session, r))[0] for r in june] == [
            ActivityClass.SPENDING.value,
            ActivityClass.TRANSFER_INTERNAL.value,
        ]
        assert await ledger() == before

        # And the balances are the ones the arithmetic says, so the equality
        # above is not two empty ledgers agreeing. Checking: 3,000 in, 200 and
        # 400 out. The card: owes 600 - 200 + 300 - 400 - 50 = 250.
        assert before["balances"] == [D("2400.00"), D("-250.00")]
