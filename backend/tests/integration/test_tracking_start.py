"""Net Worth, the Overview card and Account Composition say what began being
counted, and quote a change like-for-like.

The audit: a year's net worth read +$620k, of which all but a few thousand
was accounts arriving with their balances and a house first valued; the
Overview card said "+225.5%". One budget below, walked by hand:

    window (months=3, today Sep 15): Jun, Jul, Aug complete, Sep so far

    Checking     Starting Balance +1,000 May 20 (before the window)
                 -100 Jul 10
    Brokerage    Starting Balance +20,000 Jul 5 (off budget)
                 +500 Aug 20
    Sapphire     budget start Aug 1; Starting Balance -2,000 Jul 1,
    Visa         -300 Jul 15 unfiled (pre-start: arrival), -200 Aug 10
    House        stated 300,000 Aug 3, 310,000 Sep 2
    Loan         manual debt 50,000 dated Sep 5

    point      net worth   entered
    Jun 30         1,000         0
    Jul 31        18,600    17,700   brokerage +20,000, card -2,300
    Aug 31       318,900   300,000   house
    Sep 15       278,900   -50,000   loan

    change 277,900 · entered 267,700 · like-for-like 10,200
    (= -100 checking + 500 brokerage - 200 card + 10,000 house)

Every name and figure is invented.
"""

from datetime import date
from decimal import Decimal as D

from igab.domain.payee_names import STARTING_BALANCE_PAYEE
from igab.repositories.account_type_repo import AccountTypeRepository
from igab.repositories.asset_repo import AssetRepository
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_liability,
    create_liability_snapshot,
    create_payee,
    create_transaction,
    create_user,
)

TODAY = date(2026, 9, 15)
JUN_30, JUL_31, AUG_31 = date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31)


async def _household(db_session, user=None):
    budget = await create_budget(db_session, user or await create_user(db_session))
    opening = await create_payee(db_session, budget, STARTING_BALANCE_PAYEE)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    await create_transaction(db_session, budget, checking, "1000", date(2026, 5, 20), payee=opening)
    await create_transaction(db_session, budget, checking, "-100", date(2026, 7, 10))

    brokerage = await create_account(
        db_session, budget, "Cascade Point Brokerage", account_type="investment", on_budget=False
    )
    await create_transaction(
        db_session, budget, brokerage, "20000", date(2026, 7, 5), payee=opening
    )
    await create_transaction(db_session, budget, brokerage, "500", date(2026, 8, 20))

    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    card.budget_start_date = date(2026, 8, 1)
    await create_transaction(db_session, budget, card, "-2000", date(2026, 7, 1), payee=opening)
    await create_transaction(db_session, budget, card, "-300", date(2026, 7, 15))
    await create_transaction(db_session, budget, card, "-200", date(2026, 8, 10))

    assets = AssetRepository(db_session)
    house = await assets.create(budget_id=budget.id, name="Maple St House")
    await assets.upsert_value(house, date(2026, 8, 3), D("300000"))
    await assets.upsert_value(house, date(2026, 9, 2), D("310000"))

    loan = await create_liability(
        db_session, budget, "Harborstone Family Loan", manual_balance=D("50000")
    )
    await create_liability_snapshot(db_session, loan, date(2026, 9, 5), D("50000"))
    await db_session.flush()
    return budget, {"checking": checking, "brokerage": brokerage, "card": card}, house, loan


