"""Each activity-class rule, and the precedence between them.

The partition property itself (every row classified exactly once, sums
conserved) is asserted by assert_activity_class_partition in invariants.py and
runs on every fixture in the suite. What is checked here is that each rule
fires on the shape it is meant to, and that the ordering between them is the
intended one — a rule that quietly stops matching would still partition
correctly while putting money in the wrong bucket.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import Transaction
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    ACTIVITY_REASON,
    ActivityClass,
    ActivityReason,
    apply_class_joins,
    explain,
)
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_transfer,
    create_user,
)

TODAY = date.today()


class World:
    """A budget with one of every account shape the rules care about."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


async def _world(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    return World(
        budget=budget,
        checking=await create_account(db_session, budget, "Checking", on_budget=True),
        savings_acct=await create_account(db_session, budget, "Savings", on_budget=True),
        brokerage=await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        ),
        loan=await create_account(
            db_session, budget, "Auto Loan", account_type="loan", on_budget=False
        ),
        group=await create_category_group(db_session, budget, "Everyday"),
        income_group=await create_category_group(db_session, budget, "Inflow", is_system=True),
    )


async def _classify(db_session, txn: Transaction) -> tuple[str, str]:
    row = (
        await db_session.execute(
            # Transaction.id is not wanted; the class joins chain from it.
            apply_class_joins(
                select(Transaction.id, ACTIVITY_CLASS, ACTIVITY_REASON).where(
                    Transaction.id == txn.id
                )
            )
        )
    ).one()
    return row[1], row[2]


async def _transfer_payee(db_session, budget, account):
    return await PayeeRepository(db_session).find_or_create_transfer(
        budget.id, account.id, account.name
    )


class TestTransfersToTrackedAccounts:
    async def test_to_tracked_asset_is_savings(self, db_session):
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Investments")
        payee = await _transfer_payee(db_session, w.budget, w.brokerage)
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-500.00", TODAY, category=cat, payee=payee
        )
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.SAVINGS
        assert reason == ActivityReason.TRANSFER_TO_TRACKED_ASSET

    async def test_to_tracked_debt_is_principal(self, db_session):
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Car Payment")
        payee = await _transfer_payee(db_session, w.budget, w.loan)
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-400.00", TODAY, category=cat, payee=payee
        )
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.DEBT_PRINCIPAL
        assert reason == ActivityReason.TRANSFER_TO_TRACKED_DEBT

    async def test_works_for_an_orphaned_leg(self, db_session):
        """No partner link — the transfer payee is the only signal. This is the
        shape a YNAB import produces, and the one a real export is full of."""
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Investments")
        payee = await _transfer_payee(db_session, w.budget, w.brokerage)
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-500.00", TODAY, category=cat, payee=payee
        )
        assert txn.transfer_id is None
        assert (await _classify(db_session, txn))[0] == ActivityClass.SAVINGS


class TestInternalTransfers:
    async def test_uncategorized_leg_between_own_accounts(self, db_session):
        w = await _world(db_session)
        payee = await _transfer_payee(db_session, w.budget, w.savings_acct)
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-200.00", TODAY, payee=payee
        )
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.TRANSFER_INTERNAL
        assert reason == ActivityReason.INTERNAL_TRANSFER

    async def test_uncategorized_leg_to_a_tracked_account_is_savings(self, db_session):
        """Reversed deliberately. This asserted that without a category there
        was "no statement that this was saving" — but the account topology is
        the statement: the money left the budget and stayed in an asset the
        household owns. Treating the category as the signal made the savings
        rate read 0% for anyone whose transfers are uncategorized, which is
        most YNAB imports. Internal now means what it says: both legs inside
        the budget."""
        w = await _world(db_session)
        payee = await _transfer_payee(db_session, w.budget, w.brokerage)
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-500.00", TODAY, payee=payee
        )
        assert (await _classify(db_session, txn))[0] == ActivityClass.SAVINGS


