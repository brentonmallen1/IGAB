"""The grouped rollup, and the vocabulary that makes it safe to expose.

Two things are under test here. The arithmetic: a GROUP BY over the whole
match, not over a page, because a model handed the sum of the first 200 rows
would report it as the answer. And the closure of the vocabulary: every way a
caller could try to reach past the dimensions this module defines ends in a
named error rather than a query.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from igab.domain.spending import (
    NO_CATEGORY_LABEL,
    OFF_BUDGET_LABEL,
    TRANSFER_LABEL,
    UNCATEGORIZED,
)
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import ON_BUDGET_ACCOUNT
from igab.repositories.txn_query import (
    AGGREGATES,
    DEFAULT_GROUPS,
    GROUPABLE,
    MAX_GROUPS,
    TransactionFilters,
    UnknownDimension,
    build_where,
    group_limit,
    grouped_totals,
)

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
        rolled = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(direction="outflow"),
        )
        groups, total = rolled.groups, rolled.total_groups
        by_name = {g["group"]: g["value"] for g in groups}
        assert by_name["Groceries"] == -600
        assert by_name["Fuel"] == -50
        assert total == 2

    async def test_totals_by_month(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        groups = (
            await grouped_totals(
                db_session,
                budget.id,
                group_by="month",
                filters=TransactionFilters(direction="outflow"),
            )
        ).groups
        by_month = {g["group"]: g["value"] for g in groups}
        assert by_month["2026-07"] == -300
        assert by_month["2026-08"] == -350

    async def test_totals_by_account(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        groups = (
            await grouped_totals(
                db_session,
                budget.id,
                group_by="account",
                filters=TransactionFilters(direction="outflow"),
            )
        ).groups
        by_account = {g["group"]: g["value"] for g in groups}
        assert by_account["Sapphire Visa"] == -350
        assert by_account["Harborstone"] == -300

    async def test_a_filter_narrows_the_total(self, db_session):
        """The whole point of sharing one clause: 'groceries on the card' is
        the listing's filter and the rollup's filter, spelled once."""
        budget, _checking, card, _groceries = await _budget_with_spending(db_session)
        groups = (
            await grouped_totals(
                db_session,
                budget.id,
                group_by="category",
                filters=TransactionFilters(account_ids=[card.id], direction="outflow"),
            )
        ).groups
        assert {g["group"]: g["value"] for g in groups} == {"Groceries": -300, "Fuel": -50}

    async def test_count_counts_rows_rather_than_money(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        groups = (
            await grouped_totals(
                db_session,
                budget.id,
                group_by="category",
                aggregate="count",
                filters=TransactionFilters(direction="outflow"),
            )
        ).groups
        assert {g["group"]: g["value"] for g in groups} == {"Groceries": 3, "Fuel": 1}

    async def test_the_group_count_is_the_whole_number_of_groups(self, db_session):
        """A capped list of groups must still say how many there were, or an
        assistant reports the top few as though they were all of them."""
        budget, *_ = await _budget_with_spending(db_session)
        rolled = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(direction="outflow"),
            limit=1,
        )
        groups, total = rolled.groups, rolled.total_groups
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

        groups = (
            await grouped_totals(
                db_session,
                budget.id,
                group_by="category",
                filters=TransactionFilters(direction="outflow"),
            )
        ).groups
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
        groups = (
            await grouped_totals(db_session, budget.id, group_by="category", filters=filters)
        ).groups

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
        groups = (
            await grouped_totals(
                db_session,
                budget.id,
                group_by="month",
                filters=TransactionFilters(payee_ids=[market.id]),
            )
        ).groups
        assert [(g["value"], g["rows"]) for g in groups] == [(-125, 3)]

    async def test_the_listing_and_the_rollup_still_agree_on_it(self, db_session):
        budget, market = await _split_at(db_session)
        _rows, count, total = await TransactionRepository(db_session).list_for_budget(
            budget.id, payee_ids=[market.id], scope="leaf"
        )
        groups = (
            await grouped_totals(
                db_session,
                budget.id,
                group_by="category",
                filters=TransactionFilters(payee_ids=[market.id]),
            )
        ).groups
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
        rolled = await grouped_totals(
            db_session,
            budget.id,
            group_by="payee",
            filters=TransactionFilters(start_date=date(2026, 8, 20), end_date=date(2026, 8, 20)),
        )
        assert [(g["group"], g["value"], g["rows"]) for g in rolled.groups] == [
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
        groups = (
            await grouped_totals(db_session, budget.id, group_by="payee", filters=filters)
        ).groups
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
        rolled = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(account_ids=[]),
        )
        groups, total_groups = rolled.groups, rolled.total_groups
        assert (count, groups, total_groups) == (0, [], 0)

    async def test_no_account_filter_is_still_every_account(self, db_session):
        budget, *_ = await _budget_with_spending(db_session)
        _rows, count, _total = await TransactionRepository(db_session).list_for_budget(
            budget.id, account_ids=None, scope="leaf"
        )
        assert count == 5


async def _envelopes(db_session, amounts: dict[str, str]):
    """One envelope per name, one row each on one on-budget account."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user, "Household")
    group = await create_category_group(db_session, budget, "Everyday")
    checking = await create_account(db_session, budget, "Harborstone")
    for name, amount in amounts.items():
        category = await create_category(db_session, budget, group, name)
        await create_transaction(
            db_session, budget, checking, amount, date(2026, 8, 4), category=category
        )
    await db_session.flush()
    return budget


