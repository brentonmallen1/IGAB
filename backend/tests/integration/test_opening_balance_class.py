"""A Starting Balance row is OPENING_BALANCE: where counting begins, not activity.

The class was reserved and nothing emitted it, so a row under the
Starting Balance payee took whatever class its shape gave it. A card linked
owing $1,200 counted that debt as SPENDING — an expense on Income vs Expenses,
an "Uncategorized" line on the Discretionary tab, a month of burn rate, and
"Starting Balance" as a top payee. A checking account opened with $2,500 filed
to Ready to Assign counted it as INCOME, so the first month of every budget
read as a raise.

What this pins, in order:

- the rule, read by both implementations (the joined one reports run, and the
  subquery oracle `class_agreement.py` holds it to), on every account shape;
- what it must NOT reach: reconciliation adjustments and the other bookkeeping
  names, a payee that merely starts with the name, and a transfer leg;
- where it sits: ahead of the tags and the tracked-account rules;
- the reports that stopped counting it, by hand-written figure;
- the one bounded gap: a plan report leaves out an opening someone filed to
  an envelope, while that envelope's Activity carries it;
- that the budget never reads a class: renaming the openings moves no figure
  on the budget page while it changes the class.

Every amount is invented and round enough to check on paper.
"""

from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import Transaction
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    ACTIVITY_CLASS_SUBQUERY,
    ACTIVITY_REASON,
    ACTIVITY_REASON_SUBQUERY,
    INCOME_ROW,
    ActivityClass,
    ActivityReason,
    LegFacts,
    apply_class_joins,
    rule_ladder,
)
from igab.domain.dates import add_months
from igab.domain.payee_names import (
    RECONCILIATION_ADJUSTMENT_PAYEE,
    STARTING_BALANCE_PAYEE,
)
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.card_payment import ensure_payment_category
from igab.services.money_moves_service import MoneyMovesService
from igab.services.report_basics import class_excluded_note, discretionary, means_months
from igab.services.report_service import ReportService

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
OPENING = (ActivityClass.OPENING_BALANCE.value, ActivityReason.STARTING_BALANCE.value)


def _today() -> date:
    # Read when a test runs, from the clock the services read.
    return date.today()


async def _classes(db_session, txn: Transaction) -> tuple[str, str]:
    """(class, reason) for one row, from BOTH implementations — which must
    agree, or this raises before any caller asserts on the answer."""
    joined = (
        await db_session.execute(
            apply_class_joins(
                select(Transaction.id, ACTIVITY_CLASS, ACTIVITY_REASON).where(
                    Transaction.id == txn.id
                )
            )
        )
    ).one()
    oracle = (
        await db_session.execute(
            select(Transaction.id, ACTIVITY_CLASS_SUBQUERY, ACTIVITY_REASON_SUBQUERY).where(
                Transaction.id == txn.id
            )
        )
    ).one()
    assert (joined[1], joined[2]) == (oracle[1], oracle[2]), (
        f"joined says {joined[1:]}, the subquery oracle says {oracle[1:]}"
    )
    return joined[1], joined[2]


class World:
    def __init__(self, **kw):
        self.__dict__.update(kw)