class TestTrackedAccountActivity:
    async def test_dividend_is_investment_return_not_savings(self, db_session):
        """The distinction the savings rate depends on: growth inside a tracked
        account is not money the household saved."""
        w = await _world(db_session)
        payee = await create_payee(db_session, w.budget, "Dividend")
        txn = await create_transaction(
            db_session, w.budget, w.brokerage, "125.00", TODAY, payee=payee
        )
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.INVESTMENT_RETURN
        assert reason == ActivityReason.TRACKED_ASSET_ACTIVITY

    async def test_market_loss_is_also_investment_return(self, db_session):
        w = await _world(db_session)
        txn = await create_transaction(db_session, w.budget, w.brokerage, "-300.00", TODAY)
        assert (await _classify(db_session, txn))[0] == ActivityClass.INVESTMENT_RETURN

    async def test_interest_on_a_tracked_debt(self, db_session):
        w = await _world(db_session)
        txn = await create_transaction(db_session, w.budget, w.loan, "-45.00", TODAY)
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.DEBT_INTEREST
        assert reason == ActivityReason.TRACKED_DEBT_ACTIVITY


class TestIncomeAndSpending:
    async def test_uncategorized_inflow_is_income(self, db_session):
        w = await _world(db_session)
        payee = await create_payee(db_session, w.budget, "Employer")
        txn = await create_transaction(
            db_session, w.budget, w.checking, "3000.00", TODAY, payee=payee
        )
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.INCOME
        assert reason == ActivityReason.UNCATEGORIZED_INFLOW

    async def test_inflow_to_the_income_group_is_income(self, db_session):
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.income_group, "Ready to Assign")
        txn = await create_transaction(
            db_session, w.budget, w.checking, "3000.00", TODAY, category=cat
        )
        assert (await _classify(db_session, txn))[0] == ActivityClass.INCOME

    async def test_refund_to_an_ordinary_category_is_not_income(self, db_session):
        """A positive amount on a spending category is a refund. Calling it
        income would double-count it and inflate a savings rate's denominator;
        as spending it nets against that category instead."""
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Groceries")
        txn = await create_transaction(
            db_session, w.budget, w.checking, "40.00", TODAY, category=cat
        )
        assert (await _classify(db_session, txn))[0] == ActivityClass.SPENDING

    async def test_ordinary_purchase_is_spending(self, db_session):
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Groceries")
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-60.00", TODAY, category=cat
        )
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.SPENDING
        assert reason == ActivityReason.DEFAULT_SPENDING

    async def test_uncategorized_outflow_is_spending(self, db_session):
        w = await _world(db_session)
        txn = await create_transaction(db_session, w.budget, w.checking, "-25.00", TODAY)
        assert (await _classify(db_session, txn))[0] == ActivityClass.SPENDING


