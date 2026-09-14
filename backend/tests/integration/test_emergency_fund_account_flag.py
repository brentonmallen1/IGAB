"""An account says whether it counts toward the emergency fund.

Chosen, never guessed, and valid on one shape only: an off-budget asset that
counts as savings (`txn_filters.EMERGENCY_FUND_ACCOUNT_SHAPE`). On budget, its
money is already in the envelopes; a liability is owed, not held; and without
Counts as savings a transfer into it classes as spending while the account
counts as fund.
"""

import io
import zipfile

from sqlalchemy import select

from igab.db.models import Account
from igab.repositories.txn_filters import (
    EMERGENCY_FUND_ACCOUNT,
    EMERGENCY_FUND_ACCOUNT_CANDIDATE,
)

from .factories import create_account, create_budget


async def _budget(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    return budget


async def _accounts(api_client, budget):
    return (await api_client.get(f"/api/v1/{budget.id}/accounts")).json()


async def _counted(db_session, budget, predicate=EMERGENCY_FUND_ACCOUNT):
    return set(
        (
            await db_session.execute(
                select(Account.name).where(Account.budget_id == budget.id, predicate)
            )
        ).scalars()
    )


class TestTheFlagIsRefusedOnTheWrongShape:
    async def test_flag_refused_on_budget_or_liability_or_not_savings(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        on_budget = await create_account(db_session, budget, "Harborstone Checking")
        loan = await create_account(
            db_session, budget, "Harborstone Mortgage", account_type="mortgage", on_budget=False
        )
        car = await create_account(
            db_session,
            budget,
            "Second Car",
            account_type="other_asset",
            on_budget=False,
            counts_as_savings=False,
        )
        await db_session.commit()

        for account in (on_budget, loan, car):
            resp = await api_client.patch(
                f"/api/v1/accounts/{account.id}", json={"counts_toward_emergency_fund": True}
            )
            assert resp.status_code == 422, (account.name, resp.text)
            assert "off-budget savings account" in resp.json()["detail"]

        served = {
            a["name"]: a["counts_toward_emergency_fund"]
            for a in await _accounts(api_client, budget)
        }
        assert served == {
            "Harborstone Checking": False,
            "Harborstone Mortgage": False,
            "Second Car": False,
        }, "a refused flag writes nothing"

    async def test_a_create_with_the_flag_on_the_wrong_shape_is_refused(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={
                "name": "Harborstone Checking",
                "account_type": "checking",
                "counts_toward_emergency_fund": True,
            },
        )
        assert resp.status_code == 422, resp.text
        assert await _accounts(api_client, budget) == []

    async def test_the_same_request_may_make_the_shape_valid(self, db_session, api_client):
        """Judged after the request's other fields: turning Counts as savings on
        and the flag on in one save is how the picker marks a new account."""
        budget = await _budget(db_session, api_client)
        car = await create_account(
            db_session,
            budget,
            "Cascade Point Reserve",
            account_type="other_asset",
            on_budget=False,
            counts_as_savings=False,
        )
        await db_session.commit()

        resp = await api_client.patch(
            f"/api/v1/accounts/{car.id}",
            json={"counts_as_savings": True, "counts_toward_emergency_fund": True},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["counts_toward_emergency_fund"] is True

    async def test_an_off_budget_savings_account_may_be_created_marked(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={
                "name": "Harborstone Reserve",
                "account_type": "savings",
                "on_budget": False,
                "counts_toward_emergency_fund": True,
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["counts_toward_emergency_fund"] is True
        assert await _counted(db_session, budget) == {"Harborstone Reserve"}

    async def test_the_flag_defaults_false_and_is_served(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Harborstone Reserve", "account_type": "savings", "on_budget": False},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["counts_toward_emergency_fund"] is False


class TestThePredicates:
    async def test_flag_inert_after_account_moves_on_budget(self, db_session, api_client):
        """Moving a marked account on budget is allowed — refusing would trap
        it — and the flag it keeps counts for nothing."""
        budget = await _budget(db_session, api_client)
        reserve = await create_account(
            db_session, budget, "Harborstone Reserve", account_type="savings", on_budget=False
        )
        await db_session.commit()
        resp = await api_client.patch(
            f"/api/v1/accounts/{reserve.id}", json={"counts_toward_emergency_fund": True}
        )
        assert resp.status_code == 200, resp.text
        assert await _counted(db_session, budget) == {"Harborstone Reserve"}

        resp = await api_client.patch(f"/api/v1/accounts/{reserve.id}", json={"on_budget": True})
        assert resp.status_code == 200, resp.text
        assert resp.json()["counts_toward_emergency_fund"] is True, "the choice is kept"
        assert await _counted(db_session, budget) == set()

    async def test_closed_or_not_savings_reads_false_and_is_no_candidate(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        closed = await create_account(
            db_session, budget, "Old Reserve", account_type="savings", on_budget=False
        )
        stopped = await create_account(
            db_session, budget, "Cascade Point HYSA", account_type="savings", on_budget=False
        )
        open_ = await create_account(
            db_session, budget, "Harborstone Reserve", account_type="savings", on_budget=False
        )
        for account in (closed, stopped, open_):
            account.counts_toward_emergency_fund = True
        closed.is_closed = True
        stopped.counts_as_savings = False
        await db_session.flush()

        assert await _counted(db_session, budget) == {"Harborstone Reserve"}
        assert await _counted(db_session, budget, EMERGENCY_FUND_ACCOUNT_CANDIDATE) == {
            "Harborstone Reserve"
        }

    async def test_a_candidate_need_not_be_marked(self, db_session):
        from .factories import create_user

        budget = await create_budget(db_session, await create_user(db_session))
        await create_account(
            db_session, budget, "Harborstone Reserve", account_type="savings", on_budget=False
        )
        await create_account(db_session, budget, "Harborstone Checking")
        assert await _counted(db_session, budget, EMERGENCY_FUND_ACCOUNT_CANDIDATE) == {
            "Harborstone Reserve"
        }
        assert await _counted(db_session, budget) == set()


class TestUndoAndExport:
    async def test_undo_restores_the_flag(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        reserve = await create_account(
            db_session, budget, "Harborstone Reserve", account_type="savings", on_budget=False
        )
        await db_session.commit()
        resp = await api_client.patch(
            f"/api/v1/accounts/{reserve.id}", json={"counts_toward_emergency_fund": True}
        )
        assert resp.status_code == 200, resp.text

        resp = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert resp.status_code == 200, resp.text
        assert (resp.json()["entity_type"], resp.json()["action"]) == ("account", "update")
        [after] = await _accounts(api_client, budget)
        assert after["counts_toward_emergency_fund"] is False

    async def test_the_export_carries_the_flag_and_a_re_import_reads_it(
        self, db_session, api_client
    ):
        from igab.integrations.ynab.parser import YNABParser

        budget = await _budget(db_session, api_client)
        reserve = await create_account(
            db_session, budget, "Harborstone Reserve", account_type="savings", on_budget=False
        )
        await create_account(db_session, budget, "Harborstone Checking")
        reserve.counts_toward_emergency_fund = True
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/budgets/{budget.id}/export?format=ynab")
        assert resp.status_code == 200, resp.text
        with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
            accounts_csv = archive.read("Accounts.csv").decode()
        assert "Counts Toward Emergency Fund" in accounts_csv.splitlines()[0]

        parsed = YNABParser().parse_accounts_csv(accounts_csv)
        assert parsed["harborstone reserve"].emergency_fund is True
        assert parsed["harborstone checking"].emergency_fund is False

    async def test_a_re_import_restores_the_flag_where_the_shape_allows(
        self, db_session, api_client
    ):
        """Written and read back, like every other column of the member. The
        mapping step decides the shape; a mark on an account it moved on
        budget is not carried, and the import is not refused for it."""
        import json
        from datetime import date

        from .factories import create_transaction

        budget = await _budget(db_session, api_client)
        reserve = await create_account(
            db_session, budget, "Harborstone Reserve", account_type="savings", on_budget=False
        )
        buffer = await create_account(
            db_session, budget, "Cascade Point HYSA", account_type="savings", on_budget=False
        )
        for account in (reserve, buffer):
            account.counts_toward_emergency_fund = True
            await create_transaction(db_session, budget, account, "1000", date(2026, 8, 3))
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/budgets/{budget.id}/export?format=ynab")
        assert resp.status_code == 200, resp.text
        mapping = {
            "Harborstone Reserve": {"account_type": "savings", "on_budget": False},
            "Cascade Point HYSA": {"account_type": "savings", "on_budget": True},
        }
        resp = await api_client.post(
            "/api/v1/budgets/import-ynab",
            files={"file": ("export.zip", resp.content, "application/zip")},
            data={"name": "Reimported", "account_types": json.dumps(mapping)},
        )
        assert resp.status_code in (200, 201), resp.text
        imported_id = resp.json()["budget"]["id"]

        flags = dict(
            (
                await db_session.execute(
                    select(Account.name, Account.counts_toward_emergency_fund).where(
                        Account.budget_id == imported_id
                    )
                )
            ).all()
        )
        assert flags == {"Harborstone Reserve": True, "Cascade Point HYSA": False}

    def test_an_export_without_the_column_reads_false(self):
        from igab.integrations.ynab.parser import YNABParser

        parsed = YNABParser().parse_accounts_csv(
            "Account,Type,Classification,On Budget,Counts As Savings,Closed,Note\n"
            "Harborstone Reserve,savings,asset,false,true,false,\n"
        )
        assert parsed["harborstone reserve"].emergency_fund is False
