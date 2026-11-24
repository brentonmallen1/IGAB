"""The merge preview says what the merge does — and the picks are honoured.

Two dialogs show a merge before it happens. Each composed its own picture of
the result on the client: the register's showed only which row was kept (a
split's category read as gone), and the duplicate review's was a second
implementation of the merge that the server never saw. `preview_merge` is the
server's own answer, built from the preparation `merge` writes from, and
these tests hold the two to each other: for every shape, the previewed row is
the row the merge leaves.

Invented fixtures: a grocery run entered by hand and the bank's copy.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.db.models import TransactionMatch
from igab.domain.exceptions import InvariantViolation
from igab.domain.merging import MergeKeep
from igab.services.transaction_service import SplitSpec

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_financial_invariants

DAY = date(2026, 7, 10)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    cats = {
        "groceries": await create_category(db_session, budget, group, "Groceries"),
        "household": await create_category(db_session, budget, group, "Household"),
    }
    payees = {
        "grocer": await create_payee(db_session, budget, "Corner Grocer"),
        "bank": await create_payee(db_session, budget, "CORNER GROCER 114"),
    }
    return services, budget, checking, cats, payees


async def _entered_and_bank(db_session, budget, account, cats, payees, **bank):
    entered = await create_transaction(
        db_session,
        budget,
        account,
        "-80.00",
        DAY,
        payee=payees["grocer"],
        category=cats["groceries"],
        memo="weekly shop",
        cleared="uncleared",
    )
    from_bank = await create_transaction(
        db_session,
        budget,
        account,
        bank.pop("amount", "-80.00"),
        DAY + timedelta(days=1),
        payee=payees["bank"],
        category=bank.pop("category", cats["household"]),
        memo=bank.pop("memo", "card purchase"),
        sync_id="TRN-1",
        sync_source="simplefin",
        bank_posted_date=DAY + timedelta(days=1),
        **bank,
    )
    return entered, from_bank


async def _assert_preview_is_the_merge(services, db_session, budget, ids, keep=None):
    """The differential: preview, then merge, then compare the row."""
    preview = await services.transactions.preview_merge(budget.id, ids, keep=keep)
    merged = await services.transactions.merge(budget.id, ids, keep=keep)
    await db_session.refresh(merged)
    assert merged.id == preview.survivor_id
    assert merged.date == preview.date
    assert merged.amount == preview.amount
    assert merged.payee_id == preview.payee_id
    assert merged.category_id == preview.category_id
    assert (merged.memo or None) == preview.memo
    assert merged.cleared == preview.cleared
    assert bool(merged.is_split) == preview.is_split
    lines = await services.transaction_repo.get_splits(merged.id)
    assert sorted((line.amount, line.category_id) for line in lines) == sorted(
        (line.amount, line.category_id) for line in preview.lines
    )
    await assert_financial_invariants(db_session, budget.id)
    return preview, merged


class TestPreviewIsTheMerge:
    async def test_the_ordinary_duplicate(self, db_session):
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(db_session, budget, checking, cats, payees)
        preview, merged = await _assert_preview_is_the_merge(
            services, db_session, budget, [entered.id, bank.id]
        )
        # The entered row survives with its own bookkeeping; the bank's copy
        # contributes its record and clears it.
        assert preview.survivor_id == entered.id
        assert preview.payee_id == payees["grocer"].id
        assert preview.category_id == cats["groceries"].id
        assert preview.memo == "weekly shop — card purchase"
        assert preview.cleared == "cleared"
        assert preview.has_bank_record
        assert preview.replaced_amount is None

    async def test_with_every_field_picked_from_the_bank_row(self, db_session):
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(db_session, budget, checking, cats, payees)
        keep = MergeKeep(date=bank.id, payee=bank.id, category=bank.id, memo=bank.id)
        preview, merged = await _assert_preview_is_the_merge(
            services, db_session, budget, [entered.id, bank.id], keep
        )
        assert preview.survivor_id == entered.id, "picks choose values, not the row"
        assert merged.date == DAY + timedelta(days=1)
        assert merged.payee_id == payees["bank"].id
        assert merged.category_id == cats["household"].id
        assert merged.memo == "card purchase"

    async def test_with_a_mix_of_picks(self, db_session):
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(db_session, budget, checking, cats, payees)
        keep = MergeKeep(payee=bank.id, memo=entered.id)
        preview, merged = await _assert_preview_is_the_merge(
            services, db_session, budget, [entered.id, bank.id], keep
        )
        assert merged.payee_id == payees["bank"].id
        assert merged.category_id == cats["groceries"].id
        assert merged.memo == "weekly shop"
        assert merged.date == DAY

    async def test_the_banks_amount_replaces_the_entered_one_and_the_preview_says_so(
        self, db_session
    ):
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(
            db_session, budget, checking, cats, payees, amount="-83.50"
        )
        preview, merged = await _assert_preview_is_the_merge(
            services, db_session, budget, [entered.id, bank.id]
        )
        assert preview.amount == Decimal("-83.50")
        assert preview.replaced_amount == Decimal("-80.00")

    async def test_a_split_keeps_its_lines(self, db_session):
        """The case the old dialog drew as a category simply disappearing."""
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(db_session, budget, checking, cats, payees)
        await services.transactions.convert_to_split(
            budget.id,
            entered.id,
            [
                SplitSpec(amount=Decimal("-62.00"), category_id=cats["groceries"].id),
                SplitSpec(amount=Decimal("-18.00"), category_id=cats["household"].id),
            ],
        )
        await db_session.refresh(entered)
        preview, merged = await _assert_preview_is_the_merge(
            services, db_session, budget, [entered.id, bank.id]
        )
        assert preview.is_split and preview.category_id is None
        assert sorted(line.amount for line in preview.lines) == [
            Decimal("-62.00"),
            Decimal("-18.00"),
        ]
        book = preview.bookkeeping
        assert not book.category_id.choosable and not book.date.choosable
        assert book.category_id.source == entered.id

    async def test_a_reconciled_row_taking_a_split_in_carries_the_splits_lines(self, db_session):
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(
            db_session, budget, checking, cats, payees, cleared="reconciled"
        )
        await services.transactions.convert_to_split(
            budget.id,
            entered.id,
            [
                SplitSpec(amount=Decimal("-62.00"), category_id=cats["groceries"].id),
                SplitSpec(amount=Decimal("-18.00"), category_id=cats["household"].id),
            ],
        )
        await db_session.refresh(entered)
        preview, merged = await _assert_preview_is_the_merge(
            services, db_session, budget, [entered.id, bank.id]
        )
        assert preview.survivor_id == bank.id, "the reconciled row is kept"
        assert preview.is_split and len(preview.lines) == 2
        assert preview.bookkeeping.category_id.source == entered.id

    async def test_a_reconciled_survivor_keeps_its_date_whatever_is_picked(self, db_session):
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(
            db_session, budget, checking, cats, payees, cleared="reconciled"
        )
        preview, merged = await _assert_preview_is_the_merge(
            services, db_session, budget, [entered.id, bank.id], MergeKeep(date=entered.id)
        )
        assert preview.survivor_id == bank.id
        assert merged.date == DAY + timedelta(days=1)
        assert not preview.bookkeeping.date.choosable


class TestWhatThePreviewReports:
    async def test_which_fields_were_a_choice_and_where_each_came_from(self, db_session):
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(db_session, budget, checking, cats, payees)
        book = (
            await services.transactions.preview_merge(budget.id, [entered.id, bank.id])
        ).bookkeeping
        assert all(k.choosable for k in (book.date, book.payee_id, book.category_id, book.memo))
        assert book.date.source == book.payee_id.source == book.category_id.source == entered.id
        assert book.memo.source == "both"

        picked = (
            await services.transactions.preview_merge(
                budget.id, [entered.id, bank.id], keep=MergeKeep(payee=bank.id)
            )
        ).bookkeeping
        assert picked.payee_id.source == bank.id

    async def test_it_writes_nothing(self, db_session):
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(db_session, budget, checking, cats, payees)
        await services.transactions.preview_merge(
            budget.id, [entered.id, bank.id], keep=MergeKeep(payee=bank.id)
        )
        await db_session.refresh(entered)
        await db_session.refresh(bank)
        assert not entered.is_deleted and not bank.is_deleted
        assert entered.payee_id == payees["grocer"].id and entered.cleared == "uncleared"

    async def test_a_merge_that_would_be_refused_is_refused_in_the_same_words(self, db_session):
        services, budget, checking, cats, payees = await _setup(db_session)
        a = await create_transaction(db_session, budget, checking, "-50.00", DAY)
        b = await create_transaction(db_session, budget, checking, "-49.00", DAY)
        with pytest.raises(InvariantViolation, match="identical amounts"):
            await services.transactions.preview_merge(budget.id, [a.id, b.id])

    async def test_a_pick_from_a_third_row_is_refused(self, db_session):
        services, budget, checking, cats, payees = await _setup(db_session)
        entered, bank = await _entered_and_bank(db_session, budget, checking, cats, payees)
        other = await create_transaction(db_session, budget, checking, "-80.00", DAY)
        for call in (services.transactions.preview_merge, services.transactions.merge):
            with pytest.raises(InvariantViolation, match="one of the two"):
                await call(budget.id, [entered.id, bank.id], keep=MergeKeep(payee=other.id))


class TestEndpoints:
    async def _pair(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        cats = {
            "groceries": await create_category(db_session, budget, group, "Groceries"),
            "household": await create_category(db_session, budget, group, "Household"),
        }
        payees = {
            "grocer": await create_payee(db_session, budget, "Corner Grocer"),
            "bank": await create_payee(db_session, budget, "CORNER GROCER 114"),
        }
        entered, bank = await _entered_and_bank(db_session, budget, checking, cats, payees)
        await db_session.commit()
        return budget, checking, cats, payees, entered, bank

    async def test_preview_then_merge_with_the_same_body(self, api_client, db_session):
        budget, checking, cats, payees, entered, bank = await self._pair(api_client, db_session)
        body = {
            "transaction_ids": [str(entered.id), str(bank.id)],
            "keep": {"payee": str(bank.id), "memo": str(entered.id)},
        }
        r = await api_client.post(f"/api/v1/{budget.id}/transactions/merge/preview", json=body)
        assert r.status_code == 200, r.text
        preview = r.json()
        assert preview["payee_id"] == str(payees["bank"].id)
        assert preview["memo"] == "weekly shop"
        assert preview["choices"]["payee"] == {"source": str(bank.id), "choosable": True}
        assert preview["choices"]["memo"] == {"source": str(entered.id), "choosable": True}
        assert preview["lines"] == [] and preview["transfer"] is None

        r = await api_client.post(f"/api/v1/{budget.id}/transactions/merge", json=body)
        assert r.status_code == 200, r.text
        merged = r.json()
        for field in ("date", "amount", "payee_id", "category_id", "memo", "cleared"):
            assert merged[field] == preview[field], field

    async def test_preview_of_a_refused_merge_is_a_400_with_the_reason(
        self, api_client, db_session
    ):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        a = await create_transaction(db_session, budget, checking, "-50.00", DAY)
        b = await create_transaction(db_session, budget, checking, "-49.00", DAY)
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/transactions/merge/preview",
            json={"transaction_ids": [str(a.id), str(b.id)]},
        )
        assert r.status_code == 400
        assert "identical amounts" in r.json()["detail"]

    async def test_accepting_a_match_takes_the_reviews_picks(self, api_client, db_session):
        budget, checking, cats, payees, entered, bank = await self._pair(api_client, db_session)
        match = TransactionMatch(
            synced_transaction_id=bank.id,
            manual_transaction_id=entered.id,
            confidence_score=Decimal("0.8"),
            status="pending",
        )
        db_session.add(match)
        await db_session.commit()

        r = await api_client.post(
            f"/api/v1/simplefin/matches/{match.id}/accept",
            json={"keep": {"category": str(bank.id)}},
        )
        assert r.status_code == 204, r.text
        rows = (await api_client.get(f"/api/v1/accounts/{checking.id}/transactions")).json()
        assert len(rows) == 1
        assert rows[0]["category_id"] == str(cats["household"].id)
        assert rows[0]["payee_id"] == str(payees["grocer"].id)

    async def test_accepting_with_no_body_is_the_merge_it_always_was(self, api_client, db_session):
        budget, checking, cats, payees, entered, bank = await self._pair(api_client, db_session)
        match = TransactionMatch(
            synced_transaction_id=bank.id,
            manual_transaction_id=entered.id,
            confidence_score=Decimal("0.8"),
            status="pending",
        )
        db_session.add(match)
        await db_session.commit()
        r = await api_client.post(f"/api/v1/simplefin/matches/{match.id}/accept")
        assert r.status_code == 204, r.text
        rows = (await api_client.get(f"/api/v1/accounts/{checking.id}/transactions")).json()
        assert rows[0]["category_id"] == str(cats["groceries"].id)
        assert rows[0]["memo"] == "weekly shop — card purchase"
