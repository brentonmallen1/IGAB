"""`counterpart_account_id`: the served answer to "where does this transfer go?".

The client used to render linked legs as the bare word "Transfer" because it
had no way to know the other side: the payee on a linked leg can be null or
wrong, and the partner row may not be loaded. The server already knew — the
same expression drives cash-flow classification — so it serves the answer.

Checklist discipline (mirrors test_offbudget_categories.py): unlike
needs_category, None is a legal value here, so a listing path that forgets the
loader degrades silently to "not a transfer" rather than raising. Every path
that serializes a TransactionResponse is swept below and must carry a non-null
counterpart for transfer rows.
"""

from datetime import date

from igab.repositories.payee_repo import PayeeRepository

from .factories import create_account, create_budget, create_transaction

TODAY = date(2026, 8, 20)


async def _transfer_fixture(db_session, user):
    """A budget with a linked pair, an orphan leg, and a plain transaction."""
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")

    payee_repo = PayeeRepository(db_session)
    to_savings = await payee_repo.find_or_create_transfer(budget.id, savings.id, savings.name)
    to_checking = await payee_repo.find_or_create_transfer(budget.id, checking.id, checking.name)

    out_leg = await create_transaction(
        db_session, budget, checking, "-500.00", TODAY, payee=to_savings
    )
    in_leg = await create_transaction(
        db_session, budget, savings, "500.00", TODAY, payee=to_checking, transfer_id=out_leg.id
    )
    out_leg.transfer_id = in_leg.id
    await db_session.flush()

    # Partner never arrived (skipped account at import): payee is the only signal.
    orphan = await create_transaction(
        db_session, budget, checking, "-25.00", TODAY, payee=to_savings
    )
    plain = await create_transaction(db_session, budget, checking, "-10.00", TODAY)
    return budget, checking, savings, out_leg, in_leg, orphan, plain


def _by_id(rows: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in rows}


class TestListings:
    async def test_account_register_carries_it_for_every_shape(self, api_client, db_session):
        budget, checking, savings, out_leg, in_leg, orphan, plain = await _transfer_fixture(
            db_session, api_client.test_user
        )

        rows = _by_id((await api_client.get(f"/api/v1/accounts/{checking.id}/transactions")).json())
        assert rows[str(out_leg.id)]["counterpart_account_id"] == str(savings.id), (
            "linked leg names the partner's account"
        )
        assert rows[str(orphan.id)]["counterpart_account_id"] == str(savings.id), (
            "orphan leg falls back to the account its transfer payee names"
        )
        assert rows[str(plain.id)]["counterpart_account_id"] is None

        other_side = _by_id(
            (await api_client.get(f"/api/v1/accounts/{savings.id}/transactions")).json()
        )
        assert other_side[str(in_leg.id)]["counterpart_account_id"] == str(checking.id), (
            "the link answers in both directions"
        )

    async def test_budget_wide_listing_carries_it(self, api_client, db_session):
        budget, checking, savings, out_leg, _, orphan, plain = await _transfer_fixture(
            db_session, api_client.test_user
        )
        body = (await api_client.get(f"/api/v1/{budget.id}/transactions")).json()
        rows = _by_id(body["transactions"])
        assert rows[str(out_leg.id)]["counterpart_account_id"] == str(savings.id)
        assert rows[str(orphan.id)]["counterpart_account_id"] == str(savings.id)
        assert rows[str(plain.id)]["counterpart_account_id"] is None

    async def test_single_get_carries_it(self, api_client, db_session):
        budget, _, savings, out_leg, *_ = await _transfer_fixture(db_session, api_client.test_user)
        body = (
            await api_client.get(
                f"/api/v1/transactions/{out_leg.id}", params={"budget_id": str(budget.id)}
            )
        ).json()
        assert body["counterpart_account_id"] == str(savings.id)


class TestMutatingEndpoints:
    async def test_create_transfer_returns_it(self, api_client, db_session):
        """The create response is what the row renders as before any refetch —
        a None here is the old bare-'Transfer' bug back for exactly one paint."""
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        savings = await create_account(db_session, budget, "Savings")

        resp = await api_client.post(
            f"/api/v1/{budget.id}/transactions",
            json={
                "account_id": str(checking.id),
                "date": str(TODAY),
                "amount": "-500.00",
                "transfer_account_id": str(savings.id),
            },
        )
        assert resp.status_code == 201
        assert resp.json()["counterpart_account_id"] == str(savings.id)

    async def test_it_survives_a_service_update(self, api_client, db_session):
        """PATCH goes create→flush→refresh; a refresh that drops the
        expression serializes the leg as a plain row."""
        budget, _, savings, out_leg, *_ = await _transfer_fixture(db_session, api_client.test_user)
        resp = await api_client.patch(
            f"/api/v1/transactions/{out_leg.id}",
            params={"budget_id": str(budget.id)},
            json={"memo": "still a transfer"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["memo"] == "still a transfer"
        assert body["counterpart_account_id"] == str(savings.id)

    async def test_approve_returns_it(self, api_client, db_session):
        budget, checking, savings, *_ = await _transfer_fixture(db_session, api_client.test_user)
        payee_repo = PayeeRepository(db_session)
        to_savings = await payee_repo.find_or_create_transfer(budget.id, savings.id, savings.name)
        unapproved = await create_transaction(
            db_session, budget, checking, "-75.00", TODAY, payee=to_savings, approved=False
        )
        resp = await api_client.post(
            f"/api/v1/transactions/{unapproved.id}/approve",
            params={"budget_id": str(budget.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["counterpart_account_id"] == str(savings.id)


class TestOffBudgetCounterpart:
    async def test_tracked_account_transfer_names_the_tracked_side(self, api_client, db_session):
        """A spending transfer (categorized leg to a tracked account) is still
        a transfer to the display layer — the mortgage row should read
        'Transfer : Mortgage', not the bare word."""
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        mortgage = await create_account(
            db_session, budget, "Mortgage", account_type="mortgage", on_budget=False
        )
        payee_repo = PayeeRepository(db_session)
        to_mortgage = await payee_repo.find_or_create_transfer(
            budget.id, mortgage.id, mortgage.name
        )
        leg = await create_transaction(
            db_session, budget, checking, "-2000.00", TODAY, payee=to_mortgage
        )
        rows = _by_id((await api_client.get(f"/api/v1/accounts/{checking.id}/transactions")).json())
        assert rows[str(leg.id)]["counterpart_account_id"] == str(mortgage.id)
