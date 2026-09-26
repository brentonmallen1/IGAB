"""Discretionary: spending outside Cost of living.

The two necessity tiers answer "what leaves the account whether or not we
feel like it". This is the rest of the spending — what the household chose —
and it is the complement of the wide tier WITHIN THE SPENDING CLASS, not the
complement of the tier. `DISCRETIONARY_ROW` explains why that distinction is
the whole design: the tiers carry debt principal, so their complement would
let loan proceeds in, and "spending minus Cost of living" subtracts row sets
that differ in class and sign convention.

**Every `expect` figure here is written by hand.** Deriving them from the
queries would make each assertion a tautology. The amounts are round enough
to check on paper, and invented, like everything in this repository.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from igab.db.models import Account, Category, Transaction
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    ActivityClass,
    NecessityTier,
    apply_class_joins,
    tier_scope,
)
from igab.domain.dates import add_months, month_end
from igab.repositories.tag_repo import seed_system_tags
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import CLASS_TOTAL_ROW
from igab.repositories.txn_query import TransactionFilters, build_where
from igab.services.report_basics import cost_of_living, discretionary
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
    create_user,
    tag_with_system_tags,
)

D = Decimal


# Read when a test RUNS, from the clock the services read — see
# test_necessity_tiers.py for the midnight bug a module-level date caused.
def _today() -> date:
    return date.today()


def _first_of_last_month() -> date:
    return add_months(_today().replace(day=1), -1)


def _last_month() -> date:
    """Day 6 of last month: inside the last complete month whatever today is."""
    return _first_of_last_month() + timedelta(days=5)


@dataclass(frozen=True)
class Expected:
    """What the household below must read. Hand-computed."""

    #: Dining Out 300 - 40 refund + 120 on the card + 70 split leg = 450;
    #: Coffee 50; Hobbies 150; the uncategorized purchase 75.
    discretionary: Decimal
    #: Rent 1,200 + Electric 200 + Streaming 60 + the split's Rent leg 30.
    cost_of_living_spending: Decimal
    #: Every SPENDING row: the two above, and nothing else.
    spending: Decimal


EXPECTED = Expected(
    discretionary=D("725.00"),
    cost_of_living_spending=D("1490.00"),
    spending=D("2215.00"),
)


async def _household(db_session, owner=None):
    """One month of a household, built to put every trap in reach.

    Counted: untagged spending (Dining Out, Coffee, Hobbies), a refund netting
    against it, a card charge, a split leg, and an uncategorized purchase.

    Not counted: Essential- and Cost-of-living-tagged spending, the split's
    Essential leg, a card payment, a move between two budget accounts, money
    sent to savings from a Savings envelope and plainly to a savings account,
    a car payment into a tracked loan, $5,000 of loan proceeds, a paycheck, an
    uncategorized inflow, a purchase on an off-budget account filed to Dining
    Out, a pending charge, a deleted one, and one in the running month.
    """
    user = owner or await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    reserve = await create_account(db_session, budget, "Harborstone Reserve")
    card = await create_account(
        db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
    )
    hysa = await create_account(
        db_session, budget, "Cascade Point HYSA", on_budget=False, counts_as_savings=True
    )
    car_loan = await create_account(
        db_session, budget, "Harborstone Auto Loan", account_type="auto_loan", on_budget=False
    )
    tracking = await create_account(
        db_session, budget, "Harborstone Brokerage", on_budget=False, counts_as_savings=False
    )

    income = await create_category_group(db_session, budget, "Income", is_system=True)
    bills = await create_category_group(db_session, budget, "Bills")
    everyday = await create_category_group(db_session, budget, "Everyday")
    fun = await create_category_group(db_session, budget, "Fun")
    debt = await create_category_group(db_session, budget, "Debt")
    goals = await create_category_group(db_session, budget, "Savings Goals")

    ready = await create_category(db_session, budget, income, "Ready to Assign")
    rent = await create_category(db_session, budget, bills, "Rent")
    electric = await create_category(db_session, budget, bills, "Electric")
    dining = await create_category(db_session, budget, everyday, "Dining Out")
    coffee = await create_category(db_session, budget, everyday, "Coffee")
    streaming = await create_category(db_session, budget, fun, "Streaming")
    hobbies = await create_category(db_session, budget, fun, "Hobbies")
    car = await create_category(db_session, budget, debt, "Car Payment")
    investing = await create_category(db_session, budget, goals, "Investing")

    await seed_system_tags(db_session, budget.id)
    await tag_with_system_tags(db_session, rent, "essential")
    await tag_with_system_tags(db_session, electric, "essential")
    await tag_with_system_tags(db_session, streaming, "cost_of_living")
    # Savings, sent out by default: its outflows class SAVINGS by rule 2, so
    # "untagged for Cost of living" alone would have counted them.
    await tag_with_system_tags(db_session, investing, "savings")

    when = _last_month()

    async def spend(account, amount, category=None, **kw):
        return await create_transaction(
            db_session, budget, account, amount, when, category=category, **kw
        )

    # Counted.
    await spend(checking, "-300.00", dining)
    await spend(checking, "40.00", dining)  # a refund nets
    await spend(card, "-120.00", dining)  # a card charge is spending
    await spend(checking, "-50.00", coffee)
    await spend(checking, "-150.00", hobbies)
    await spend(checking, "-75.00")  # uncategorized: its own line
    parent = await spend(checking, "-100.00", is_split=True)
    await spend(checking, "-70.00", dining, parent_transaction_id=parent.id)
    await spend(checking, "-30.00", rent, parent_transaction_id=parent.id)

    # Cost of living: counted there, not here.
    await spend(checking, "-1200.00", rent)
    await spend(checking, "-200.00", electric)
    await spend(checking, "-60.00", streaming)

    # Not spending at all.
    await create_transfer(db_session, budget, checking, card, "500.00", when)  # card payment
    await create_transfer(db_session, budget, checking, reserve, "400.00", when)  # transfer
    await create_transfer(db_session, budget, checking, hysa, "250.00", when)  # savings
    await create_transfer(
        db_session, budget, checking, tracking, "200.00", when, category=investing
    )  # savings, by its envelope
    await create_transfer(
        db_session, budget, checking, car_loan, "340.00", when, category=car
    )  # debt principal
    await create_transfer(db_session, budget, car_loan, checking, "5000.00", when)  # proceeds
    await spend(checking, "3000.00", ready)  # income
    await spend(checking, "25.00")  # uncategorized inflow is income
    await spend(tracking, "-500.00", dining)  # an off-budget account

    # Spending, but not in these rows.
    await spend(checking, "-99.00", dining, cleared="pending")
    await spend(checking, "-88.00", dining, is_deleted=True)
    await create_transaction(db_session, budget, checking, "-999.00", _today(), category=dining)

    return budget


async def _report(db_session, budget, months: int = 1) -> dict:
    return await discretionary(ReportService(db_session), budget.id, months)


class TestWhatCounts:
    async def test_only_untagged_spending_net_of_refunds(self, db_session):
        budget = await _household(db_session)
        report = await _report(db_session, budget)

        assert report["tagged"] is True
        assert report["basis"] == "tag"
        assert report["months_averaged"] == 1
        assert report["total"] == EXPECTED.discretionary
        assert report["avg_monthly"] == EXPECTED.discretionary
        assert report["monthly_totals"] == [EXPECTED.discretionary]

    async def test_by_category_within_its_group(self, db_session):
        budget = await _household(db_session)
        report = await _report(db_session, budget)

        lines = {
            g["group_name"]: {c["category_name"]: c["total"] for c in g["categories"]}
            for g in report["groups"]
        }
        # Bills is absent: its only rows are Essential, the split's Rent leg
        # included. Debt and Savings Goals are absent by class. Streaming sits
        # in Fun and is Cost of living, so Fun is Hobbies alone.
        assert lines == {
            "Everyday": {"Dining Out": D("450.00"), "Coffee": D("50.00")},
            "Fun": {"Hobbies": D("150.00")},
            "Uncategorized": {},
        }
        totals = {g["group_name"]: g["total"] for g in report["groups"]}
        assert totals == {"Everyday": D("500.00"), "Fun": D("150.00"), "Uncategorized": D("75.00")}
        # Biggest first, lines and groups alike.
        assert [g["group_name"] for g in report["groups"]] == ["Everyday", "Fun", "Uncategorized"]
        assert [c["category_name"] for c in report["groups"][0]["categories"]] == [
            "Dining Out",
            "Coffee",
        ]

    async def test_uncategorized_spending_is_its_own_line(self, db_session):
        """The user's call: an unfiled purchase is discretionary until someone
        files it, and it is named rather than dropped. Its line carries no
        group id — the drill opens it by "no category", since an empty id list
        would filter nothing."""
        budget = await _household(db_session)
        report = await _report(db_session, budget)

        line = next(g for g in report["groups"] if g["group_id"] is None)
        assert line["group_name"] == "Uncategorized"
        assert line["total"] == D("75.00")
        assert line["categories"] == []
        assert all(g["group_id"] is not None for g in report["groups"] if g is not line)

    async def test_a_refund_nets(self, db_session):
        budget = await _household(db_session)
        before = (await _report(db_session, budget))["total"]
        dining = await _category(db_session, budget, "Dining Out")
        checking = await _account(db_session, budget, "Harborstone Checking")
        await create_transaction(
            db_session, budget, checking, "60.00", _last_month(), category=dining
        )

        after = await _report(db_session, budget)
        assert before - after["total"] == D("60.00")
        everyday = next(g for g in after["groups"] if g["group_name"] == "Everyday")
        assert everyday["categories"][0]["total"] == D("390.00")

    async def test_the_window_is_complete_months(self, db_session):
        """Two complete months: last month's 725 and 30 of coffee the month
        before. The running month's 999 is in neither."""
        budget = await _household(db_session)
        coffee = await _category(db_session, budget, "Coffee")
        checking = await _account(db_session, budget, "Harborstone Checking")
        earlier = add_months(_first_of_last_month(), -1) + timedelta(days=9)
        await create_transaction(db_session, budget, checking, "-30.00", earlier, category=coffee)

        report = await _report(db_session, budget, months=2)
        assert report["window_start"] == add_months(_first_of_last_month(), -1)
        assert report["window_end"] == month_end(_first_of_last_month())
        assert report["monthly_totals"] == [D("30.00"), D("725.00")]
        assert report["total"] == D("755.00")
        assert report["avg_monthly"] == D("377.50")