class TestNetWorth:
    async def test_each_point_carries_what_entered_it(self, db_session):
        budget, accounts, house, loan = await _household(db_session)

        report = await ReportService(db_session).net_worth(budget.id, months=3, today=TODAY)
        points = report["points"]

        assert [p["net_worth"] for p in points] == [
            D("1000"),
            D("18600"),
            D("318900"),
            D("278900"),
        ]
        assert [p["entered"] for p in points] == [D("0"), D("17700"), D("300000"), D("-50000")]
        july = {e["name"]: e["amount"] for e in points[1]["entries"]}
        assert july == {"Cascade Point Brokerage": D("20000"), "Sapphire Visa": D("-2300")}
        assert [(e["kind"], e["id"]) for e in points[2]["entries"]] == [
            ("stated_asset", str(house.id))
        ]
        assert [(e["kind"], e["id"], e["day"]) for e in points[3]["entries"]] == [
            ("manual_debt", str(loan.id), date(2026, 9, 5))
        ]

    async def test_the_headline_is_the_change_less_what_entered(self, db_session):
        budget, *_ = await _household(db_session)

        report = await ReportService(db_session).net_worth(budget.id, months=3, today=TODAY)

        assert report["change"] == D("277900")
        assert report["entered_total"] == D("267700")
        assert report["like_for_like_change"] == D("10200")

    async def test_the_windows_first_point_is_its_baseline(self, db_session):
        """At months=1 the window opens on August: July's arrivals are in
        its first point and not subtracted again."""
        budget, *_ = await _household(db_session)

        report = await ReportService(db_session).net_worth(budget.id, months=1, today=TODAY)

        assert [p["net_worth"] for p in report["points"]] == [D("318900"), D("278900")]
        # August's house is August's own stretch: the first point's baseline.
        assert report["points"][0]["entered"] == D("300000")
        assert report["like_for_like_change"] == D("10000")

    async def test_a_card_payment_after_the_start_is_not_an_arrival(self, db_session):
        """Only the opening class enters: a filed row, or one after the
        budget start, is money that moved."""
        budget, accounts, *_ = await _household(db_session)
        await create_transaction(
            db_session, budget, accounts["card"], "-40", date(2026, 7, 20), memo="filed later"
        )
        # Filed before the start: the escape hatch — it counts as spending.
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        await create_transaction(
            db_session, budget, accounts["card"], "-60", date(2026, 7, 21), category=groceries
        )

        report = await ReportService(db_session).net_worth(budget.id, months=3, today=TODAY)

        july = {e["name"]: e["amount"] for e in report["points"][1]["entries"]}
        # -2,000 opening, -300 and -40 unfiled pre-start; the filed -60 is not.
        assert july["Sapphire Visa"] == D("-2340")
        assert report["like_for_like_change"] == D("10140")

    async def test_stated_values_carry_their_dates(self, db_session):
        budget, _, house, loan = await _household(db_session)

        report = await ReportService(db_session).net_worth(budget.id, months=3, today=TODAY)

        assert {(s["id"], s["value"], s["as_of"]) for s in report["stated_values"]} == {
            (str(house.id), D("310000"), date(2026, 9, 2)),
            (str(loan.id), D("50000"), date(2026, 9, 5)),
        }

    async def test_a_balance_unmoved_for_sixty_days_is_flagged(self, db_session):
        """Checking last moved Jul 10, 67 days before Sep 15; everything else
        moved inside the threshold."""
        budget, accounts, *_ = await _household(db_session)

        report = await ReportService(db_session).net_worth(budget.id, months=3, today=TODAY)

        assert report["stale_balances"] == [
            {
                "kind": "account",
                "id": str(accounts["checking"].id),
                "name": "Harborstone Checking",
                "last_changed": date(2026, 7, 10),
            }
        ]

    async def test_a_value_first_stated_long_ago_and_never_updated_is_flagged(self, db_session):
        budget = await create_budget(db_session, await create_user(db_session))
        assets = AssetRepository(db_session)
        car = await assets.create(budget_id=budget.id, name="Cedar Wagon")
        await assets.upsert_value(car, date(2026, 7, 1), D("9000"))
        typed = await create_liability(db_session, budget, "Jane Doe IOU", manual_balance=D("800"))
        await db_session.flush()

        report = await ReportService(db_session).net_worth(budget.id, months=3, today=TODAY)

        assert [(s["kind"], s["name"], s["last_changed"]) for s in report["stale_balances"]] == [
            # No dated balance: nothing says when it was true, first.
            ("manual_debt", "Jane Doe IOU", None),
            ("stated_asset", "Cedar Wagon", date(2026, 7, 1)),
        ]
        # ...and it entered today, the only day the sheet counts it.
        assert report["points"][-1]["entries"][0]["id"] == str(typed.id)

    async def test_the_api_serves_the_same(self, api_client, db_session):
        budget, *_ = await _household(db_session, api_client.test_user)

        resp = await api_client.get(
            f"/api/v1/{budget.id}/reports/net-worth",
            params={"months": 3, "client_today": TODAY.isoformat()},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["like_for_like_change"] == 10200
        assert body["entered_total"] == 267700
        assert [p["entered"] for p in body["points"]] == [0, 17700, 300000, -50000]
        assert body["stale_balances"][0]["name"] == "Harborstone Checking"
        assert body["stale_after_days"] == 60


class TestOverviewCard:
    async def test_the_card_change_leaves_out_what_arrived_in_the_range(self, db_session):
        """August's range: the change is against Jul 31. The house and the
        loan arrived after it; the rest is -200 card, +500 brokerage and
        +10,000 house revaluation."""
        budget, *_ = await _household(db_session)

        metrics = await ReportService(db_session).dashboard_metrics(
            budget.id, date(2026, 8, 1), AUG_31, today=TODAY
        )

        assert metrics["net_worth"] == D("278900")
        assert metrics["net_worth_prev"] == D("18600")
        assert metrics["net_worth_entered"] == D("250000")
        assert metrics["net_worth_change"] == D("10300")


class TestAccountComposition:
    async def test_the_stack_sums_to_net_with_bands_for_what_no_account_holds(self, db_session):
        budget, *_ = await _household(db_session)

        report = await ReportService(db_session).account_composition(
            budget.id, months=3, today=TODAY
        )

        for point in report["points"]:
            stack = sum(point["balances"].values(), D("0"))
            assert stack + point["stated_assets"] + point["manual_debts"] == point["net_worth"]
        now = report["points"][-1]
        assert (now["stated_assets"], now["manual_debts"]) == (D("310000"), D("-50000"))
        assert [p["entered"] for p in report["points"]] == [
            D("0"),
            D("17700"),
            D("300000"),
            D("-50000"),
        ]

    async def test_series_are_every_live_type_in_registry_order(self, db_session):
        """Colours are a series' place in this list. It used to be the types
        with a row in the window, sorted — so a range that dropped a type
        repainted every type after it."""
        budget, *_ = await _household(db_session)
        await create_account(db_session, budget, "Empty Savings", account_type="savings")
        await db_session.flush()
        registry = [t.key for t in await AccountTypeRepository(db_session).get_all(budget.id)]
        expected = [
            k for k in registry if k in {"checking", "investment", "credit_card", "savings"}
        ]

        svc = ReportService(db_session)
        long = await svc.account_composition(budget.id, months=3, today=TODAY)
        short = await svc.account_composition(budget.id, months=1, today=TODAY)

        assert long["series"] == short["series"] == expected
        # A type with no row anywhere still has its place, at zero.
        assert long["points"][-1]["balances"]["savings"] == D("0")
