"""Off-budget accounts don't use categories — nothing may nag about them.

Plain rows in tracking accounts (market adjustments, payroll contributions)
are net-worth movement, not unfiled spending: they must not appear in the
per-account uncategorized badge or the review inbox's uncategorized bucket.
Approval still applies everywhere, and the on-budget rules are unchanged —
including the "spending transfer missing its category" case.
"""

from datetime import date, timedelta

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()
OLD = TODAY - timedelta(days=10)


async def test_offbudget_rows_never_count_as_uncategorized(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Goals")
    investing = await create_category(db_session, budget, group, "Investing")

    # Checking: one genuinely unfiled row, one categorized spending-transfer
    # leg, and one spending-transfer leg MISSING its category
    await create_transaction(db_session, budget, checking, "-25.00", OLD)
    cat_leg = await create_transaction(
        db_session, budget, checking, "-800.00", OLD, category=investing
    )
    cat_partner = await create_transaction(
        db_session, budget, brokerage, "800.00", OLD, transfer_id=cat_leg.id
    )
    cat_leg.transfer_id = cat_partner.id
    bare_leg = await create_transaction(db_session, budget, checking, "-200.00", OLD)
    bare_partner = await create_transaction(
        db_session, budget, brokerage, "200.00", OLD, transfer_id=bare_leg.id
    )
    bare_leg.transfer_id = bare_partner.id

    # Brokerage: plain uncategorized activity, one row also unapproved
    await create_transaction(db_session, budget, brokerage, "250.00", OLD)
    await create_transaction(db_session, budget, brokerage, "-35.00", OLD)
    await create_transaction(db_session, budget, brokerage, "1150.00", OLD, approved=False)
    await db_session.flush()

    # Badge: checking counts its plain row + the category-less spending
    # transfer; the brokerage never asks for categories
    assert await services.account_repo.get_uncategorized_count(checking.id) == 2
    assert await services.account_repo.get_uncategorized_count(brokerage.id) == 0

    # Review inbox: only the on-budget plain row is "uncategorized"; the
    # off-budget unapproved row still needs its approval
    review = await services.transaction_repo.count_pending_review(budget.id)
    assert review["uncategorized"] == 1
    assert review["unapproved"] == 1