async def _add_transfer(db, budget, source, target, amount, category=None):
    await create_transfer(
        db,
        budget,
        await _account(db, budget, source),
        await _account(db, budget, target),
        amount,
        _last_month(),
        category=await _category(db, budget, category) if category else None,
    )


async def _add_row(db, budget, account, amount, category=None, when=None, **kw):
    await create_transaction(
        db,
        budget,
        await _account(db, budget, account),
        amount,
        when or _last_month(),
        category=await _category(db, budget, category) if category else None,
        **kw,
    )


#: One more of each thing that is not discretionary spending, added to a
#: household that already reads 725. Each must leave it at 725.
NOT_DISCRETIONARY = {
    "a transfer between budget accounts": lambda db, b: _add_transfer(
        db, b, "Harborstone Checking", "Harborstone Reserve", "90.00"
    ),
    "a card payment": lambda db, b: _add_transfer(
        db, b, "Harborstone Checking", "Sapphire Visa", "90.00"
    ),
    "a move to a savings account": lambda db, b: _add_transfer(
        db, b, "Harborstone Checking", "Cascade Point HYSA", "90.00"
    ),
    "money sent out of a Savings envelope": lambda db, b: _add_transfer(
        db, b, "Harborstone Checking", "Harborstone Brokerage", "90.00", "Investing"
    ),
    "a payment into a tracked loan": lambda db, b: _add_transfer(
        db, b, "Harborstone Checking", "Harborstone Auto Loan", "90.00", "Car Payment"
    ),
    "money drawn from a tracked loan": lambda db, b: _add_transfer(
        db, b, "Harborstone Auto Loan", "Harborstone Checking", "90.00"
    ),
    "income": lambda db, b: _add_row(db, b, "Harborstone Checking", "90.00", "Ready to Assign"),
    "an uncategorized inflow": lambda db, b: _add_row(db, b, "Harborstone Checking", "90.00"),
    "a purchase on an off-budget account": lambda db, b: _add_row(
        db, b, "Harborstone Brokerage", "-90.00", "Coffee"
    ),
    "Essential spending": lambda db, b: _add_row(db, b, "Harborstone Checking", "-90.00", "Rent"),
    "Cost of living spending": lambda db, b: _add_row(
        db, b, "Harborstone Checking", "-90.00", "Streaming"
    ),
    "a pending charge": lambda db, b: _add_row(
        db, b, "Harborstone Checking", "-90.00", "Coffee", cleared="pending"
    ),
    "a deleted charge": lambda db, b: _add_row(
        db, b, "Harborstone Checking", "-90.00", "Coffee", is_deleted=True
    ),
    "a charge in the running month": lambda db, b: _add_row(
        db, b, "Harborstone Checking", "-90.00", "Coffee", when=_today()
    ),
}


