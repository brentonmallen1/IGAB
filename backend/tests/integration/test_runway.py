"""Runway, served: how long the money lasts if income stopped.

One rule (`domain.runway`) read four ways — the Overview's Runway card, the
Cash Projection's "If income stopped" line and pickers, the Emergency Fund
report's "Covered" and the Essentials report's fund card. These pin that each
reads the rule, at the choice it says it reads, from the figures their own
reports serve.

The household is invented and every figure is round enough to check on paper:

- three complete months of Rent 1,000 (Essential), Gym 200 (Cost of living)
  and Dining 300 (neither): Essentials 1,000 a month, Cost of living 1,200,
  all spending 1,500;
- checking opened four months back with 20,000, so the cash is 15,500;
- 500 owed on a Sapphire Visa, charged today (the running month counts in no
  average);
- the emergency fund: a 2,000 envelope (inside the cash), a Cascade Point
  HYSA of 4,000 marked as the fund, and 1,000 declared as kept elsewhere —
  7,000 in all;
- another off-budget savings account of 3,000, savings but not the fund.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.db.models import GuideBinding
from igab.domain.dates import add_months, month_start
from igab.domain.runway import MoneyBasis, SpendingBasis
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.emergency_coverage import EmergencyCoverageService
from igab.services.essentials import essentials_summary
from igab.services.report_service import ReportService
from igab.services.runway import runway_read, spending_figures
from igab.services.savings_report import savings_report

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
)

TODAY = date.today()
THIS_MONTH = month_start(TODAY)
#: The three complete months every basis averages, oldest first.
MONTHS = [add_months(THIS_MONTH, -n) for n in (3, 2, 1)]
OPENED = add_months(THIS_MONTH, -4)

ALL, LIVING, LEAN = SpendingBasis.ALL, SpendingBasis.COST_OF_LIVING, SpendingBasis.ESSENTIALS
CHECKING, WITH_FUND, WITH_SAVINGS = (
    MoneyBasis.CHECKING,
    MoneyBasis.WITH_FUND,
    MoneyBasis.WITH_SAVINGS,
)


async def _tag(db_session, budget, category, key: str):
    tags = TagRepository(db_session)
    tag = await tags.get_system_tag(budget.id, key)
    await tags.set_category_tags(category.id, [tag.id])


async def _world(
    db_session,
    user=None,
    *,
    tagged: bool = True,
    fund: bool = True,
    card_owes: str = "-500.00",
):
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    await seed_system_tags(db_session, budget.id)
    checking = await create_account(db_session, budget, "Checking")
    await create_transaction(db_session, budget, checking, "20000.00", OPENED)

    bills = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, bills, "Rent")
    gym = await create_category(db_session, budget, bills, "Gym")
    dining = await create_category(db_session, budget, bills, "Dining")
    if tagged:
        await _tag(db_session, budget, rent, "essential")
        await _tag(db_session, budget, gym, "cost_of_living")
    for month in MONTHS:
        day = month + timedelta(days=4)
        for category, amount in ((rent, "-1000.00"), (gym, "-200.00"), (dining, "-300.00")):
            await create_transaction(db_session, budget, checking, amount, day, category=category)

    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    await create_transaction(db_session, budget, card, card_owes, TODAY, category=dining)

    other = await create_account(
        db_session, budget, "Harborstone Savings", account_type="savings", on_budget=False
    )
    await create_transaction(db_session, budget, other, "3000.00", OPENED)
    hysa = await create_account(
        db_session, budget, "Cascade Point HYSA", account_type="savings", on_budget=False
    )
    await create_transaction(db_session, budget, hysa, "4000.00", OPENED)

    if fund:
        goals = await create_category_group(db_session, budget, "Goals")
        envelope = await create_category(db_session, budget, goals, "Emergency Fund")
        await _tag(db_session, budget, envelope, "emergency_fund")
        await create_budget_assignment(db_session, budget, envelope, MONTHS[0], "2000.00")
        hysa.counts_toward_emergency_fund = True
        db_session.add(
            GuideBinding(
                budget_id=budget.id,
                concept_key="emergency_fund",
                mode="external",
                amount=Decimal("1000.00"),
                as_of=TODAY,
            )
        )
    await db_session.flush()
    return budget


def _months(read) -> dict:
    return {(o.spending, o.money): o.months for o in read.options}


# ─── The rule, at every choice ───────────────────────────────────────────────


async def test_every_choice_by_hand(db_session):
    budget = await _world(db_session)

    read = await runway_read(db_session, budget.id, TODAY)

    assert _months(read) == {
        # 15,500 cash − 500 owed = 15,000.
        (ALL, CHECKING): Decimal("10.0"),
        (LIVING, CHECKING): Decimal("12.5"),
        (LEAN, CHECKING): Decimal("15.0"),
        # + the HYSA 4,000 and the declared 1,000 — not the envelope, which is
        # already in the cash: 20,000.
        (ALL, WITH_FUND): Decimal("13.3"),
        (LIVING, WITH_FUND): Decimal("16.7"),
        (LEAN, WITH_FUND): Decimal("20.0"),
        # + every off-budget savings account (7,000) and the declared 1,000:
        # 23,000.
        (ALL, WITH_SAVINGS): Decimal("15.3"),
        (LIVING, WITH_SAVINGS): Decimal("19.2"),
        (LEAN, WITH_SAVINGS): Decimal("23.0"),
    }
    by_choice = {(o.spending, o.money): o for o in read.options}
    assert by_choice[(LEAN, WITH_FUND)].money_total == Decimal("20000.00")
    assert by_choice[(ALL, WITH_SAVINGS)].money_total == Decimal("23000.00")
    assert {o.card_debt for o in read.options} == {Decimal("500.00")}
    assert {o.monthly_spending for o in read.options} == {
        Decimal("1500.00"),
        Decimal("1200.00"),
        Decimal("1000.00"),
    }


async def test_the_monthly_figures_share_the_essentials_headline_window(db_session):
    budget = await _world(db_session)

    figures = await spending_figures(db_session, budget.id, TODAY)
    summary = await essentials_summary(db_session, budget.id, 12, TODAY)

    assert figures.monthly[LEAN] == summary["essentials"].monthly
    assert (figures.window_start, figures.window_end) == (
        summary["essentials"].window_start,
        summary["essentials"].window_end,
    )


async def test_all_spending_is_net_of_refunds_and_counts_uncategorized(db_session):
    """The one spending definition: a refund lowers it, an uncategorized
    outflow is in it, and the running month is in no average. Dining 300 a
    month, a 90 uncategorized outflow and a 30 refund: (900 + 90 − 30) / 3.
    Gross would read 330; dropping the uncategorized row, 290."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    await create_transaction(db_session, budget, checking, "5000.00", OPENED)
    group = await create_category_group(db_session, budget, "Everyday")
    dining = await create_category(db_session, budget, group, "Dining")
    for month in MONTHS:
        await create_transaction(
            db_session, budget, checking, "-300.00", month + timedelta(days=2), category=dining
        )
    await create_transaction(db_session, budget, checking, "-90.00", MONTHS[1] + timedelta(days=3))
    await create_transaction(
        db_session, budget, checking, "30.00", MONTHS[2] + timedelta(days=3), category=dining
    )
    await create_transaction(db_session, budget, checking, "-999.00", TODAY, category=dining)
    await db_session.flush()

    figures = await spending_figures(db_session, budget.id, TODAY)

    assert figures.monthly[ALL] == Decimal("320.00")