class TestRankedBySize:
    """order="value" ranks by the absolute total, largest first.

    Signed descending put every inflow ahead of every outflow and the biggest
    outflows (most negative) last of all, so a limit cut exactly the spends
    the question was about: asked where August's money went, the assistant
    was shown the 22 smallest spends and none of the 9 largest.
    """

    async def test_the_largest_spends_survive_the_cut(self, db_session):
        budget = await _envelopes(
            db_session, {"Rent": "-1200", "Groceries": "-400", "Coffee": "-5", "Refunds": "50"}
        )
        rolled = await grouped_totals(db_session, budget.id, group_by="category", limit=2)
        assert [g["group"] for g in rolled.groups] == ["Rent", "Groceries"]

    async def test_an_inflow_does_not_outrank_a_bigger_spend_by_its_sign(self, db_session):
        budget = await _envelopes(db_session, {"Rent": "-1200", "Refunds": "50"})
        rolled = await grouped_totals(db_session, budget.id, group_by="category")
        assert [g["group"] for g in rolled.groups] == ["Rent", "Refunds"]

    async def test_a_tie_breaks_by_label(self, db_session):
        budget = await _envelopes(db_session, {"Beta": "-100", "Alpha": "100", "Gamma": "-100"})
        rolled = await grouped_totals(db_session, budget.id, group_by="category")
        assert [g["group"] for g in rolled.groups] == ["Alpha", "Beta", "Gamma"]

    async def test_rows_order_breaks_its_ties_by_label_too(self, db_session):
        budget = await _envelopes(db_session, {"Beta": "-1", "Alpha": "-900"})
        rolled = await grouped_totals(db_session, budget.id, group_by="category", order="rows")
        assert [g["group"] for g in rolled.groups] == ["Alpha", "Beta"]

    async def test_group_order_is_by_name(self, db_session):
        budget = await _envelopes(db_session, {"Beta": "-900", "Alpha": "-1"})
        rolled = await grouped_totals(db_session, budget.id, group_by="category", order="group")
        assert [g["group"] for g in rolled.groups] == ["Alpha", "Beta"]


class TestWhatTheCutLeftOut:
    """Computed over every group, so a cut list can say what it cut."""

    async def test_sum_states_the_whole_total_and_the_rest(self, db_session):
        budget = await _envelopes(
            db_session, {"Rent": "-1200", "Groceries": "-400", "Coffee": "-5", "Refunds": "50"}
        )
        rolled = await grouped_totals(db_session, budget.id, group_by="category", limit=2)
        assert rolled.total_groups == 4
        assert rolled.omitted_groups == 2
        assert rolled.total == Decimal("-1555")
        # Coffee and Refunds: -5 + 50.
        assert rolled.omitted_value == Decimal("45")

    async def test_count_states_the_whole_row_count_and_the_rest(self, db_session):
        budget = await _envelopes(db_session, {"Rent": "-1200", "Groceries": "-400", "Fuel": "-60"})
        rolled = await grouped_totals(
            db_session, budget.id, group_by="category", aggregate="count", limit=1
        )
        assert (rolled.total, rolled.omitted_groups, rolled.omitted_value) == (3, 2, 2)

    @pytest.mark.parametrize("aggregate", ["avg", "min", "max"])
    async def test_a_non_additive_aggregate_states_only_how_many_were_cut(
        self, db_session, aggregate
    ):
        """A sum of averages means nothing, so no figure is offered for it."""
        budget = await _envelopes(db_session, {"Rent": "-1200", "Groceries": "-400", "Fuel": "-60"})
        rolled = await grouped_totals(
            db_session, budget.id, group_by="category", aggregate=aggregate, limit=1
        )
        assert (rolled.total, rolled.omitted_value, rolled.omitted_groups) == (None, None, 2)

    async def test_nothing_cut_omits_nothing(self, db_session):
        budget = await _envelopes(db_session, {"Rent": "-1200", "Fuel": "-60"})
        rolled = await grouped_totals(db_session, budget.id, group_by="category")
        assert (rolled.omitted_groups, rolled.omitted_value, rolled.total) == (
            0,
            Decimal("0"),
            Decimal("-1260"),
        )