class TestWhatIsLeftOut:
    @pytest.mark.parametrize("case", list(NOT_DISCRETIONARY))
    async def test_it_leaves_the_figure_alone(self, db_session, case):
        budget = await _household(db_session)
        await NOT_DISCRETIONARY[case](db_session, budget)

        report = await _report(db_session, budget)
        assert report["total"] == EXPECTED.discretionary, case

    async def test_and_the_same_charge_on_a_budget_account_counts(self, db_session):
        """The control for the cases above: 90 of Coffee from checking moves
        the figure by exactly 90, so a case that left it alone did so because
        of what it was, not because nothing reaches the report."""
        budget = await _household(db_session)
        await _add_row(db_session, budget, "Harborstone Checking", "-90.00", "Coffee")

        report = await _report(db_session, budget)
        assert report["total"] == EXPECTED.discretionary + D("90.00")


class TestTheIdentity:
    """SPENDING = Cost of living's SPENDING rows + discretionary, row for row.

    Structural: both halves start from `CLASS_TOTAL_ROW`, ask one class, and
    split on one tag arm, negated. This pins it end to end, on a household
    whose every non-spending row is a trap."""

    async def test_spending_splits_into_the_two_halves(self, db_session):
        budget = await _household(db_session)
        report = await _report(db_session, budget)
        col_spending = await _cost_of_living_spending(db_session, budget, report)

        assert report["spending_total"] == EXPECTED.spending
        assert col_spending == EXPECTED.cost_of_living_spending
        assert report["total"] == EXPECTED.discretionary
        assert report["spending_total"] == col_spending + report["total"]

    async def test_it_is_not_spending_minus_cost_of_living(self, db_session):
        """Why the figure is its own predicate. Cost of living counts the
        $340 car payment by class, so subtracting it from spending reads 385
        where the household's discretionary spending is 725 — and a larger
        loan would drive the difference negative."""
        budget = await _household(db_session)
        report = await _report(db_session, budget)
        col = await cost_of_living(db_session, budget.id, months=1)

        assert col["avg_monthly_cost_of_living"] == D("1830.00")  # 1,490 + 340
        assert report["spending_total"] - col["avg_monthly_cost_of_living"] == D("385.00")
        assert report["total"] == EXPECTED.discretionary

    async def test_loan_proceeds_do_not_enter(self, db_session):
        """The trap a fourth `NecessityTier` would have sprung: the tiers'
        classes carry DEBT_PRINCIPAL, and money arriving from a tracked loan is
        that class. The household already took $5,000; take $5,000 more."""
        budget = await _household(db_session)
        checking = await _account(db_session, budget, "Harborstone Checking")
        loan = await _account(db_session, budget, "Harborstone Auto Loan")
        await create_transfer(db_session, budget, loan, checking, "5000.00", _last_month())

        report = await _report(db_session, budget)
        assert report["total"] == EXPECTED.discretionary
        assert report["spending_total"] == EXPECTED.spending