async def _world(db_session):
    """One of every account shape a starting balance lands on."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
    everyday = await create_category_group(db_session, budget, "Everyday")
    return World(
        budget=budget,
        everyday=everyday,
        checking=await create_account(db_session, budget, "Harborstone Checking"),
        savings=await create_account(
            db_session, budget, "Harborstone Reserve", account_type="savings"
        ),
        card=await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
        ),
        loan=await create_account(
            db_session, budget, "Harborstone Auto Loan", account_type="auto_loan", on_budget=False
        ),
        brokerage=await create_account(
            db_session,
            budget,
            "Cascade Point Brokerage",
            account_type="investment",
            on_budget=False,
        ),
        ready=await create_category(db_session, budget, inflow, "Ready to Assign"),
        groceries=await create_category(db_session, budget, everyday, "Groceries"),
        starting=await create_payee(db_session, budget, STARTING_BALANCE_PAYEE),
    )


# ─── The rule ────────────────────────────────────────────────────────────────

#: (account, amount, filed to Ready to Assign?, the class the same row takes
#: under any other payee). The last column is what each opening used to count
#: as — written out so the change is visible row by row.
SHAPES = [
    pytest.param("checking", "2500.00", True, ActivityClass.INCOME, id="checking, filed to RTA"),
    pytest.param("checking", "2500.00", False, ActivityClass.INCOME, id="checking, uncategorized"),
    pytest.param("savings", "3000.00", True, ActivityClass.INCOME, id="on-budget savings"),
    pytest.param("card", "-1200.00", False, ActivityClass.SPENDING, id="card owing"),
    pytest.param("loan", "-9000.00", False, ActivityClass.DEBT_INTEREST, id="tracked loan"),
    pytest.param(
        "brokerage", "12000.00", False, ActivityClass.INVESTMENT_RETURN, id="tracked investment"
    ),
]


class TestTheRule:
    @pytest.mark.parametrize(("account", "amount", "filed", "otherwise"), SHAPES)
    async def test_a_starting_balance_is_an_opening_on_every_account(
        self, db_session, account, amount, filed, otherwise
    ):
        w = await _world(db_session)
        opening = await create_transaction(
            db_session,
            w.budget,
            getattr(w, account),
            amount,
            _today(),
            payee=w.starting,
            category=w.ready if filed else None,
        )
        assert await _classes(db_session, opening) == OPENING

    @pytest.mark.parametrize(("account", "amount", "filed", "otherwise"), SHAPES)
    async def test_it_is_the_name_that_decides(self, db_session, account, amount, filed, otherwise):
        """The same row under another payee takes the class its shape gives —
        which is exactly what every opening used to count as."""
        w = await _world(db_session)
        other = await create_payee(db_session, w.budget, "Opening Deposit")
        row = await create_transaction(
            db_session,
            w.budget,
            getattr(w, account),
            amount,
            _today(),
            payee=other,
            category=w.ready if filed else None,
        )
        assert (await _classes(db_session, row))[0] == otherwise.value

    async def test_the_partition_stays_total(self, db_session):
        w = await _world(db_session)
        for account, amount in (("checking", "2500.00"), ("card", "-1200.00"), ("loan", "-9000")):
            await create_transaction(
                db_session, w.budget, getattr(w, account), amount, _today(), payee=w.starting
            )
        await assert_activity_class_partition(db_session, w.budget.id)


class TestWhatItMustNotReach:
    @pytest.mark.parametrize(
        ("name", "account", "amount", "expected"),
        [
            # On a cash account an adjustment can stand for spending nobody
            # recorded, so it keeps the class its shape gives it.
            (RECONCILIATION_ADJUSTMENT_PAYEE, "checking", "-35.00", ActivityClass.SPENDING),
            (RECONCILIATION_ADJUSTMENT_PAYEE, "checking", "35.00", ActivityClass.INCOME),
            (RECONCILIATION_ADJUSTMENT_PAYEE, "card", "-50.00", ActivityClass.SPENDING),
            (RECONCILIATION_ADJUSTMENT_PAYEE, "loan", "-20.00", ActivityClass.DEBT_INTEREST),
            ("Manual Balance Adjustment", "checking", "-15.00", ActivityClass.SPENDING),
            ("Manual Balance Adjustment", "brokerage", "40.00", ActivityClass.INVESTMENT_RETURN),
        ],
        ids=[
            "reconcile out, checking",
            "reconcile in, checking",
            "reconcile, card",
            "reconcile, tracked loan",
            "manual, checking",
            "manual, tracked investment",
        ],
    )
    async def test_the_other_bookkeeping_names_keep_their_class(
        self, db_session, name, account, amount, expected
    ):
        w = await _world(db_session)
        payee = await create_payee(db_session, w.budget, name)
        row = await create_transaction(
            db_session, w.budget, getattr(w, account), amount, _today(), payee=payee
        )
        assert (await _classes(db_session, row))[0] == expected.value

    @pytest.mark.parametrize(
        "name",
        ["Starting Balance Cafe", "The Starting Balance", "Starting Balances"],
    )
    async def test_the_name_must_match_exactly(self, db_session, name):
        w = await _world(db_session)
        cafe = await create_payee(db_session, w.budget, name)
        row = await create_transaction(
            db_session, w.budget, w.checking, "-12.00", _today(), payee=cafe
        )
        assert await _classes(db_session, row) == (
            ActivityClass.SPENDING.value,
            ActivityReason.DEFAULT_SPENDING.value,
        )

    async def test_a_memo_is_not_a_payee(self, db_session):
        """The sample budget writes "Starting balance" as a memo too. Only the
        payee decides."""
        w = await _world(db_session)
        row = await create_transaction(
            db_session, w.budget, w.checking, "-12.00", _today(), memo="Starting balance"
        )
        assert (await _classes(db_session, row))[0] == ActivityClass.SPENDING.value

    async def test_a_payee_less_row_is_not_an_opening(self, db_session):
        """The joined reading compares a NULL name: it must read "no", not
        UNKNOWN, or the row would drop through a CASE arm by luck."""
        w = await _world(db_session)
        row = await create_transaction(db_session, w.budget, w.checking, "80.00", _today())
        assert (await _classes(db_session, row))[0] == ActivityClass.INCOME.value

    async def test_a_transfer_is_never_an_opening(self, db_session):
        """An opening someone later linked to the move that funded it IS that
        move. Between two budget accounts it is internal; its partner leg says
        the same."""
        w = await _world(db_session)
        out_leg, in_leg = await create_transfer(
            db_session, w.budget, w.checking, w.savings, "500.00", _today()
        )
        in_leg.payee_id = w.starting.id
        await db_session.flush()
        for leg in (in_leg, out_leg):
            assert await _classes(db_session, leg) == (
                ActivityClass.TRANSFER_INTERNAL.value,
                ActivityReason.INTERNAL_TRANSFER.value,
            )

    async def test_a_linked_opening_on_a_tracked_account_takes_the_transfer_rules(self, db_session):
        """The brokerage was opened by a move from checking: the checking leg
        is savings by where the money went, not an opening by its partner's
        name."""
        w = await _world(db_session)
        out_leg, in_leg = await create_transfer(
            db_session, w.budget, w.checking, w.brokerage, "1000.00", _today()
        )
        in_leg.payee_id = w.starting.id
        await db_session.flush()
        assert (await _classes(db_session, out_leg))[0] == ActivityClass.SAVINGS.value
        assert (await _classes(db_session, in_leg))[0] == ActivityClass.TRANSFER_INTERNAL.value


class TestWhereItSits:
    """First: ahead of the tags, which describe money that moved, and ahead of
    the tracked-account rules, which would call a loan's principal interest."""

    async def test_it_is_rule_one_of_the_ladder(self):
        first = rule_ladder()[0]
        assert (first.cls, first.reason) == (
            ActivityClass.OPENING_BALANCE,
            ActivityReason.STARTING_BALANCE,
        )
        assert first.tag_key is None

    @pytest.mark.parametrize(
        ("tag", "amount"),
        [
            # Filed to a Savings envelope, an opening deposit would have read
            # as savings drawn back out.
            ("savings", "2500.00"),
            # Filed to a Debt principal envelope, a card's opening debt would
            # have read as this month's debt payment — Cost of living and all.
            ("debt_principal", "-1200.00"),
        ],
    )
    async def test_it_beats_a_tag(self, db_session, tag, amount):
        w = await _world(db_session)
        category = await create_category(db_session, w.budget, w.everyday, "Tagged")
        await tag_with_system_tags(db_session, category, tag)
        account = w.checking if D(amount) > 0 else w.card
        row = await create_transaction(
            db_session, w.budget, account, amount, _today(), payee=w.starting, category=category
        )
        assert await _classes(db_session, row) == OPENING

    async def test_the_guide_asks_the_same_ladder(self, db_session):
        """The explorer's FROM-less CASE over literal facts: a starting
        balance is an opening on any account, and a transfer leg carrying the
        name is still the transfer."""
        service = MoneyMovesService(db_session)
        plain = LegFacts(
            own_on_budget=False,
            own_is_liability=True,
            transfer_leg=False,
            starting_balance=True,
            tracked_counterpart=False,
            counterpart_is_liability=False,
            counterpart_counts_as_savings=True,
            categorized=False,
            savings_sent_out=False,
            tagged_debt=False,
            in_system_group=False,
            amount_positive=False,
        )
        assert await service.classify(plain) == (
            ActivityClass.OPENING_BALANCE,
            ActivityReason.STARTING_BALANCE,
        )
        linked = replace(plain, own_on_budget=True, own_is_liability=False, transfer_leg=True)
        assert await service.classify(linked) == (
            ActivityClass.TRANSFER_INTERNAL,
            ActivityReason.INTERNAL_TRANSFER,
        )