class TestTagsOverrideInference:
    async def _tag(self, db_session, budget, category, system_key):
        repo = TagRepository(db_session)
        tags = {t.system_key: t for t in await repo.list_for_budget(budget.id)}
        tag = tags.get(system_key)
        if tag is None:
            from .factories import create_tag

            tag = await create_tag(db_session, budget, system_key, system_key=system_key)
        await repo.set_category_tags(category.id, [tag.id])

    async def test_savings_tag_makes_plain_spending_savings(self, db_session):
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Emergency Fund")
        await self._tag(db_session, w.budget, cat, "savings")
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-500.00", TODAY, category=cat
        )
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.SAVINGS
        assert reason == ActivityReason.TAGGED_SAVINGS

    async def test_long_term_expense_does_not_disguise_a_payout_as_saving(self, db_session):
        """A sinking fund's monthly set-aside is a BudgetAssignment — a budget
        row, not a transaction — so there is nothing here for the classifier to
        protect. The only transaction the envelope ever sees is the payout, and
        the tag used to call that SAVINGS: the app said the household saved
        $2,340 in the month it paid its property tax, kept the bill out of every
        spending report, out of Cost of Living and out of the emergency-fund
        target, and left Budget vs Actual and Cumulative Variance showing a
        permanent phantom underspend.
        """
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Property Tax")
        await self._tag(db_session, w.budget, cat, "long_term_expense")
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-500.00", TODAY, category=cat
        )
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.SPENDING
        # And the explanation stops naming a tag the category does not carry.
        assert reason == ActivityReason.DEFAULT_SPENDING

    async def test_a_sinking_fund_transfer_to_a_tracked_account_is_still_saving(self, db_session):
        """Nothing is lost by dropping the tag from rule 1: a household that
        moves the set-aside into a real savings account still gets SAVINGS,
        from the rule that asks where the money WENT rather than what the
        category is called.
        """
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Property Tax")
        await self._tag(db_session, w.budget, cat, "long_term_expense")
        payee = await _transfer_payee(db_session, w.budget, w.brokerage)
        leg = await create_transaction(
            db_session, w.budget, w.checking, "-195.00", TODAY, category=cat, payee=payee
        )
        cls, reason = await _classify(db_session, leg)
        assert cls == ActivityClass.SAVINGS
        assert reason == ActivityReason.TRANSFER_TO_TRACKED_ASSET

    async def test_a_categorized_on_budget_transfer_from_a_sinking_fund_is_spending(
        self, db_session
    ):
        """The one shape this change makes noisier, named so it is a decision
        rather than a surprise.

        A categorized leg between two ON-budget accounts matches no transfer
        rule — rule 5 is gated on the leg being uncategorized, and rules 3 and
        4 need an off-budget counterpart — so it falls to the spending default.
        The `long_term_expense` tag used to catch it at rule 1.

        It is a narrow shape: `domain/transfers.py` only permits a category on
        a leg whose partner is OFF budget, so a row like this arrives from an
        import (a tracking account mapped on-budget) or from PATCH /accounts
        flipping `on_budget` under categorized legs, rather than from the app.

        It is NOT kept out of the reports. CASH_FLOW_ROW keeps categorized
        transfer legs — only UNcategorized on-budget legs are excluded — and
        the class totals behind the savings rate do not read CASH_FLOW_ROW at
        all. So the leg is spending everywhere spending is counted: the bounded
        divergence from an uncategorized leg is pinned at report level by
        `TestACategorizedOnBudgetLegIsSpending` below. Recorded here so the
        reading is deliberate.
        """
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Property Tax")
        await self._tag(db_session, w.budget, cat, "long_term_expense")
        payee = await _transfer_payee(db_session, w.budget, w.savings_acct)
        leg = await create_transaction(
            db_session, w.budget, w.checking, "-195.00", TODAY, category=cat, payee=payee
        )
        assert (await _classify(db_session, leg))[0] == ActivityClass.SPENDING

    async def test_the_savings_tag_still_makes_a_plain_outflow_saving(self, db_session):
        """The sibling behaviour that deliberately stays. Asked for directly —
        see `ReportService.savings_rate` — and it is a different claim from
        "this envelope holds money for a known annual bill".
        """
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Emergency Fund")
        await self._tag(db_session, w.budget, cat, "savings")
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-500.00", TODAY, category=cat
        )
        assert (await _classify(db_session, txn))[0] == ActivityClass.SAVINGS

    async def test_debt_tag_beats_a_tracked_asset_transfer(self, db_session):
        """Tag precedence: the user's explicit statement wins over what the
        counterpart account would otherwise imply."""
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Loan Payoff")
        await self._tag(db_session, w.budget, cat, "debt_principal")
        payee = await _transfer_payee(db_session, w.budget, w.brokerage)
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-500.00", TODAY, category=cat, payee=payee
        )
        cls, reason = await _classify(db_session, txn)
        assert cls == ActivityClass.DEBT_PRINCIPAL
        assert reason == ActivityReason.TAGGED_DEBT