class TestTheBasis:
    async def test_nothing_tagged_serves_no_number(self, db_session):
        """Untagged, every category is "outside Cost of living" and the figure
        would be the whole burn rate under a name that says it was chosen."""
        budget = await create_budget(db_session, await create_user(db_session))
        checking = await create_account(db_session, budget, "Harborstone Checking")
        everyday = await create_category_group(db_session, budget, "Everyday")
        dining = await create_category(db_session, budget, everyday, "Dining Out")
        await seed_system_tags(db_session, budget.id)
        await create_transaction(
            db_session, budget, checking, "-300.00", _last_month(), category=dining
        )

        report = await _report(db_session, budget)
        assert report["tagged"] is False
        assert report["basis"] == "all"
        assert report["total"] is None
        assert report["avg_monthly"] is None
        assert report["spending_total"] is None
        assert report["monthly_totals"] == []
        assert report["groups"] == []
        # The window is still served, so the page can say which months.
        assert report["months_averaged"] == 1

    async def test_essential_alone_is_a_choice(self, db_session):
        """Essential ⊆ Cost of living, so tagging only Essential chooses the
        wide tier too — the same basis the Cost of Living report reads."""
        budget = await create_budget(db_session, await create_user(db_session))
        checking = await create_account(db_session, budget, "Harborstone Checking")
        bills = await create_category_group(db_session, budget, "Bills")
        rent = await create_category(db_session, budget, bills, "Rent")
        dining = await create_category(db_session, budget, bills, "Dining Out")
        await seed_system_tags(db_session, budget.id)
        await tag_with_system_tags(db_session, rent, "essential")
        await create_transaction(
            db_session, budget, checking, "-1200.00", _last_month(), category=rent
        )
        await create_transaction(
            db_session, budget, checking, "-80.00", _last_month(), category=dining
        )

        report = await _report(db_session, budget)
        col = await cost_of_living(db_session, budget.id, months=1)
        assert report["tagged"] is col["tagged"] is True
        assert report["total"] == D("80.00")