# ─── The reports that stopped counting it ────────────────────────────────────


async def _household(db_session, when: date):
    """A household whose first month holds its openings.

    Counted: a $3,000 paycheck, $400 of Groceries (tagged Essential) and
    $150 of Dining Out on the card (untagged, so discretionary).

    Openings, counted nowhere: checking opened with $2,500 filed to Ready to
    Assign, the card linked owing $1,200, a tracked loan opened at $9,000.
    """
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    card = await create_account(
        db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
    )
    loan = await create_account(
        db_session, budget, "Harborstone Auto Loan", account_type="auto_loan", on_budget=False
    )
    inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
    everyday = await create_category_group(db_session, budget, "Everyday")
    ready = await create_category(db_session, budget, inflow, "Ready to Assign")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    dining = await create_category(db_session, budget, everyday, "Dining Out")
    await tag_with_system_tags(db_session, groceries, "essential")

    starting = await create_payee(db_session, budget, STARTING_BALANCE_PAYEE)
    employer = await create_payee(db_session, budget, "Northwind Payserv")
    grocer = await create_payee(db_session, budget, "Corner Market")
    bistro = await create_payee(db_session, budget, "Thai Garden")

    openings = [
        await create_transaction(
            db_session, budget, checking, "2500.00", when, payee=starting, category=ready
        ),
        await create_transaction(db_session, budget, card, "-1200.00", when, payee=starting),
        await create_transaction(db_session, budget, loan, "-9000.00", when, payee=starting),
    ]
    await create_transaction(
        db_session, budget, checking, "3000.00", when, payee=employer, category=ready
    )
    await create_transaction(
        db_session, budget, checking, "-400.00", when, payee=grocer, category=groceries
    )
    await create_transaction(
        db_session, budget, card, "-150.00", when, payee=bistro, category=dining
    )
    return budget, openings


