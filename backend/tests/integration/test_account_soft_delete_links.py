"""Soft-deleting an account must unlink its CC-payment category — the FK's
ON DELETE SET NULL only fires on hard deletes, so without the repository doing
it the category keeps pointing at a deleted account."""

from igab.db.models import Category

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_user,
    make_services,
)


async def test_soft_delete_unlinks_payment_category(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    card = await create_account(db_session, budget, "Visa", account_type="credit_card")
    other = await create_account(db_session, budget, "Amex", account_type="credit_card")
    group = await create_category_group(db_session, budget, "Debt")
    payment_cat = await create_category(db_session, budget, group, "Visa Payment")
    other_cat = await create_category(db_session, budget, group, "Amex Payment")
    payment_cat.linked_account_id = card.id
    other_cat.linked_account_id = other.id
    await db_session.flush()

    await services.account_repo.soft_delete(card.id)

    refreshed = await db_session.get(Category, payment_cat.id)
    assert refreshed is not None
    await db_session.refresh(refreshed)
    assert refreshed.linked_account_id is None
    # Unrelated links stay intact
    untouched = await db_session.get(Category, other_cat.id)
    await db_session.refresh(untouched)
    assert untouched.linked_account_id == other.id
