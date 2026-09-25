"""A card's starting balance and reconcile adjustments need no category.

They correct the card's own ledger: the debt a card arrived with, or the
difference a reconcile found. No envelope paid for either, so the debt sits
in the card's Not covered and is retired by assigning to the card. Asking for
a category put "1 to categorize" on every card created with a balance, for
good — seven of seventeen sample cards — and filing one in an envelope would
book old debt as this month's spending.

Bounded on purpose: only those payee names, only on cards. An ordinary card
charge still needs a category, and a starting balance on a cash account is
untouched (YNAB files it to Ready to Assign, and so may the user).
"""

from datetime import date, timedelta

from igab.domain.payee_names import (
    RECONCILIATION_ADJUSTMENT_PAYEE,
    STARTING_BALANCE_PAYEE,
)

from .factories import (
    create_account,
    create_budget,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)

OLD = date.today() - timedelta(days=10)


async def _world(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    checking = await create_account(db_session, budget, "Harborstone Checking")
    starting = await create_payee(db_session, budget, STARTING_BALANCE_PAYEE)
    adjustment = await create_payee(db_session, budget, RECONCILIATION_ADJUSTMENT_PAYEE)
    shop = await create_payee(db_session, budget, "Corner Shop")
    await create_transaction(db_session, budget, card, "-420.00", OLD, payee=starting)
    await create_transaction(db_session, budget, card, "-3.10", OLD, payee=adjustment)
    await create_transaction(db_session, budget, card, "-12.00", OLD, payee=shop)
    await create_transaction(db_session, budget, checking, "1500.00", OLD, payee=starting)
    await db_session.flush()
    return services, budget, card, checking


async def test_a_cards_ledger_corrections_need_no_category(db_session):
    services, _, card, _ = await _world(db_session)
    rows = await services.transaction_repo.get_for_account(card.id)
    flagged = {t.amount for t in rows if t.needs_category}
    assert [str(a) for a in flagged] == ["-12.0000"], "only the Corner Shop charge"
    assert await services.account_repo.get_uncategorized_count(card.id) == 1


async def test_a_starting_balance_on_cash_still_asks(db_session):
    services, _, _, checking = await _world(db_session)
    assert await services.account_repo.get_uncategorized_count(checking.id) == 1


async def test_the_badge_the_filter_and_the_flag_still_agree(db_session):
    services, budget, card, _ = await _world(db_session)
    review = await services.transaction_repo.count_pending_review(budget.id)
    rows, count, _ = await services.transaction_repo.list_for_budget(
        budget.id, scope="leaf", posted_only=True, uncategorized=True
    )
    assert count == len(rows) == review["uncategorized"] == 2
    filtered = await services.transaction_repo.get_for_account(card.id, uncategorized=True)
    assert len(filtered) == 1 and all(t.needs_category for t in filtered)