INCOME = D("3000.00")
#: Groceries 400 + Dining Out 150.
SPENDING = D("550.00")
#: Dining Out alone: Groceries is Essential.
DISCRETIONARY = D("150.00")


class TestTheReportsThisMonth:
    """Everything dated today, so every window — this calendar month, the
    trailing thirty days — holds the same rows whatever day it is."""

    async def test_income_vs_expenses(self, db_session):
        budget, _ = await _household(db_session, _today())
        month = (await ReportService(db_session).income_vs_expense(budget.id, months=1))[-1]
        assert month["income"] == INCOME, "the checking opening read as income"
        assert month["expenses"] == SPENDING, "the card's opening debt read as an expense"

    async def test_the_overview_and_burn_rate(self, db_session):
        budget, _ = await _household(db_session, _today())
        today = _today()
        reports = ReportService(db_session)
        cards = await reports.dashboard_metrics(budget.id, today.replace(day=1), today, today)
        assert cards["income_this_month"] == INCOME
        assert cards["expenses_this_month"] == SPENDING
        assert cards["burn_rate_30"] == SPENDING
        burn = await reports.burn_rate(budget.id, months=1, today=today)
        assert burn[-1]["rolling_30"] == SPENDING

    async def test_the_savings_rate_divides_by_real_income(self, db_session):
        budget, _ = await _household(db_session, _today())
        rate = await ReportService(db_session).savings_rate(budget.id, months=1)
        assert rate["summary"]["income"] == INCOME
        assert rate["summary"]["spending"] == SPENDING

    async def test_the_sankey_draws_neither_side_of_an_opening(self, db_session):
        budget, _ = await _household(db_session, _today())
        today = _today()
        sankey = await ReportService(db_session).cash_flow_sankey(
            budget.id, today.replace(day=1), today
        )
        assert sankey["total_income"] == INCOME
        assert sankey["total_expense"] == SPENDING
        assert sankey["total_spending"] == SPENDING
        names = {n["name"] for n in sankey["nodes"]}
        assert STARTING_BALANCE_PAYEE not in names
        assert "Uncategorized" not in names

    async def test_starting_balance_is_not_a_top_payee(self, db_session):
        budget, _ = await _household(db_session, _today())
        today = _today()
        payees, total, count, _ = await ReportService(db_session).payee_analysis(
            budget.id, today.replace(day=1), today
        )
        assert {p["payee_name"] for p in payees} == {"Corner Market", "Thai Garden"}
        assert (total, count) == (SPENDING, 2)

    async def test_income_rows_hold_no_opening(self, db_session):
        """`INCOME_ROW` is what Income by Source and both Sankey modes read."""
        budget, openings = await _household(db_session, _today())
        rows = (
            await db_session.execute(
                apply_class_joins(
                    select(Transaction.id).where(Transaction.budget_id == budget.id, INCOME_ROW)
                )
            )
        ).all()
        assert len(rows) == 1
        assert openings[0].id not in {r.id for r in rows}


