"""The grouped rollup, and the vocabulary that makes it safe to expose.

Two things are under test here. The arithmetic: a GROUP BY over the whole
match, not over a page, because a model handed the sum of the first 200 rows
would report it as the answer. And the closure of the vocabulary: every way a
caller could try to reach past the dimensions this module defines ends in a
named error rather than a query.
"""

import uuid
from datetime import date

import pytest

from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_query import (
    AGGREGATES,
    GROUPABLE,
    TransactionFilters,
    UnknownDimension,
    build_where,
    grouped_totals,
)

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
)


async def _budget_with_spending(db_session):
    """Two envelopes, two accounts, known amounts — round enough to check on
    paper, which is the only way an aggregate test is worth anything."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user, "Household")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    fuel = await create_category(db_session, budget, group, "Fuel")
    checking = await create_account(db_session, budget, "Harborstone")
    card = await create_account(db_session, budget, "Sapphire Visa")
    await db_session.flush()

    # Groceries: 100 + 200 on checking, 300 on the card = 600
    await create_transaction(
        db_session, budget, checking, "-100", date(2026, 7, 5), category=groceries
    )
    await create_transaction(
        db_session, budget, checking, "-200", date(2026, 7, 12), category=groceries
    )
    await create_transaction(db_session, budget, card, "-300", date(2026, 8, 3), category=groceries)
    # Fuel: 50 on the card
    await create_transaction(db_session, budget, card, "-50", date(2026, 8, 9), category=fuel)
    # An inflow, which most questions do not mean
    await create_transaction(db_session, budget, checking, "2000", date(2026, 7, 1))
    await db_session.flush()
    return budget, checking, card, groceries


class TestTheArithmetic:
    async def test_totals_by_category_over_the_whole_match(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        groups, total = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(direction="outflow"),
        )
        by_name = {g["group"]: g["value"] for g in groups}
        assert by_name["Groceries"] == -600
        assert by_name["Fuel"] == -50
        assert total == 2

    async def test_totals_by_month(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        groups, _ = await grouped_totals(
            db_session,
            budget.id,
            group_by="month",
            filters=TransactionFilters(direction="outflow"),
        )
        by_month = {g["group"]: g["value"] for g in groups}
        assert by_month["2026-07"] == -300
        assert by_month["2026-08"] == -350

    async def test_totals_by_account(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        groups, _ = await grouped_totals(
            db_session,
            budget.id,
            group_by="account",
            filters=TransactionFilters(direction="outflow"),
        )
        by_account = {g["group"]: g["value"] for g in groups}
        assert by_account["Sapphire Visa"] == -350
        assert by_account["Harborstone"] == -300

    async def test_a_filter_narrows_the_total(self, db_session):
        """The whole point of sharing one clause: 'groceries on the card' is
        the listing's filter and the rollup's filter, spelled once."""
        budget, _checking, card, _groceries = await _budget_with_spending(db_session)
        groups, _ = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(account_ids=[card.id], direction="outflow"),
        )
        assert {g["group"]: g["value"] for g in groups} == {"Groceries": -300, "Fuel": -50}

    async def test_count_counts_rows_rather_than_money(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        groups, _ = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            aggregate="count",
            filters=TransactionFilters(direction="outflow"),
        )
        assert {g["group"]: g["value"] for g in groups} == {"Groceries": 3, "Fuel": 1}

    async def test_the_group_count_is_the_whole_number_of_groups(self, db_session):
        """A capped list of groups must still say how many there were, or an
        assistant reports the top few as though they were all of them."""
        budget, *_ = await _budget_with_spending(db_session)
        groups, total = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(direction="outflow"),
            limit=1,
        )
        assert len(groups) == 1
        assert total == 2


class TestTheVocabularyIsClosed:
    """What makes this safe to hand a model.

    Nothing a caller writes becomes SQL. These are the ways someone might
    try, and each one is a named error instead.
    """

    @pytest.mark.parametrize(
        "attempt",
        [
            "amount; DROP TABLE transactions",
            "(SELECT password_hash FROM users)",
            "budget_id",
            "",
            "Category.name",
        ],
    )
    async def test_an_unknown_group_by_is_refused(self, db_session, attempt):
        budget, *_ = await _budget_with_spending(db_session)
        with pytest.raises(UnknownDimension) as raised:
            await grouped_totals(db_session, budget.id, group_by=attempt)
        # The error names what IS allowed: a model that guessed wrong can
        # correct itself rather than guess again.
        assert "category" in str(raised.value)

    async def test_an_unknown_aggregate_is_refused(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        with pytest.raises(UnknownDimension):
            await grouped_totals(
                db_session, budget.id, group_by="category", aggregate="sum(1); DELETE FROM"
            )

    def test_every_dimension_is_an_expression_this_module_built(self):
        """Not a string. There is no code path that turns a caller's text
        into a column, which is the property the whole design rests on."""
        for name, dimension in GROUPABLE.items():
            assert not isinstance(dimension.expression, str), name
        for name, make in AGGREGATES.items():
            assert callable(make), name

    async def test_the_budget_is_never_widened(self, db_session):
        """Another budget's rows are not reachable through any argument —
        budget_id is a parameter of the call, not of the query."""
        budget, *_ = await _budget_with_spending(db_session)
        other_user = await create_user(db_session, email="other@example.com")
        other = await create_budget(db_session, other_user, "Someone else")
        other_group = await create_category_group(db_session, other, "Everyday")
        other_cat = await create_category(db_session, other, other_group, "Groceries")
        other_account = await create_account(db_session, other, "Their bank")
        await db_session.flush()
        await create_transaction(
            db_session, other, other_account, "-999", date(2026, 7, 7), category=other_cat
        )
        await db_session.flush()

        groups, _ = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(direction="outflow"),
        )
        assert all(g["value"] != -999 for g in groups)
        assert {g["group"] for g in groups} == {"Groceries", "Fuel"}


class TestOneClauseBothCallers:
    async def test_the_listing_and_the_rollup_agree(self, db_session):
        """The reason the clause moved into its own module. If these two ever
        disagree, a chat answer contradicts the register it came from."""
        budget, _checking, card, _groceries = await _budget_with_spending(db_session)
        repo = TransactionRepository(db_session)
        filters = TransactionFilters(account_ids=[card.id], direction="outflow")

        _rows, count, total = await repo.list_for_budget(
            budget.id,
            account_ids=[card.id],
            direction="outflow",
            scope="leaf",
        )
        groups, _ = await grouped_totals(
            db_session, budget.id, group_by="category", filters=filters
        )

        assert sum(g["value"] for g in groups) == total
        assert sum(g["rows"] for g in groups) == count

    def test_build_where_needs_no_database(self):
        """Pure, so every branch of a hundred-line clause is testable without
        one. That is what keeps it honest as it grows."""
        parts = build_where(uuid.uuid4(), TransactionFilters(search="coffee"), scope="leaf")
        assert parts.payee_join is True
        assert parts.class_joins is False
        assert len(parts.where) >= 3


async def _split_at(db_session):
    """A -100 split at Harborstone Market — the payee on the parent only, as
    the app's split editor writes it — beside a plain -25 there."""
    budget, checking, _card, groceries = await _budget_with_spending(db_session)
    market = await create_payee(db_session, budget, "Harborstone Market")
    when = date(2026, 8, 20)
    parent = await create_transaction(
        db_session, budget, checking, "-100", when, payee=market, is_split=True
    )
    for amount in ("-60", "-40"):
        await create_transaction(
            db_session,
            budget,
            checking,
            amount,
            when,
            category=groceries,
            parent_transaction_id=parent.id,
        )
    await create_transaction(db_session, budget, checking, "-25", when, payee=market)
    await db_session.flush()
    return budget, market


