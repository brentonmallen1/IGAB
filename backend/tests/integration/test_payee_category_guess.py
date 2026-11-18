"""Auto-fill through `TransactionService._create` on a real database:
the repository's history order and filters, the per-payee rule in
domain/category_guess.py, and the service's precedence around it.

Payees and amounts are invented; the warehouse club is the shape of the bug
that made every grocery run file under the annual membership.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from igab.services.transaction_service import TransactionCreate

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


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    return services, budget, checking, group


async def _auto(services, budget, account, payee, amount: str, day: date):
    return await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=account.id, date=day, amount=Decimal(amount), payee_id=payee.id
        ),
    )


async def test_warehouse_club_grocery_run_is_not_filed_as_membership(db_session):
    services, budget, checking, group = await _setup(db_session)
    groceries = await create_category(db_session, budget, group, "Groceries")
    membership = await create_category(db_session, budget, group, "Club Membership")
    club = await create_payee(db_session, budget, "Northwind Warehouse Club")

    base = datetime(2026, 9, 1, tzinfo=UTC)
    runs = [
        (date(2026, 6, 14), "-195.00"),
        (date(2026, 7, 2), "-165.00"),
        (date(2026, 7, 19), "-120.00"),
        (date(2026, 8, 5), "-210.00"),
        (date(2026, 8, 22), "-150.00"),
        (date(2026, 9, 8), "-180.00"),
    ]
    for i, (day, amount) in enumerate(runs):
        row = await create_transaction(
            db_session, budget, checking, amount, day, category=groceries, payee=club
        )
        row.created_at = base + timedelta(minutes=i)
    # Same date as the last grocery run, entered after it.
    late = await create_transaction(
        db_session, budget, checking, "-60.00", date(2026, 9, 8), category=membership, payee=club
    )
    late.created_at = base + timedelta(hours=1)
    # A split parent is uncategorised and teaches nothing.
    await create_transaction(
        db_session, budget, checking, "-240.00", date(2026, 10, 1), payee=club, is_split=True
    )
    await db_session.flush()

    history = await services.transactions.transaction_repo.recent_categorized_for_payee(
        budget.id, club.id
    )
    # The tie that broke the old rule: the membership is "most recent".
    assert history[0].category_id == membership.id
    assert len(history) == len(runs) + 1

    grocery = await _auto(services, budget, checking, club, "-172.00", date(2026, 10, 15))
    assert grocery.category_id == groceries.id

    renewal = await _auto(services, budget, checking, club, "-60.00", date(2026, 10, 16))
    assert renewal.category_id == membership.id


async def test_mixed_payee_is_left_blank_even_with_a_default(db_session):
    services, budget, checking, group = await _setup(db_session)
    cats = [await create_category(db_session, budget, group, f"Env {n}") for n in range(4)]
    store = await create_payee(
        db_session, budget, "Everything Store", default_category_id=cats[0].id
    )
    amounts = ["-12.00", "-55.00", "-23.00", "-80.00", "-17.00", "-34.00", "-61.00", "-9.00"]
    for i, amount in enumerate(amounts):
        await create_transaction(
            db_session,
            budget,
            checking,
            amount,
            date(2026, 5, 1) + timedelta(days=i),
            category=cats[(i * 3 + i // 2) % 4],
            payee=store,
        )
    await db_session.flush()

    row = await _auto(services, budget, checking, store, "-30.00", date(2026, 6, 1))
    assert row.category_id is None


async def test_new_payee_uses_its_default_and_otherwise_stays_blank(db_session):
    services, budget, checking, group = await _setup(db_session)
    dining = await create_category(db_session, budget, group, "Dining")
    with_default = await create_payee(
        db_session, budget, "Harborstone Cafe", default_category_id=dining.id
    )
    without = await create_payee(db_session, budget, "Brand New Shop")
    await db_session.flush()

    first = await _auto(services, budget, checking, with_default, "-14.00", date(2026, 6, 1))
    assert first.category_id == dining.id

    blank = await _auto(services, budget, checking, without, "-14.00", date(2026, 6, 1))
    assert blank.category_id is None


async def test_alternating_subscription_amounts_follow_the_amount(db_session):
    """A→X / B→Y in an irregular order: the amount decides, not recency."""
    services, budget, checking, group = await _setup(db_session)
    streaming = await create_category(db_session, budget, group, "Streaming")
    software = await create_category(db_session, budget, group, "Software")
    vendor = await create_payee(db_session, budget, "Cascade Point Digital")
    pattern = "AABBABBAAB"
    for i, c in enumerate(pattern):
        amount, cat = ("-15.99", streaming) if c == "A" else ("-42.50", software)
        await create_transaction(
            db_session,
            budget,
            checking,
            amount,
            date(2026, 1, 1) + timedelta(days=7 * i),
            category=cat,
            payee=vendor,
        )
    await db_session.flush()

    a = await _auto(services, budget, checking, vendor, "-15.99", date(2026, 6, 1))
    b = await _auto(services, budget, checking, vendor, "-42.50", date(2026, 6, 2))
    assert a.category_id == streaming.id
    assert b.category_id == software.id


async def test_untrusted_payee_falls_back_to_amount_then_dominant_envelope(db_session):
    """No rule is trusted for this club, but Groceries holds half its rows
    and the membership amount has been seen before. The payee's default is
    not consulted: it has history."""
    services, budget, checking, group = await _setup(db_session)
    groceries = await create_category(db_session, budget, group, "Groceries")
    membership = await create_category(db_session, budget, group, "Club Membership")
    household = await create_category(db_session, budget, group, "Household")
    club = await create_payee(
        db_session, budget, "Northwind Warehouse Club", default_category_id=household.id
    )
    spec = [
        ("-140.00", groceries), ("-38.00", household), ("-155.00", groceries),
        ("-150.00", household), ("-42.00", groceries), ("-60.00", membership),
        ("-48.00", groceries), ("-145.00", household), ("-52.00", groceries),
        ("-170.00", household),
    ]  # fmt: skip
    for i, (amount, cat) in enumerate(spec):
        await create_transaction(
            db_session,
            budget,
            checking,
            amount,
            date(2026, 1, 1) + timedelta(days=9 * i),
            category=cat,
            payee=club,
        )
    await db_session.flush()

    grocery = await _auto(services, budget, checking, club, "-152.00", date(2026, 6, 1))
    assert grocery.category_id == groceries.id

    renewal = await _auto(services, budget, checking, club, "-60.00", date(2026, 6, 2))
    assert renewal.category_id == membership.id