def _last_month() -> date:
    """Day 6 of last month: inside the last complete month whatever today is."""
    return add_months(_today().replace(day=1), -1) + timedelta(days=5)


class TestTheReportsOverCompleteMonths:
    async def test_discretionary_has_no_uncategorized_line(self, db_session):
        budget, _ = await _household(db_session, _last_month())
        report = await discretionary(ReportService(db_session), budget.id, 1)
        assert report["tagged"] is True
        assert report["total"] == DISCRETIONARY
        assert report["spending_total"] == SPENDING
        groups = {g["group_name"]: g["total"] for g in report["groups"]}
        assert groups == {"Everyday": DISCRETIONARY}, "the card's opening debt was a line here"

    async def test_the_discretionary_drill_opens_no_opening(self, db_session):
        """The rows behind the figure are the same predicate, so the drill —
        as `DiscretionaryReport` sends it — cannot list the opening the figure
        no longer counts, and its "no category" drill is empty."""
        budget, openings = await _household(db_session, _last_month())
        report = await discretionary(ReportService(db_session), budget.id, 1)
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
        assert (count, -total) == (1, DISCRETIONARY)
        assert not {r.id for r in rows} & {o.id for o in openings}
        _, count, total = await repo.list_for_budget(budget.id, no_category=True, **drill)
        assert (count, total) == (0, D("0"))

    async def test_the_means_trend(self, db_session):
        budget, _ = await _household(db_session, _last_month())
        rows = await means_months(ReportService(db_session), budget.id, _today())
        month = next(r for r in rows if r["month"] == _last_month().replace(day=1))
        assert month["income"] == INCOME
        assert month["outflows"] == SPENDING


class TestTheExcludedNote:
    async def test_an_opening_is_never_named_as_left_out(self):
        """The note's remedy is "Include savings & debt payments", which can
        never add a starting balance back — so it is not named, like an
        internal transfer. A savings row beside it still is."""

        class Row:
            def __init__(self, cls, amount):
                self.cls, self.id, self.amount = cls, "cat", D(amount)

        opening = Row(ActivityClass.OPENING_BALANCE.value, "-1200.00")
        assert class_excluded_note([opening], scoped=True) is None
        saved = Row(ActivityClass.SAVINGS.value, "-100.00")
        note = class_excluded_note([opening, saved], scoped=True)
        assert [n["activity_class"] for n in note or []] == [ActivityClass.SAVINGS.value]