class TestOneLimit:
    """The default and the ceiling, written once (`group_limit`).

    Each test names a copy that used to disagree: the handler, the
    repository wrapper and the registry text said 25 by default and the
    handler capped at 100, while `grouped_totals` defaulted to 50 and capped
    at 200 — and only the handler had a floor.
    """

    def test_the_default_is_default_groups_not_the_handlers_25(self):
        assert group_limit(None) == DEFAULT_GROUPS == 50

    def test_the_ceiling_is_max_groups_not_txn_querys_200(self):
        assert group_limit(500) == MAX_GROUPS == 100

    def test_a_limit_below_one_still_asks_for_one_group(self):
        """`grouped_totals` had no floor: 0 returned no groups and a
        negative limit was a Postgres error."""
        assert group_limit(0) == 1
        assert group_limit(-5) == 1

    def test_an_unreadable_limit_is_the_default(self):
        assert group_limit("plenty") == DEFAULT_GROUPS
        assert group_limit(True) == DEFAULT_GROUPS
        assert group_limit("30") == 30

    async def test_grouped_totals_uses_the_one_clamp(self, db_session):
        budget = await _envelopes(db_session, {"Rent": "-1200", "Fuel": "-60"})
        assert len((await grouped_totals(db_session, budget.id, group_by="category")).groups) == 2
        for limit in (0, -3):
            rolled = await grouped_totals(db_session, budget.id, group_by="category", limit=limit)
            assert [g["group"] for g in rolled.groups] == ["Rent"]


async def _budget_with_tracking_accounts(db_session):
    """Every reason a row can carry no category, one row each, in August.

    - Groceries -400 on checking: filed.
    - A +9,000 market adjustment on an off-budget brokerage: Off-budget.
    - A 1,500 mortgage payment from checking to an off-budget loan: the
      checking leg needs a category (it is budget cash flow), the loan leg is
      Off-budget.
    - A 500 move from checking to an on-budget HYSA: two Transfer legs.
    - A -75 row dated before its account's budget start: No category.
    """
    user = await create_user(db_session)
    budget = await create_budget(db_session, user, "Household")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    checking = await create_account(db_session, budget, "Harborstone Checking")
    hysa = await create_account(db_session, budget, "Cascade Point HYSA", account_type="savings")
    brokerage = await create_account(
        db_session, budget, "Northwind Brokerage", account_type="investment", on_budget=False
    )
    loan = await create_account(
        db_session, budget, "Harborstone Mortgage", account_type="mortgage", on_budget=False
    )
    joint = await create_account(db_session, budget, "Harborstone Joint")
    joint.budget_start_date = date(2026, 8, 15)
    await db_session.flush()

    when = date(2026, 8, 10)
    await create_transaction(db_session, budget, checking, "-400", when, category=groceries)
    await create_transaction(db_session, budget, brokerage, "9000", when)
    await create_transfer(db_session, budget, checking, loan, "1500", when)
    await create_transfer(db_session, budget, checking, hysa, "500", when)
    await create_transaction(db_session, budget, joint, "-75", date(2026, 8, 5))
    await db_session.flush()
    return budget, brokerage


#: The assistant's default scope, as `_filters_from_args` builds it.
BUDGET_MONEY = TransactionFilters(on_budget_only=True, cash_flow_only=True)