class TestThePayeeFilter:
    """The filter reads the payee of record (`PAYEE_OF_RECORD`), which the
    Pareto and Payee Analysis bars rank by."""

    async def test_the_rollup_counts_a_split_by_the_payee_its_parent_names(self, db_session):
        # The assistant's grouped query: leaf scope, like the listing's drill.
        # The raw column matched only the plain -25.
        budget, market = await _split_at(db_session)
        groups, _ = await grouped_totals(
            db_session,
            budget.id,
            group_by="month",
            filters=TransactionFilters(payee_ids=[market.id]),
        )
        assert [(g["value"], g["rows"]) for g in groups] == [(-125, 3)]

    async def test_the_listing_and_the_rollup_still_agree_on_it(self, db_session):
        budget, market = await _split_at(db_session)
        _rows, count, total = await TransactionRepository(db_session).list_for_budget(
            budget.id, payee_ids=[market.id], scope="leaf"
        )
        groups, _ = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(payee_ids=[market.id]),
        )
        assert (count, total) == (3, -125)
        assert sum(g["value"] for g in groups) == total

    async def test_an_empty_payee_list_matches_nothing(self, db_session):
        """The assistant's tools pass [] for a payee name that resolved to
        nobody, and say "nothing was searched". A truthiness test read [] as
        no filter and answered with the whole budget."""
        budget, _market = await _split_at(db_session)
        _rows, count, _total = await TransactionRepository(db_session).list_for_budget(
            budget.id, payee_ids=[], scope="leaf"
        )
        assert count == 0

    async def test_the_payee_rollup_files_a_split_under_the_shop_its_parent_names(self, db_session):
        """The MCP grouped query's payee dimension grouped by the raw column,
        so the -100 split's legs (payee on the parent only) read "(no payee)"
        beside the same shop's -25."""
        budget, market = await _split_at(db_session)
        groups, _ = await grouped_totals(
            db_session,
            budget.id,
            group_by="payee",
            filters=TransactionFilters(start_date=date(2026, 8, 20), end_date=date(2026, 8, 20)),
        )
        assert [(g["group"], g["value"], g["rows"]) for g in groups] == [
            ("Harborstone Market", -125, 3)
        ]

    async def test_a_payee_rollup_and_a_search_still_agree(self, db_session):
        """The dimension joins its own alias: `search` still matches the row's
        own payee, as the listing's does, under a payee rollup."""
        budget, market = await _split_at(db_session)
        filters = TransactionFilters(search="Harborstone Market")
        _rows, count, total = await TransactionRepository(db_session).list_for_budget(
            budget.id, search="Harborstone Market", scope="leaf"
        )
        groups, _ = await grouped_totals(db_session, budget.id, group_by="payee", filters=filters)
        assert sum(g["rows"] for g in groups) == count
        assert sum(g["value"] for g in groups) == total

    def test_only_a_payee_filter_asks_for_the_split_parent(self):
        budget_id = uuid.uuid4()
        asked = build_where(budget_id, TransactionFilters(payee_ids=[uuid.uuid4()]))
        assert asked.split_parent_join is True
        assert build_where(budget_id, TransactionFilters()).split_parent_join is False


class TestTheAccountFilter:
    async def test_an_empty_account_list_matches_nothing(self, db_session):
        """The assistant's tools pass [] for an account name that resolved to
        nothing, and say "nothing was searched". A truthiness test read [] as
        no filter and answered with every row in the budget — the payee
        filter's bug, which was fixed on its own."""
        budget, *_ = await _budget_with_spending(db_session)
        _rows, count, _total = await TransactionRepository(db_session).list_for_budget(
            budget.id, account_ids=[], scope="leaf"
        )
        groups, total_groups = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(account_ids=[]),
        )
        assert (count, groups, total_groups) == (0, [], 0)

    async def test_no_account_filter_is_still_every_account(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        _rows, count, _total = await TransactionRepository(db_session).list_for_budget(
            budget.id, account_ids=None, scope="leaf"
        )
        assert count == 5