class TestTheDrillTotalsItsLine:
    """Every line, group and month opens the rows it totals — the drill sends
    the report's own predicate (`discretionary=True`) with exactly what
    `DiscretionaryReport` sends."""

    async def test_every_line_group_and_month(self, db_session):
        budget = await _household(db_session)
        report = await _report(db_session, budget)
        window = (report["window_start"], report["window_end"])

        assert await _drill(db_session, budget, window) == report["total"]
        for group in report["groups"]:
            if group["group_id"] is None:
                opened = await _drill(db_session, budget, window, no_category=True)
            else:
                ids = [UUID(c["category_id"]) for c in group["categories"]]
                opened = await _drill(db_session, budget, window, category_ids=ids)
            assert opened == group["total"], group["group_name"]
            for line in group["categories"]:
                ids = [UUID(line["category_id"])]
                opened = await _drill(db_session, budget, window, category_ids=ids)
                assert opened == line["total"], line["category_name"]
        for month, amount in zip(report["months"], report["monthly_totals"], strict=True):
            assert await _drill(db_session, budget, (month, month_end(month))) == amount

    async def test_without_the_flag_the_panel_overstates(self, db_session):
        """Pins what the flag is for. A line's category ids say which
        envelopes, not which rows: Everyday's ids alone also list the $500
        purchase on an off-budget account filed to Dining Out, which no
        discretionary figure counted."""
        budget = await _household(db_session)
        report = await _report(db_session, budget)
        window = (report["window_start"], report["window_end"])
        everyday = next(g for g in report["groups"] if g["group_name"] == "Everyday")
        ids = [UUID(c["category_id"]) for c in everyday["categories"]]

        # 500 of Everyday plus the 500 off-budget purchase filed to Dining Out.
        assert await _drill(db_session, budget, window, category_ids=ids, flag=False) == D(
            "1000.00"
        )
        assert await _drill(db_session, budget, window, category_ids=ids) == D("500.00")

    async def test_the_flag_reaches_the_query_through_the_api(self, api_client, db_session):
        budget = await _household(db_session, api_client.test_user)
        resp = await api_client.get(
            f"/api/v1/{budget.id}/reports/discretionary", params={"months": 1}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert Decimal(str(body["total"])) == EXPECTED.discretionary
        fun = next(g for g in body["groups"] if g["group_name"] == "Fun")

        resp = await api_client.get(
            f"/api/v1/{budget.id}/transactions",
            params={
                "start_date": body["window_start"],
                "end_date": body["window_end"],
                "scope": "leaf",
                "posted_only": "true",
                "cash_flow_only": "true",
                "category_ids": ",".join(c["category_id"] for c in fun["categories"]),
                "discretionary": "true",
            },
        )
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["total_amount"])) == D("-150.00")

    def test_the_flag_asks_for_the_class_joins(self):
        """The predicate reads the class, and a class read without its joins
        is a cartesian product. Pure: no database."""
        plain = build_where(UUID(int=0), TransactionFilters(), scope="leaf")
        flagged = build_where(UUID(int=0), TransactionFilters(discretionary=True), scope="leaf")
        assert plain.class_joins is False
        assert flagged.class_joins is True
        assert len(flagged.where) == len(plain.where) + 1