class TestWhyARowHasNoCategory:
    """`Uncategorized` means what the register's filter means (`NEEDS_CATEGORY`).

    The rollup coalesced every NULL category to it, so a tracking account's
    market adjustment and a mortgage's loan leg ranked "Uncategorized" first,
    positive, at several times the month's spending.
    """

    @pytest.mark.parametrize(
        ("group_by", "filed"), [("category", "Groceries"), ("category_group", "Everyday")]
    )
    async def test_each_reason_has_its_own_label(self, db_session, group_by, filed):
        budget, _ = await _budget_with_tracking_accounts(db_session)
        rolled = await grouped_totals(db_session, budget.id, group_by=group_by)
        assert {g["group"]: (g["value"], g["rows"]) for g in rolled.groups} == {
            filed: (Decimal("-400"), 1),
            OFF_BUDGET_LABEL: (Decimal("10500"), 2),
            UNCATEGORIZED: (Decimal("-1500"), 1),
            TRANSFER_LABEL: (Decimal("0"), 2),
            NO_CATEGORY_LABEL: (Decimal("-75"), 1),
        }

    async def test_the_uncategorized_line_is_the_registers_filter(self, db_session):
        budget, _ = await _budget_with_tracking_accounts(db_session)
        _rows, count, total = await TransactionRepository(db_session).list_for_budget(
            budget.id, uncategorized=True, scope="leaf"
        )
        rolled = await grouped_totals(db_session, budget.id, group_by="category")
        line = next(g for g in rolled.groups if g["group"] == UNCATEGORIZED)
        assert (line["rows"], line["value"]) == (count, total)


class TestTheBudgetsOwnMoney:
    """`on_budget_only` + `cash_flow_only`: the assistant's default scope."""

    async def test_tracking_accounts_and_internal_transfers_are_left_out(self, db_session):
        budget, _ = await _budget_with_tracking_accounts(db_session)
        rolled = await grouped_totals(
            db_session, budget.id, group_by="category", filters=BUDGET_MONEY
        )
        # The mortgage payment's checking leg stays: money leaving the budget.
        assert {g["group"]: g["value"] for g in rolled.groups} == {
            UNCATEGORIZED: Decimal("-1500"),
            "Groceries": Decimal("-400"),
            NO_CATEGORY_LABEL: Decimal("-75"),
        }

    async def test_off_by_default_so_the_register_is_untouched(self, db_session):
        budget, _ = await _budget_with_tracking_accounts(db_session)
        _rows, count, _total = await TransactionRepository(db_session).list_for_budget(
            budget.id, scope="leaf"
        )
        assert count == 7
        default = build_where(budget.id, TransactionFilters()).where
        assert not any(clause is ON_BUDGET_ACCOUNT for clause in default)
        opted = build_where(budget.id, TransactionFilters(on_budget_only=True)).where
        assert any(clause is ON_BUDGET_ACCOUNT for clause in opted)

    async def test_on_budget_only_alone_keeps_internal_transfers(self, db_session):
        budget, _ = await _budget_with_tracking_accounts(db_session)
        rolled = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(on_budget_only=True),
        )
        assert OFF_BUDGET_LABEL not in {g["group"] for g in rolled.groups}
        assert TRANSFER_LABEL in {g["group"] for g in rolled.groups}

    async def test_naming_the_tracking_account_reaches_it(self, db_session):
        budget, brokerage = await _budget_with_tracking_accounts(db_session)
        rolled = await grouped_totals(
            db_session,
            budget.id,
            group_by="category",
            filters=TransactionFilters(account_ids=[brokerage.id]),
        )
        assert [(g["group"], g["value"]) for g in rolled.groups] == [
            (OFF_BUDGET_LABEL, Decimal("9000"))
        ]

    async def test_the_listing_and_the_rollup_agree_under_it(self, db_session):
        budget, _ = await _budget_with_tracking_accounts(db_session)
        _rows, count, total = await TransactionRepository(db_session).list_for_budget(
            budget.id, on_budget_only=True, cash_flow_only=True, scope="leaf"
        )
        rolled = await grouped_totals(
            db_session, budget.id, group_by="category", filters=BUDGET_MONEY
        )
        assert (sum(g["rows"] for g in rolled.groups), rolled.total) == (count, total)
        assert (count, total) == (3, Decimal("-1975"))