# ─── The Overview's default, and its fallbacks ───────────────────────────────


async def test_the_overview_reads_essentials_against_the_cash_and_the_fund(db_session):
    budget = await _world(db_session)

    card = (await ReportService(db_session).dashboard_metrics(budget.id, MONTHS[2], TODAY))[
        "runway"
    ]

    assert (card["spending"], card["money"]) == (LEAN, WITH_FUND)
    assert card["months"] == Decimal("20.0")
    # Twenty months of 30.4375 days: 608.75, 609 whole.
    assert card["runs_out_on"] == TODAY + timedelta(days=609)
    assert card["fund_chosen"] is True
    assert card["essentials_known"] is True
    assert card["card_debt"] == Decimal("500.00")


async def test_no_fund_falls_back_to_the_cash_and_says_so(db_session):
    budget = await _world(db_session, fund=False)

    read = await runway_read(db_session, budget.id, TODAY)

    assert read.fund_chosen is False
    assert (read.default.spending, read.default.money) == (LEAN, CHECKING)
    assert read.default.months == Decimal("15.0")
    # The fund choice is unanswered, not zero: no money, no runway.
    with_fund = next(o for o in read.options if (o.spending, o.money) == (LEAN, WITH_FUND))
    assert with_fund.money_total is None
    assert with_fund.months is None
    # Savings still count without a fund: 15,500 + 7,000 − 500.
    with_savings = next(o for o in read.options if (o.spending, o.money) == (LEAN, WITH_SAVINGS))
    assert with_savings.money_total == Decimal("22000.00")