class TestThePlanReportsLeaveAFiledOpeningOut:
    async def test_the_gap_to_the_envelope_is_exactly_the_opening(self, db_session):
        """The one place a report and the budget page part over an opening.

        Checking opens overdrawn by 1,200 and someone files that opening to
        an "Old Overdraft" envelope, assigning 1,200 to it. The envelope's
        Activity carries the row, as it carries any row filed there. The plan
        reports ask what was SPENT, and an opening is not spending, so they
        read 0 — the gap is the opening, and nothing else. `planned_spend_filter`
        says why that is bounded; this fails if the gap ever widens.
        """
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Harborstone Checking")
        everyday = await create_category_group(db_session, budget, "Everyday")
        overdraft = await create_category(db_session, budget, everyday, "Old Overdraft")
        dining = await create_category(db_session, budget, everyday, "Dining Out")
        starting = await create_payee(db_session, budget, STARTING_BALANCE_PAYEE)
        today = _today()
        first = today.replace(day=1)
        await create_budget_assignment(db_session, budget, overdraft, first, "1200.00")
        await create_budget_assignment(db_session, budget, dining, first, "200.00")
        await create_transaction(
            db_session, budget, checking, "-1200.00", today, payee=starting, category=overdraft
        )
        await create_transaction(db_session, budget, checking, "-80.00", today, category=dining)

        summary = await services.budgets.get_budget_summary(budget.id, first)
        activity = {c.category_id: c.activity for c in summary.category_balances}
        assert activity[overdraft.id] == D("-1200.00")
        assert activity[dining.id] == D("-80.00")

        reports = ReportService(db_session)
        bva = await reports.budget_vs_actual(budget.id, first, today)
        variance = await reports.cumulative_variance(budget.id, months=1)
        pvr = await reports.plan_vs_reality(budget.id, months=1)
        assert bva["total_spent"] == D("80.00")
        assert variance[-1]["actual_spent"] == D("80.00")
        assert pvr["total_spent"] == D("80.00")


# ─── The budget never reads a class ──────────────────────────────────────────

JUN, JUL, AUG = (date(2026, m, 1) for m in (6, 7, 8))


class TestTheBudgetNeverReadsTheClass:
    async def test_renaming_the_openings_moves_no_budget_figure(self, db_session):
        """Ready to Assign, every envelope and the card are summed from rows,
        assignments and the card model — never from the class. So pointing
        both openings at another payee changes their class and nothing on the
        budget page, in the month they land or any after.

        The household: checking opens with 2,500 filed to Ready to Assign, the
        card is linked owing 1,200. A 3,000 paycheck, 600 assigned to
        Groceries, 300 of groceries on the card, 400 assigned to the card and
        a 500 payment from checking.
        """
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Harborstone Checking")
        card = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
        )
        card_envelope = await ensure_payment_category(db_session, card)
        assert card_envelope is not None
        inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
        everyday = await create_category_group(db_session, budget, "Everyday")
        ready = await create_category(db_session, budget, inflow, "Ready to Assign")
        groceries = await create_category(db_session, budget, everyday, "Groceries")
        starting = await create_payee(db_session, budget, STARTING_BALANCE_PAYEE)

        openings = [
            await create_transaction(
                db_session,
                budget,
                checking,
                "2500.00",
                date(2026, 6, 1),
                payee=starting,
                category=ready,
            ),
            await create_transaction(
                db_session, budget, card, "-1200.00", date(2026, 6, 1), payee=starting
            ),
        ]
        await create_transaction(
            db_session, budget, checking, "3000.00", date(2026, 7, 1), category=ready
        )
        await create_budget_assignment(db_session, budget, groceries, JUL, "600.00")
        await create_transaction(
            db_session, budget, card, "-300.00", date(2026, 7, 10), category=groceries
        )
        await create_budget_assignment(db_session, budget, card_envelope, JUL, "400.00")
        await create_transfer(db_session, budget, checking, card, "500.00", date(2026, 7, 20))
        await db_session.flush()

        async def budget_page() -> list[dict]:
            services = make_services(db_session)
            return [
                asdict(await services.budgets.get_budget_summary(budget.id, month))
                for month in (JUN, JUL, AUG)
            ]

        before = await budget_page()
        assert [await _classes(db_session, o) for o in openings] == [OPENING, OPENING]

        other = await create_payee(db_session, budget, "Opening Deposit")
        for opening in openings:
            opening.payee_id = other.id
        await db_session.flush()

        assert [(await _classes(db_session, o))[0] for o in openings] == [
            ActivityClass.INCOME.value,
            ActivityClass.SPENDING.value,
        ]
        assert await budget_page() == before

        # And the figures are the ones the arithmetic says, so the equality
        # above is not two empty pages agreeing. Ready to Assign in August:
        # 2,500 + 3,000 in, 600 + 400 assigned.
        august = before[-1]
        assert august["to_be_assigned"] == D("4500.00")
        visa = next(c for c in august["cards"] if c["account_id"] == card.id)
        # Owes 1,200 + 300 - 500 = 1,000.
        assert visa["balance"] == D("-1000.00")