# ── helpers ──────────────────────────────────────────────────────────────


async def _drill(
    db_session,
    budget,
    window: tuple[date, date],
    *,
    category_ids: list[UUID] | None = None,
    no_category: bool = False,
    flag: bool = True,
) -> Decimal:
    """The drill a line opens, as `DiscretionaryReport` sends it; the panel's
    own figure is the listing's served total."""
    _, _, total = await TransactionRepository(db_session).list_for_budget(
        budget.id,
        start_date=window[0],
        end_date=window[1],
        scope="leaf",
        posted_only=True,
        cash_flow_only=True,
        category_ids=category_ids,
        no_category=no_category,
        discretionary=flag,
    )
    return -total


async def _cost_of_living_spending(db_session, budget, report) -> Decimal:
    """The wide tier's SPENDING rows over the report's window, from the tier's
    own predicate — the other half of the identity."""
    q = apply_class_joins(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .select_from(Transaction)
        .where(
            Transaction.budget_id == budget.id,
            Transaction.date >= report["window_start"],
            Transaction.date <= report["window_end"],
            CLASS_TOTAL_ROW,
            ACTIVITY_CLASS == ActivityClass.SPENDING.value,
            tier_scope(NecessityTier.COST_OF_LIVING),
        )
    )
    return -Decimal((await db_session.execute(q)).scalar_one())


async def _category(db_session, budget, name: str):
    return (
        await db_session.execute(
            select(Category).where(Category.budget_id == budget.id, Category.name == name)
        )
    ).scalar_one()


async def _account(db_session, budget, name: str):
    return (
        await db_session.execute(
            select(Account).where(Account.budget_id == budget.id, Account.name == name)
        )
    ).scalar_one()
