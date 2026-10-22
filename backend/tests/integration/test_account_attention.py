"""What is waiting on an account — one set of rows, however it is counted.

The sidebar's per-account count and the account page's review banner each
spelled their own predicate. The banner scoped itself to
`parent_transaction_id IS NULL` by hand, which is right for approval (a split
is approved as a whole) and wrong for a category: an unfiled split LINE is
unfiled spending. The sidebar counted those lines; the banner did not. Both
now read AWAITING_CATEGORY / AWAITING_APPROVAL, and this file pins that they
agree — case by case, so the case that used to differ is named.
"""

from datetime import date

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


async def _setup(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    return budget, checking, groceries


async def _both_counts(db_session, account):
    services = make_services(db_session)
    sidebar = await services.account_repo.get_attention(account.id)
    banner = await services.transaction_repo.count_pending_review_for_account(account.id)
    return sidebar, banner


async def test_an_unfiled_split_line_counts_in_both(db_session):
    """The divergence: the banner skipped split lines."""
    budget, checking, groceries = await _setup(db_session)
    parent = await create_transaction(db_session, budget, checking, "-90.00", TODAY, is_split=True)
    await create_transaction(
        db_session,
        budget,
        checking,
        "-60.00",
        TODAY,
        category=groceries,
        parent_transaction_id=parent.id,
    )
    await create_transaction(
        db_session, budget, checking, "-30.00", TODAY, parent_transaction_id=parent.id
    )
    await db_session.flush()

    sidebar, banner = await _both_counts(db_session, checking)
    assert sidebar.uncategorized == 1
    assert banner["uncategorized"] == 1, "the banner used to read 0 here"
    assert banner["total"] == 1


async def test_a_split_is_approved_as_a_whole(db_session):
    """An unapproved split is one thing to approve, not one per line."""
    budget, checking, groceries = await _setup(db_session)
    parent = await create_transaction(
        db_session, budget, checking, "-90.00", TODAY, is_split=True, approved=False
    )
    for amount in ("-60.00", "-30.00"):
        await create_transaction(
            db_session,
            budget,
            checking,
            amount,
            TODAY,
            category=groceries,
            approved=False,
            parent_transaction_id=parent.id,
        )
    await db_session.flush()

    sidebar, banner = await _both_counts(db_session, checking)
    assert sidebar.unapproved == 1
    assert banner["unapproved"] == 1


async def test_both_halves_of_one_row_count_once_in_the_total(db_session):
    budget, checking, _ = await _setup(db_session)
    await create_transaction(db_session, budget, checking, "-12.00", TODAY, approved=False)
    await db_session.flush()

    sidebar, banner = await _both_counts(db_session, checking)
    assert (sidebar.uncategorized, sidebar.unapproved) == (1, 1)
    assert banner["both"] == 1 and banner["total"] == 1


async def test_pending_rows_are_on_their_way_not_waiting(db_session):
    """A pending row is counted as pending only — its amount is provisional,
    so it is not yet work to file or approve."""
    budget, checking, _ = await _setup(db_session)
    await create_transaction(
        db_session, budget, checking, "-40.00", TODAY, cleared="pending", approved=False
    )
    await db_session.flush()

    sidebar, banner = await _both_counts(db_session, checking)
    assert (sidebar.uncategorized, sidebar.unapproved, sidebar.pending) == (0, 0, 1)
    assert banner["total"] == 0


async def test_deleted_rows_count_nowhere(db_session):
    budget, checking, _ = await _setup(db_session)
    await create_transaction(
        db_session, budget, checking, "-40.00", TODAY, approved=False, is_deleted=True
    )
    await create_transaction(
        db_session, budget, checking, "-40.00", TODAY, cleared="pending", is_deleted=True
    )
    await db_session.flush()

    sidebar, banner = await _both_counts(db_session, checking)
    assert (sidebar.uncategorized, sidebar.unapproved, sidebar.pending) == (0, 0, 0)
    assert banner["total"] == 0


async def test_a_clear_account_reads_zero_without_a_row(db_session):
    """No rows at all: the grouped query returns nothing for the account, and
    the default is zeros rather than a missing key."""
    _, checking, _ = await _setup(db_session)
    services = make_services(db_session)
    counts = await services.account_repo.attention_counts_for([checking.id])
    assert counts[checking.id].uncategorized == 0
    assert counts[checking.id].pending == 0


async def test_the_list_endpoint_serves_all_three(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    await create_transaction(db_session, budget, checking, "-12.00", TODAY, approved=False)
    await create_transaction(db_session, budget, checking, "-40.00", TODAY, cleared="pending")
    await db_session.commit()

    r = await api_client.get(f"/api/v1/{budget.id}/accounts")
    assert r.status_code == 200, r.text
    [row] = r.json()
    assert (row["uncategorized_count"], row["unapproved_count"], row["pending_count"]) == (1, 1, 1)
