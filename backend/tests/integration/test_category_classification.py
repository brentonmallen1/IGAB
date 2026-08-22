"""The category-level "how does this count?" endpoint.

The per-transaction endpoint explains one row after the user has found it;
this one puts the answer on the category itself — a "Debt payment" badge on
Car Payment says why it will be missing from spending reports *before* the
user goes looking. The badge contract: `dominant` only when one non-spending
class covers more than half of the window's outflow.
"""

from datetime import date, timedelta
from decimal import Decimal

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


async def _world(db_session, owner):
    budget = await create_budget(db_session, owner)
    checking = await create_account(db_session, budget, "Checking", on_budget=True)
    loan = await create_account(
        db_session, budget, "Car Loan", account_type="loan", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Bills")
    to_loan = await create_payee(
        db_session, budget, "Transfer : Car Loan", transfer_account_id=loan.id
    )
    return budget, checking, loan, group, to_loan


async def _get(api_client, category_id):
    resp = await api_client.get(f"/api/v1/categories/{category_id}/classification")
    assert resp.status_code == 200
    return resp.json()


class TestCategoryClassification:
    async def test_a_debt_payment_category_gets_the_badge(self, api_client, db_session):
        budget, checking, _, group, to_loan = await _world(db_session, api_client.test_user)
        car = await create_category(db_session, budget, group, "Car Payment")
        await create_transaction(
            db_session, budget, checking, "-275.00", TODAY, category=car, payee=to_loan
        )

        body = await _get(api_client, car.id)

        assert body["dominant"] == "debt_principal"
        assert body["dominant_label"] == "Debt payment"
        assert "pays down a tracked debt" in body["explanation"]
        assert body["explanation"].startswith("All of this category's activity")
        assert body["classes"] == [
            {
                "activity_class": "debt_principal",
                "label": "Debt payment",
                "total": "275.00",
                "count": 1,
            }
        ]

    async def test_an_ordinary_category_gets_no_badge(self, api_client, db_session):
        budget, checking, _, group, _ = await _world(db_session, api_client.test_user)
        groceries = await create_category(db_session, budget, group, "Groceries")
        await create_transaction(
            db_session, budget, checking, "-80.00", TODAY, category=groceries
        )

        body = await _get(api_client, groceries.id)

        assert body["dominant"] is None
        assert body["explanation"] is None
        assert body["classes"][0]["activity_class"] == "spending"

    async def test_mixed_activity_reports_composition_but_badges_the_majority(
        self, api_client, db_session
    ):
        """One stray coffee categorised as Car Payment must not strip the
        badge — but the composition list still shows both."""
        budget, checking, _, group, to_loan = await _world(db_session, api_client.test_user)
        car = await create_category(db_session, budget, group, "Car Payment")
        await create_transaction(
            db_session, budget, checking, "-275.00", TODAY, category=car, payee=to_loan
        )
        await create_transaction(db_session, budget, checking, "-4.50", TODAY, category=car)

        body = await _get(api_client, car.id)

        assert body["dominant"] == "debt_principal"
        assert body["explanation"].startswith("Most of this category's activity")
        assert [c["activity_class"] for c in body["classes"]] == [
            "debt_principal",
            "spending",
        ]

    async def test_a_spending_majority_means_no_badge(self, api_client, db_session):
        budget, checking, _, group, to_loan = await _world(db_session, api_client.test_user)
        cat = await create_category(db_session, budget, group, "Mostly Groceries")
        await create_transaction(db_session, budget, checking, "-300.00", TODAY, category=cat)
        await create_transaction(
            db_session, budget, checking, "-100.00", TODAY, category=cat, payee=to_loan
        )

        body = await _get(api_client, cat.id)

        assert body["dominant"] is None
        assert len(body["classes"]) == 2

    async def test_an_exact_half_is_not_a_majority(self, api_client, db_session):
        budget, checking, _, group, to_loan = await _world(db_session, api_client.test_user)
        cat = await create_category(db_session, budget, group, "Split Down The Middle")
        await create_transaction(db_session, budget, checking, "-100.00", TODAY, category=cat)
        await create_transaction(
            db_session, budget, checking, "-100.00", TODAY, category=cat, payee=to_loan
        )

        body = await _get(api_client, cat.id)

        assert body["dominant"] is None

    async def test_a_savings_tag_drives_the_badge(self, api_client, db_session):
        """The override path: no transfer anywhere, just the tag — and the
        explanation says the tag is the reason."""
        budget, checking, _, group, _ = await _world(db_session, api_client.test_user)
        fund = await create_category(db_session, budget, group, "Emergency Fund")
        repo = TagRepository(db_session)
        tags = {t.system_key: t for t in await repo.list_for_budget(budget.id)}
        tag = tags.get("savings") or await create_tag(
            db_session, budget, "savings", system_key="savings"
        )
        await repo.set_category_tags(fund.id, [tag.id])
        await create_transaction(db_session, budget, checking, "-500.00", TODAY, category=fund)

        body = await _get(api_client, fund.id)

        assert body["dominant"] == "savings"
        assert "tagged as savings" in body["explanation"]

    async def test_no_activity_means_no_classes_and_no_badge(self, api_client, db_session):
        budget, _, _, group, _ = await _world(db_session, api_client.test_user)
        empty = await create_category(db_session, budget, group, "Brand New")

        body = await _get(api_client, empty.id)

        assert body["classes"] == []
        assert body["dominant"] is None

    async def test_activity_older_than_the_window_is_ignored(self, api_client, db_session):
        budget, checking, _, group, to_loan = await _world(db_session, api_client.test_user)
        car = await create_category(db_session, budget, group, "Old Car")
        await create_transaction(
            db_session,
            budget,
            checking,
            "-275.00",
            TODAY - timedelta(days=400),
            category=car,
            payee=to_loan,
        )

        body = await _get(api_client, car.id)

        assert body["classes"] == []
        assert body["dominant"] is None

    async def test_inflows_do_not_dilute_the_badge(self, api_client, db_session):
        """A refund in the category is not outflow; the badge is about where
        money goes when it leaves."""
        budget, checking, _, group, to_loan = await _world(db_session, api_client.test_user)
        car = await create_category(db_session, budget, group, "Car Payment")
        await create_transaction(
            db_session, budget, checking, "-275.00", TODAY, category=car, payee=to_loan
        )
        await create_transaction(db_session, budget, checking, "500.00", TODAY, category=car)

        body = await _get(api_client, car.id)

        assert body["dominant"] == "debt_principal"
        assert sum(Decimal(c["total"]) for c in body["classes"]) == Decimal("275.00")

    async def test_another_users_category_is_forbidden(self, api_client, db_session):
        other = await create_user(db_session)
        budget, checking, _, group, _ = await _world(db_session, other)
        cat = await create_category(db_session, budget, group, "Not Yours")

        resp = await api_client.get(f"/api/v1/categories/{cat.id}/classification")

        assert resp.status_code in (403, 404)
