"""The budget row's target verdict is computed once, on the server.

`frontend/src/utils/targets.ts` used to mirror `calculate_status`, and
`CategoryRow.tsx` re-implemented the shortfall a third time with the target
types inverted relative to the mirror — the pill and the "Save $X more" line
beside it were computed from different rules and rendered together.

These tests are the served-field checklist from test_offbudget_categories.py,
applied to `target_status` and `needed_this_month`: every listing path carries
them, they agree with the service the assign endpoint asks, and they say
nothing when there is no target.
"""

from datetime import date
from decimal import Decimal

from igab.services.target_service import TargetService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

MONTH = date(2026, 8, 1)


async def _setup(db_session, user):
    services = make_services(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    account = await create_account(db_session, budget, "Checking")
    return services, budget, group, account


async def _month(api_client, budget, month=MONTH):
    resp = await api_client.get(f"/api/v1/{budget.id}/months/{month.isoformat()}")
    assert resp.status_code == 200, resp.text
    return {b["category_id"]: b for b in resp.json()["category_balances"]}


async def _set_target(db_session, category, target_type, amount, target_date=None):
    from igab.repositories.target_repo import TargetRepository

    svc = TargetService(TargetRepository(db_session))
    return await svc.upsert(
        category.id, target_type, Decimal(amount), target_date=target_date
    )


class TestTheFieldsAreServed:
    async def test_a_category_without_a_target_says_nothing(self, db_session, api_client):
        _, budget, group, _ = await _setup(db_session, api_client.test_user)
        category = await create_category(db_session, budget, group, "Groceries")

        row = (await _month(api_client, budget))[str(category.id)]

        assert row["target_status"] is None
        assert row["needed_this_month"] is None

    async def test_an_unfunded_target_reports_what_it_needs(self, db_session, api_client):
        services, budget, group, _ = await _setup(db_session, api_client.test_user)
        category = await create_category(db_session, budget, group, "Groceries")
        await _set_target(db_session, category, "monthly_funding", "400.00")

        row = (await _month(api_client, budget))[str(category.id)]

        assert row["target_status"] == "underfunded"
        assert Decimal(str(row["needed_this_month"])) == Decimal("400.00")

    async def test_assigning_the_target_funds_it(self, db_session, api_client):
        services, budget, group, _ = await _setup(db_session, api_client.test_user)
        category = await create_category(db_session, budget, group, "Groceries")
        await _set_target(db_session, category, "monthly_funding", "400.00")
        await services.budgets.set_assignment(budget.id, category.id, MONTH, Decimal("400.00"))

        row = (await _month(api_client, budget))[str(category.id)]

        assert row["target_status"] == "funded"
        assert Decimal(str(row["needed_this_month"])) == Decimal("0")

    async def test_a_savings_goal_is_judged_on_the_balance(self, db_session, api_client):
        # The case the client's mirror got wrong: money assigned and then spent
        # leaves the balance short, and the pill must say so.
        services, budget, group, account = await _setup(db_session, api_client.test_user)
        category = await create_category(db_session, budget, group, "Emergency")
        await _set_target(db_session, category, "savings_balance", "1000.00")
        await services.budgets.set_assignment(budget.id, category.id, MONTH, Decimal("400.00"))
        await create_transaction(
            db_session, budget, account, "-400.00", MONTH, category=category, cleared="cleared"
        )

        row = (await _month(api_client, budget))[str(category.id)]

        assert Decimal(str(row["available"])) == Decimal("0.00")
        assert row["target_status"] == "underfunded"
        assert Decimal(str(row["needed_this_month"])) == Decimal("1000.00")


class TestTheServedFieldIsTheOnlyRule:
    async def test_the_pill_agrees_with_the_service_row_for_row(self, db_session, api_client):
        """Whatever the endpoint says must be what TargetService says."""
        services, budget, group, account = await _setup(db_session, api_client.test_user)
        svc = services.transactions  # noqa: F841  (keeps make_services warm)

        cases = [
            ("monthly_funding", "400.00", None, "0.00", None),
            ("monthly_funding", "400.00", None, "400.00", None),
            ("monthly_funding", "400.00", None, "500.00", None),
            ("savings_balance", "1000.00", None, "300.00", None),
            ("savings_balance", "1000.00", None, "1000.00", None),
            ("weekly_funding", "50.00", None, "0.00", None),
            ("needed_for_spending", "600.00", date(2026, 10, 1), "100.00", None),
            ("needed_for_spending", "600.00", None, "600.00", None),
        ]
        categories = []
        for i, (ttype, amount, tdate, assigned, _) in enumerate(cases):
            category = await create_category(db_session, budget, group, f"C{i}")
            await _set_target(db_session, category, ttype, amount, target_date=tdate)
            if Decimal(assigned) != 0:
                await services.budgets.set_assignment(
                    budget.id, category.id, MONTH, Decimal(assigned)
                )
            categories.append(category)

        rows = await _month(api_client, budget)
        summary = await services.budgets.get_budget_summary(budget.id, MONTH)
        balances = {b.category_id: b for b in summary.category_balances}

        from igab.repositories.target_repo import TargetRepository

        target_service = TargetService(TargetRepository(db_session))
        for category in categories:
            target = await target_service.get(category.id)
            bal = balances[category.id]
            assert rows[str(category.id)]["target_status"] == target_service.calculate_status(
                target, bal.assigned, bal.available
            ), category.name
            assert Decimal(
                str(rows[str(category.id)]["needed_this_month"])
            ) == target_service.calculate_needed(target, bal.assigned, bal.available), category.name

    async def test_underfunded_means_fill_underfunded_would_move_money(
        self, db_session, api_client
    ):
        """The pill's whole job, asserted against the endpoint that does it."""
        services, budget, group, _ = await _setup(db_session, api_client.test_user)
        for i, (ttype, amount, assigned) in enumerate(
            [
                ("monthly_funding", "400.00", "0.00"),
                ("monthly_funding", "400.00", "400.00"),
                ("savings_balance", "1000.00", "0.00"),
                ("savings_balance", "1000.00", "1000.00"),
            ]
        ):
            category = await create_category(db_session, budget, group, f"C{i}")
            await _set_target(db_session, category, ttype, amount)
            if Decimal(assigned) != 0:
                await services.budgets.set_assignment(
                    budget.id, category.id, MONTH, Decimal(assigned)
                )

        for row in (await _month(api_client, budget)).values():
            if row["target_status"] is None:
                continue
            needed = Decimal(str(row["needed_this_month"]))
            assert (row["target_status"] == "underfunded") == (needed > 0), row


class TestOverspentCountMatchesItsAmount:
    """The hero shows an amount and a count side by side. They were computed
    from different populations — the amount server-side over non-system
    categories including hidden ones, the count client-side from a category
    list that excludes hidden — so a hidden overspent category made the two
    disagree, and Cover Overspent then acted on a category the count denied.
    """

    async def test_the_count_and_the_amount_cover_the_same_categories(
        self, db_session, api_client
    ):
        services, budget, group, account = await _setup(db_session, api_client.test_user)
        for i, spend in enumerate(["-50.00", "-30.00"]):
            category = await create_category(db_session, budget, group, f"Over{i}")
            await create_transaction(
                db_session, budget, account, spend, MONTH, category=category, cleared="cleared"
            )

        resp = await api_client.get(f"/api/v1/{budget.id}/months/{MONTH.isoformat()}")
        data = resp.json()

        assert data["overspent_count"] == 2
        assert Decimal(str(data["total_overspent"])) == Decimal("80.00")

    async def test_a_hidden_overspent_category_is_counted_because_it_is_covered(
        self, db_session, api_client
    ):
        from igab.repositories.category_repo import CategoryRepository

        services, budget, group, account = await _setup(db_session, api_client.test_user)
        category = await create_category(db_session, budget, group, "Hidden")
        await create_transaction(
            db_session, budget, account, "-25.00", MONTH, category=category, cleared="cleared"
        )
        await CategoryRepository(db_session).update(category.id, is_hidden=True)

        resp = await api_client.get(f"/api/v1/{budget.id}/months/{MONTH.isoformat()}")
        data = resp.json()

        # Hidden categories still hold money and still overspend, so Cover
        # Overspent acts on them — the count has to agree with that.
        assert data["overspent_count"] == 1
        assert Decimal(str(data["total_overspent"])) == Decimal("25.00")

    async def test_a_system_category_is_not_overspending(self, db_session, api_client):
        from igab.repositories.category_repo import CategoryGroupRepository

        services, budget, group, account = await _setup(db_session, api_client.test_user)
        income = await create_category_group(db_session, budget, "Income")
        await CategoryGroupRepository(db_session).update(income.id, is_system=True)
        category = await create_category(db_session, budget, income, "Paycheque")
        await create_transaction(
            db_session, budget, account, "-40.00", MONTH, category=category, cleared="cleared"
        )

        resp = await api_client.get(f"/api/v1/{budget.id}/months/{MONTH.isoformat()}")

        assert resp.json()["overspent_count"] == 0

    async def test_nothing_overspent_is_zero(self, db_session, api_client):
        services, budget, group, _ = await _setup(db_session, api_client.test_user)
        await create_category(db_session, budget, group, "Groceries")

        resp = await api_client.get(f"/api/v1/{budget.id}/months/{MONTH.isoformat()}")

        assert resp.json()["overspent_count"] == 0
        assert Decimal(str(resp.json()["total_overspent"])) == Decimal("0")
