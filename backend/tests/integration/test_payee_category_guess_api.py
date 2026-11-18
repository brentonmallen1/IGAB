"""GET /{budget}/payees/{payee}/category-guess — what Save would file.

The editors pre-fill from this, so it must agree with `_create` exactly
(both call `TransactionService.guess_category_for`), and it is asked on every
payee pick and amount edit, so its cost is pinned: the history query, plus
one more only for a payee with no history.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    make_services,
)
from .statement_counts import count_request


async def _budget(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    return budget, checking, group


async def _seed(db_session, budget, account, payee, spec, start=date(2026, 1, 1)):
    for i, (amount, cat) in enumerate(spec):
        await create_transaction(
            db_session,
            budget,
            account,
            amount,
            start + timedelta(days=3 * i),
            category=cat,
            payee=payee,
        )
    await db_session.flush()


def _path(budget, payee):
    return f"/api/v1/{budget.id}/payees/{payee.id}/category-guess"


async def _guess(api_client, budget, payee, amount: str):
    resp = await api_client.get(_path(budget, payee), params={"amount": amount})
    assert resp.status_code == 200, resp.text
    return resp.json()["category_id"]


async def test_guess_matches_what_save_files(api_client, db_session):
    budget, checking, group = await _budget(api_client, db_session)
    groceries = await create_category(db_session, budget, group, "Groceries")
    membership = await create_category(db_session, budget, group, "Club Membership")
    household = await create_category(db_session, budget, group, "Household")
    club = await create_payee(db_session, budget, "Northwind Warehouse Club")
    spec = [
        ("-140.00", groceries), ("-38.00", household), ("-155.00", groceries),
        ("-150.00", household), ("-42.00", groceries), ("-60.00", membership),
        ("-48.00", groceries), ("-145.00", household), ("-52.00", groceries),
        ("-170.00", household),
    ]  # fmt: skip
    await _seed(db_session, budget, checking, club, spec)

    services = make_services(db_session)
    for amount in ("-152.00", "-60.00", "-41.00"):
        shown = await _guess(api_client, budget, club, amount)
        saved = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 6, 1),
                amount=Decimal(amount),
                payee_id=club.id,
            ),
        )
        assert shown == (str(saved.category_id) if saved.category_id else None)
        # Undo the row's effect on the history so each amount asks the
        # same question Save just answered.
        await db_session.delete(saved)
        await db_session.flush()

    assert await _guess(api_client, budget, club, "-152.00") == str(groceries.id)
    assert await _guess(api_client, budget, club, "-60.00") == str(membership.id)


async def test_default_answers_only_without_history(api_client, db_session):
    budget, checking, group = await _budget(api_client, db_session)
    dining = await create_category(db_session, budget, group, "Dining")
    misc = await create_category(db_session, budget, group, "Misc")
    cafe = await create_payee(db_session, budget, "Harborstone Cafe", default_category_id=dining.id)
    await db_session.flush()

    assert await _guess(api_client, budget, cafe, "-14.00") == str(dining.id)

    await _seed(db_session, budget, checking, cafe, [("-9.00", misc)])
    assert await _guess(api_client, budget, cafe, "-14.00") == str(misc.id)


async def test_a_default_that_may_not_be_filed_to_answers_null(api_client, db_session):
    budget, _, group = await _budget(api_client, db_session)
    archived = await create_category(db_session, budget, group, "Old Envelope")
    archived.is_archived = True
    shop = await create_payee(
        db_session, budget, "Cascade Point Shop", default_category_id=archived.id
    )
    await db_session.flush()

    assert await _guess(api_client, budget, shop, "-5.00") is None


async def test_a_payee_from_another_budget_answers_null(api_client, db_session):
    budget, checking, group = await _budget(api_client, db_session)
    other, other_checking, other_group = await _budget(api_client, db_session)
    theirs = await create_category(db_session, other, other_group, "Theirs")
    payee = await create_payee(db_session, other, "Sapphire Outlet", default_category_id=theirs.id)
    await _seed(db_session, other, other_checking, payee, [("-5.00", theirs)])

    assert await _guess(api_client, budget, payee, "-5.00") is None


async def test_the_guess_costs_the_history_query_plus_at_most_one(api_client, db_session):
    """Flat in history size, one statement reading transactions, and the
    default lookup only when there is no history to read."""
    budget, checking, group = await _budget(api_client, db_session)
    groceries = await create_category(db_session, budget, group, "Groceries")
    dining = await create_category(db_session, budget, group, "Dining")
    regular = await create_payee(db_session, budget, "Corner Market")
    fresh = await create_payee(db_session, budget, "Brand New Shop", default_category_id=dining.id)
    await _seed(
        db_session, budget, checking, regular, [(f"-{20 + i}.00", groceries) for i in range(5)]
    )

    params = {"amount": "-25.00"}
    small = await count_request(api_client, db_session, _path(budget, regular), params)

    await _seed(
        db_session,
        budget,
        checking,
        regular,
        [(f"-{40 + i}.00", groceries) for i in range(30)],
        start=date(2026, 3, 1),
    )
    large = await count_request(api_client, db_session, _path(budget, regular), params)
    assert large.selects == small.selects, "the guess asks per history row"

    reading_history = [s for s, _ in large.statements if "FROM transactions" in s]
    assert len(reading_history) == 1
    assert large.rows_fetched - small.rows_fetched <= 24 - 5, "history is not bounded"

    no_history = await count_request(api_client, db_session, _path(budget, fresh), params)
    assert no_history.selects == large.selects + 1