class TestEdgeCases:
    async def test_zero_amount_is_spending_not_income(self, db_session):
        """`amount > 0` is strict, so a zero row must not drift into income."""
        w = await _world(db_session)
        txn = await create_transaction(db_session, w.budget, w.checking, "0.00", TODAY)
        assert (await _classify(db_session, txn))[0] == ActivityClass.SPENDING

    async def test_categorized_transfer_with_unresolvable_counterpart_keeps_its_meaning(
        self, db_session
    ):
        """A payee named like a transfer but not linked to an account (the
        pre-migration state) leaves the counterpart unknown. The row keeps the
        meaning its category gives it rather than vanishing into a neutral
        bucket."""
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Groceries")
        payee = await create_payee(db_session, w.budget, "Transfer : Somewhere")
        txn = await create_transaction(
            db_session, w.budget, w.checking, "-60.00", TODAY, category=cat, payee=payee
        )
        assert (await _classify(db_session, txn))[0] == ActivityClass.SPENDING

    async def test_income_on_a_tracked_account_is_not_budget_income(self, db_session):
        """An employer 401k contribution lands in a tracked account. It grows
        net worth but was never budgeted, so it must not inflate income."""
        w = await _world(db_session)
        txn = await create_transaction(db_session, w.budget, w.brokerage, "1000.00", TODAY)
        assert (await _classify(db_session, txn))[0] == ActivityClass.INVESTMENT_RETURN

    async def test_every_class_value_is_reachable_or_reserved(self):
        emitted = {
            cls for _, cls, _ in __import__("igab.domain.activity_class", fromlist=["RULES"]).RULES
        }
        emitted.add(ActivityClass.SPENDING)
        reserved = {ActivityClass.OPENING_BALANCE}
        assert set(ActivityClass) == emitted | reserved


class TestExplain:
    async def test_every_reason_has_copy(self):
        for reason in ActivityReason:
            assert explain(reason.value), f"{reason} has no user-facing text"

    async def test_unknown_reason_does_not_raise(self):
        assert explain("something_from_the_future")


class TestACategorizedOnBudgetLegIsSpending:
    """The bound on the one shape #182 made noisier, stated in report figures
    rather than a class assertion.

    A categorized leg between two on-budget accounts is spending in every
    report that counts spending — CASH_FLOW_ROW keeps categorized legs, and
    the class totals do not read it. The bound: it counts ONCE (its
    uncategorized partner leg is internal and counts nothing), and a
    `long_term_expense` tag makes no difference — the figures are those of
    the same leg filed to any category. If the bill is later paid from the
    receiving account under the same category, spending sees both; that is
    the cost of the shape, and why it is named here.
    """

    @pytest.mark.parametrize("tag", ["long_term_expense", None], ids=["sinking fund", "untagged"])
    async def test_it_counts_once_as_spending(self, db_session, tag):
        w = await _world(db_session)
        cat = await create_category(db_session, w.budget, w.group, "Property Tax")
        if tag:
            await seed_system_tags(db_session, w.budget.id)
            tags = TagRepository(db_session)
            await tags.set_category_tags(cat.id, [(await tags.get_system_tag(w.budget.id, tag)).id])
        today = date.today()
        await create_transfer(
            db_session, w.budget, w.checking, w.savings_acct, "195.00", today, category=cat
        )

        reports = ReportService(db_session)
        by_cat, total = await reports.spending_by_category(w.budget.id, today.replace(day=1), today)
        rate = await reports.savings_rate(w.budget.id, months=1)
        burn = await reports.burn_rate(w.budget.id, months=1)

        assert [(c["name"], c["total"]) for c in by_cat] == [("Property Tax", Decimal("195.00"))]
        assert total == Decimal("195.00")
        assert rate["summary"]["spending"] == Decimal("195.00")
        assert rate["summary"]["savings"] == Decimal("0")
        assert burn[-1]["rolling_30"] == Decimal("195.00")