async def test_nothing_tagged_falls_back_to_all_spending(db_session):
    budget = await _world(db_session, tagged=False)

    read = await runway_read(db_session, budget.id, TODAY)

    assert read.essentials_known is False
    assert (read.default.spending, read.default.money) == (ALL, WITH_FUND)
    assert read.default.months == Decimal("13.3")
    # Untagged tiers are unknown, never "everything": no runway to state.
    for option in read.options:
        if option.spending in (LIVING, LEAN):
            assert option.monthly_spending is None
            assert option.months is None


async def test_card_debt_larger_than_the_cash_has_run_out_today(db_session):
    # 15,500 of cash, 16,000 owed.
    budget = await _world(db_session, card_owes="-16000.00")

    read = await runway_read(db_session, budget.id, TODAY)
    checking = next(o for o in read.options if (o.spending, o.money) == (LEAN, CHECKING))

    assert checking.money_total == Decimal("-500.00")
    assert checking.months == Decimal("0.0")
    assert checking.runs_out_on == TODAY


async def test_an_off_budget_mortgage_is_not_money_and_not_owed(db_session):
    """The runway counts cash and savings against the cards. Net worth counts
    a house, a 401k and the mortgage against them — an off-budget loan is
    neither the budget's cash nor a card it owes from that cash."""
    budget = await _world(db_session)
    mortgage = await create_account(
        db_session, budget, "Maple St Mortgage", account_type="mortgage", on_budget=False
    )
    await create_transaction(db_session, budget, mortgage, "-280000.00", OPENED)
    await db_session.flush()

    read = await runway_read(db_session, budget.id, TODAY)

    assert read.default.months == Decimal("20.0")
    assert read.default.card_debt == Decimal("500.00")


async def _saving_but_not_cash(db_session, budget):
    """A 401k and a brokerage account (Investment) and crypto marked as savings
    (Other Asset): 90,000 the Savings report lists, none of it cash."""
    for name, account_type, amount in (
        ("Jane Doe 401k", "investment", "50000.00"),
        ("Brokerage", "investment", "30000.00"),
        ("Crypto", "other_asset", "10000.00"),
    ):
        account = await create_account(
            db_session,
            budget,
            name,
            account_type=account_type,
            on_budget=False,
            counts_as_savings=True,
        )
        await create_transaction(db_session, budget, account, amount, OPENED)
    await db_session.flush()


async def test_savings_accounts_count_only_those_that_hold_cash(db_session):
    """ "+ savings accounts" read every off-budget savings account, so a 401k
    and a brokerage account counted as months to live on; a budget with far
    more saved in retirement than in cash read years of runway. It counts the
    HYSAs (7,000) and the declared 1,000 and nothing else: 23,000, as before
    the 90,000 arrived."""
    budget = await _world(db_session)
    await _saving_but_not_cash(db_session, budget)

    read = await runway_read(db_session, budget.id, TODAY)

    by_choice = {(o.spending, o.money): o for o in read.options}
    assert by_choice[(ALL, WITH_SAVINGS)].money_total == Decimal("23000.00")
    assert by_choice[(LEAN, WITH_SAVINGS)].months == Decimal("23.0")
    # The fund's and the cash's figures never read the savings accounts.
    assert by_choice[(LEAN, WITH_FUND)].money_total == Decimal("20000.00")
    assert by_choice[(LEAN, CHECKING)].money_total == Decimal("15000.00")


async def test_the_savings_report_still_lists_what_the_runway_leaves_out(db_session):
    """Deliberate divergence: the 401k is saving, so the Savings report counts
    it under Saved; it is not cash, so the runway does not. Pinned so the two
    stay apart by exactly the accounts that are not cash."""
    budget = await _world(db_session)
    await _saving_but_not_cash(db_session, budget)

    saved = (await savings_report(db_session, budget.id, 3, TODAY))["saved"]
    read = await runway_read(db_session, budget.id, TODAY)

    with_savings = next(o for o in read.options if (o.spending, o.money) == (ALL, WITH_SAVINGS))
    # The HYSAs' 7,000 and the 90,000 that is not cash, where the runway
    # counts 15,500 cash + 7,000 + 1,000 declared − 500 owed.
    assert saved["accounts_total"] == Decimal("97000.00")
    assert with_savings.money_total == Decimal("23000.00")


