"""Income Split: every dollar that came in, in exactly one bucket.

The report sets a household's split beside the 50/30/20 rule. Its buckets are
read from the same rows four other reports read, so it is held here to each of
them: Needs to the Essentials headline, Wants to Cost of Living and
Discretionary, saved to the Savings Rate — and the buckets to income, to the
cent. Every place the existing reports could double-count when put side by
side (an untagged debt payment, loan proceeds, uncategorized spending) is a
case of its own below.

**Every expected figure is written by hand.** The household is invented and
its amounts are round enough to check on paper.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.domain.dates import add_months, complete_month_window, month_end
from igab.services.essentials import essentials_headline
from igab.services.income_split import income_split
from igab.services.report_basics import cost_of_living, discretionary, savings_contributors
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_liability,
    create_transaction,
    create_transfer,
    create_user,
    tag_with_system_tags,
)

D = Decimal


def _today() -> date:
    return date.today()


def _last_month() -> tuple[date, date]:
    first = add_months(_today().replace(day=1), -1)
    return first, month_end(first)


async def _household(db_session, owner=None):
    """One month of a household — last month — with every trap in reach.

    Take-home $7,000. Needs: a $2,100 mortgage into a tracked loan (Essential,
    minimum $2,000), $750 of groceries net of a $50 refund, and a $1,200 yearly
    car premium paid this month (Essential and Long-term expense). Wants: a
    $60 gym (Cost of living) and $500 of dining (untagged, $100 of it on the
    card). Savings & debt: $500 moved to the HYSA, a $350 car payment from an
    untagged envelope (minimum $300), and $50 sent to the car loan with no
    category at all. Uncategorized: a $30 purchase.

    Not counted anywhere: $1,000 of loan proceeds, a card payment, a pending
    and a deleted charge, a purchase on an off-budget account, and a charge in
    the running month.
    """
    user = owner or await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    hysa = await create_account(
        db_session, budget, "Cascade Point HYSA", on_budget=False, counts_as_savings=True
    )
    mortgage_acct = await create_account(
        db_session, budget, "Harborstone Mortgage", account_type="mortgage", on_budget=False
    )
    auto = await create_account(
        db_session, budget, "Harborstone Auto Loan", account_type="auto_loan", on_budget=False
    )
    brokerage = await create_account(
        db_session, budget, "Harborstone Brokerage", on_budget=False, counts_as_savings=False
    )
    await create_liability(
        db_session,
        budget,
        "Harborstone Mortgage",
        liability_type="mortgage",
        linked_account_id=mortgage_acct.id,
        minimum_payment=D("2000.00"),
    )
    await create_liability(
        db_session,
        budget,
        "Harborstone Auto Loan",
        liability_type="auto",
        linked_account_id=auto.id,
        minimum_payment=D("300.00"),
    )

    income = await create_category_group(db_session, budget, "Income", is_system=True)
    home = await create_category_group(db_session, budget, "Home")
    everyday = await create_category_group(db_session, budget, "Everyday")
    debt = await create_category_group(db_session, budget, "Debt")
    ready = await create_category(db_session, budget, income, "Ready to Assign")
    mortgage = await create_category(db_session, budget, home, "Mortgage")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    insurance = await create_category(db_session, budget, everyday, "Car insurance")
    gym = await create_category(db_session, budget, everyday, "Gym")
    dining = await create_category(db_session, budget, everyday, "Dining out")
    car = await create_category(db_session, budget, debt, "Car payment")

    await tag_with_system_tags(db_session, mortgage, "essential")
    await tag_with_system_tags(db_session, groceries, "essential")
    await tag_with_system_tags(db_session, insurance, "essential", "long_term_expense")
    await tag_with_system_tags(db_session, gym, "cost_of_living")

    # What the loans owed before last month — so a minimum is billable
    # against a balance, and the budget's history starts a year back.
    year_ago = add_months(_today().replace(day=1), -13)
    await create_transaction(db_session, budget, mortgage_acct, "-300000.00", year_ago)
    await create_transaction(db_session, budget, auto, "-20000.00", year_ago)

    when, _ = _last_month()
    when += timedelta(days=5)

    async def spend(account, amount, category=None, **kw):
        return await create_transaction(
            db_session, budget, account, amount, when, category=category, **kw
        )

    await spend(checking, "7000.00", ready)
    await create_transfer(
        db_session, budget, checking, mortgage_acct, "2100.00", when, category=mortgage
    )
    await spend(checking, "-800.00", groceries)
    await spend(checking, "50.00", groceries)  # a refund nets
    await spend(checking, "-1200.00", insurance)
    await spend(checking, "-60.00", gym)
    await spend(checking, "-400.00", dining)
    await spend(card, "-100.00", dining)
    await create_transfer(db_session, budget, checking, auto, "350.00", when, category=car)
    await create_transfer(db_session, budget, checking, auto, "50.00", when)  # no category
    await spend(checking, "-30.00")
    await create_transfer(db_session, budget, checking, hysa, "500.00", when)

    # Counted nowhere.
    await create_transfer(db_session, budget, auto, checking, "1000.00", when)  # proceeds
    await create_transfer(db_session, budget, checking, card, "100.00", when)  # card payment
    await spend(checking, "-99.00", dining, cleared="pending")
    await spend(checking, "-88.00", dining, is_deleted=True)
    await spend(brokerage, "-500.00", dining)
    await create_transaction(db_session, budget, checking, "-999.00", _today(), category=dining)
    await db_session.flush()
    return budget


async def _split(db_session, budget, start, end):
    return await income_split(db_session, budget.id, start, end, _today())


async def _spread(db_session, budget, on: bool):
    from igab.services.report_settings import set_spread_sinking_funds

    await set_spread_sinking_funds(db_session, budget.id, on)


class TestTheBuckets:
    async def test_add_up_to_income_to_the_cent(self, db_session):
        budget = await _household(db_session)
        await _spread(db_session, budget, False)
        s = await _split(db_session, budget, *_last_month())

        assert s["income"] == D("7000.00")
        assert s["needs"]["total"] == D("4050.00")
        assert s["wants"]["total"] == D("560.00")
        assert s["savings_debt"]["total"] == D("900.00")
        assert s["uncategorized"]["total"] == D("30.00")
        assert s["left_over"] == D("1460.00")
        parts = (
            s["needs"]["total"]
            + s["wants"]["total"]
            + s["savings_debt"]["total"]
            + s["uncategorized"]["total"]
            + s["left_over"]
        )
        assert parts == s["income"]

    async def test_name_why_each_line_is_where_it_is(self, db_session):
        budget = await _household(db_session)
        await _spread(db_session, budget, False)
        s = await _split(db_session, budget, *_last_month())

        def reasons(lines):
            return {line["name"]: (line["reason"], line["total"]) for line in lines}

        assert reasons(s["needs"]["lines"]) == {
            "Mortgage": ("essential_debt", D("2100.00")),
            "Car insurance": ("essential", D("1200.00")),
            "Groceries": ("essential", D("750.00")),
        }
        assert reasons(s["wants"]["committed"]) == {"Gym": ("cost_of_living", D("60.00"))}
        assert reasons(s["wants"]["chosen"]) == {"Dining out": ("untagged", D("500.00"))}
        assert reasons(s["savings_debt"]["debt"]) == {
            "Car payment": ("debt_not_essential", D("350.00")),
            # No category: named by the account it went to.
            "Harborstone Auto Loan": ("debt_no_category", D("50.00")),
        }
        assert [line["total"] for line in s["savings_debt"]["saved"]] == [D("500.00")]

    async def test_loan_proceeds_are_not_negative_debt_repayment(self, db_session):
        """$1,000 came IN from the car loan. Netted against the $400 paid to it,
        Savings & debt would read -$600 of debt."""
        budget = await _household(db_session)
        await _spread(db_session, budget, False)
        s = await _split(db_session, budget, *_last_month())
        assert sum(line["total"] for line in s["savings_debt"]["debt"]) == D("400.00")

    async def test_uncategorized_spending_is_counted_once(self, db_session):
        """Discretionary draws uncategorized spending as a line of its own; it
        is its own bucket here and not also a chosen want."""
        budget = await _household(db_session)
        s = await _split(db_session, budget, *_last_month())
        assert s["uncategorized"] == {"total": D("30.00"), "count": 1}
        assert all(line["name"] for line in s["wants"]["chosen"])

    async def test_an_essential_debt_reads_against_its_minimum(self, db_session):
        budget = await _household(db_session)
        await _spread(db_session, budget, False)
        s = await _split(db_session, budget, *_last_month())
        mortgage = next(x for x in s["needs"]["lines"] if x["name"] == "Mortgage")
        assert (mortgage["minimum"], mortgage["above_minimum"]) == (D("2000.00"), D("100.00"))
        # Read strictly, the $100 above the minimum is debt repaid, not a need.
        assert s["strict"] == {"needs": D("3950.00"), "savings_debt": D("1000.00")}

    async def test_spreads_the_yearly_premium_when_the_budget_asks(self, db_session):
        budget = await _household(db_session)
        await _spread(db_session, budget, True)
        s = await _split(db_session, budget, *_last_month())
        premium = next(x for x in s["needs"]["lines"] if x["name"] == "Car insurance")
        assert (premium["total"], premium["as_paid"], premium["spread"]) == (
            D("100.00"),
            D("1200.00"),
            True,
        )
        assert s["needs"]["total"] == D("2950.00")
        assert s["left_over"] == D("2560.00")


class TestAgreesWithTheOtherReports:
    async def test_needs_is_the_essentials_headline(self, db_session):
        """Over the last three complete months, Needs per month IS the figure
        the Essentials report, the Overview card and the emergency-fund target
        quote — spread or not."""
        budget = await _household(db_session)
        start, end = complete_month_window(_today(), 3)
        for on in (False, True):
            await _spread(db_session, budget, on)
            head = await essentials_headline(db_session, budget.id, _today())
            s = await _split(db_session, budget, start, end)
            assert s["months"] == D("3.00")
            assert s["needs"]["total"] / 3 == head["essentials"].monthly, f"spread {on}"

    async def test_chosen_and_uncategorized_are_discretionary(self, db_session):
        budget = await _household(db_session)
        await _spread(db_session, budget, False)
        report = await discretionary(ReportService(db_session), budget.id, 1, _today())
        s = await _split(db_session, budget, *_last_month())
        chosen = sum(line["total"] for line in s["wants"]["chosen"])
        assert chosen + s["uncategorized"]["total"] == report["total"] == D("530.00")

    async def test_needs_committed_and_every_debt_payment_are_cost_of_living(self, db_session):
        budget = await _household(db_session)
        await _spread(db_session, budget, False)
        report = await cost_of_living(db_session, budget.id, 1, _today())
        s = await _split(db_session, budget, *_last_month())
        debt = sum(line["total"] for line in s["savings_debt"]["debt"])
        committed = sum(line["total"] for line in s["wants"]["committed"])
        assert s["needs"]["total"] + committed + debt == report["avg_monthly_cost_of_living"]

    async def test_saved_and_income_are_the_savings_rates(self, db_session):
        budget = await _household(db_session)
        start, end = _last_month()
        rate = await savings_contributors(db_session, budget.id, start, end, _today())
        s = await _split(db_session, budget, start, end)
        saved = sum(line["total"] for line in s["savings_debt"]["saved"])
        assert (s["income"], saved) == (rate["income"], rate["savings"])


class TestTheWindow:
    async def test_a_range_before_the_history_starts_at_its_first_month(self, db_session):
        budget = await _household(db_session)
        first = add_months(_today().replace(day=1), -13)
        s = await _split(db_session, budget, first - timedelta(days=400), _last_month()[1])
        assert s["clamped"] is True
        assert s["start_date"] == first

    async def test_a_range_to_today_is_running_and_not_whole_months(self, db_session):
        budget = await _household(db_session)
        s = await _split(db_session, budget, _today().replace(day=1), _today())
        assert s["running"] is True
        assert s["whole_months"] is (_today() == month_end(_today()))

    async def test_nothing_tagged_essential_says_so(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        s = await _split(db_session, budget, *_last_month())
        assert s["tagged"] is False


async def test_the_endpoint_serves_it(api_client, db_session):
    budget = await _household(db_session, owner=api_client.test_user)
    await db_session.commit()
    start, end = _last_month()
    r = await api_client.get(
        f"/api/v1/{budget.id}/reports/income-split",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["income"] == 7000
    assert {"needs", "wants", "savings_debt", "uncategorized", "left_over", "strict"} <= set(body)