async def test_a_fund_kept_in_an_investment_account_still_counts_with_savings(db_session):
    """The person chose it as the fund, so "+ emergency fund" counts it — and
    "+ savings accounts" beside it never counts less than the fund does."""
    budget = await _world(db_session)
    fund_account = await create_account(
        db_session,
        budget,
        "Money Market",
        account_type="investment",
        on_budget=False,
        counts_as_savings=True,
    )
    await create_transaction(db_session, budget, fund_account, "5000.00", OPENED)
    fund_account.counts_toward_emergency_fund = True
    await db_session.flush()

    read = await runway_read(db_session, budget.id, TODAY)

    by_choice = {(o.spending, o.money): o for o in read.options}
    # 20,000 + the fund's 5,000.
    assert by_choice[(LEAN, WITH_FUND)].money_total == Decimal("25000.00")
    # 23,000 + the fund's 5,000.
    assert by_choice[(LEAN, WITH_SAVINGS)].money_total == Decimal("28000.00")


# ─── The Emergency Fund and Essentials reports read the same rule ─────────────


async def test_covered_is_the_rule_at_essentials_and_the_fund(db_session):
    """7,000 of fund, 500 owed on the card, 1,000 a month of Essentials: 6.5
    months — the card debt taken out, and said so. It divided the fund alone
    and read 7.0."""
    budget = await _world(db_session)

    report = await EmergencyCoverageService(db_session).coverage(budget.id, months=3, today=TODAY)
    essentials = await essentials_summary(db_session, budget.id, 12, TODAY)

    covered = report["covered"]
    assert (covered.spending, covered.money) == (LEAN, MoneyBasis.FUND)
    assert covered.money_total == Decimal("6500.00")
    assert covered.card_debt == Decimal("500.00")
    assert covered.months == Decimal("6.5")
    assert covered == essentials["fund_runway"]


async def test_the_chart_stays_the_fund_over_essentials(db_session):
    """The deliberate gap: the headline takes out today's card debt, the
    series does not. With the fund unchanged since last month, the newest
    point reads 7.0 and the headline 6.5 — exactly the 500 owed over the
    1,000 a month. A wider gap is a second divergence nobody decided."""
    budget = await _world(db_session)

    report = await EmergencyCoverageService(db_session).coverage(budget.id, months=3, today=TODAY)

    newest = report["series"][-1]
    assert newest["fund_balance"] == Decimal("7000.00")
    assert newest["coverage_months"] == Decimal("7.0")
    gap = newest["coverage_months"] - report["covered"].months
    assert gap == report["covered"].card_debt / newest["essentials"]


# ─── Served ──────────────────────────────────────────────────────────────────


async def test_the_dashboard_serves_the_runway_card(db_session, api_client):
    budget = await _world(db_session, api_client.test_user)

    body = (
        await api_client.get(
            f"/api/v1/{budget.id}/reports/dashboard",
            params={"start_date": MONTHS[2].isoformat(), "end_date": TODAY.isoformat()},
        )
    ).json()

    assert "days_until_zero" not in body
    runway = body["runway"]
    assert (runway["spending"], runway["money"]) == ("essentials", "with_fund")
    assert Decimal(str(runway["months"])) == Decimal("20.0")
    assert runway["runs_out_on"] == (TODAY + timedelta(days=609)).isoformat()
    assert Decimal(str(runway["money_total"])) == Decimal("20000.00")
    assert Decimal(str(runway["card_debt"])) == Decimal("500.00")
    assert runway["fund_chosen"] is True
    assert runway["window_start"] == MONTHS[0].isoformat()


async def test_the_projection_serves_every_choice_with_its_line(db_session, api_client):
    budget = await _world(db_session, api_client.test_user)

    body = (
        await api_client.get(f"/api/v1/{budget.id}/reports/cash-projection", params={"days": 90})
    ).json()

    assert all("deterministic" not in p for p in body["points"])
    stopped = body["if_income_stopped"]
    assert (stopped["default_spending"], stopped["default_money"]) == ("essentials", "with_fund")
    assert [(o["spending"], o["money"]) for o in stopped["options"]] == [
        (spending, money)
        for spending in ("all", "cost_of_living", "essentials")
        for money in ("checking", "with_fund", "with_savings")
    ]
    default = next(
        o for o in stopped["options"] if (o["spending"], o["money"]) == ("essentials", "with_fund")
    )
    # From 20,000 today, down 1,000 a month; twenty months outlast the
    # horizon, so the line stops on its last day: 90 / 30.4375 months spent.
    [first, last] = default["line"]
    assert (first["date"], Decimal(str(first["balance"]))) == (
        TODAY.isoformat(),
        Decimal("20000.00"),
    )
    assert last["date"] == (TODAY + timedelta(days=90)).isoformat()
    assert Decimal(str(last["balance"])) == Decimal("17043.12")
