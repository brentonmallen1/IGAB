"""Phase 9 spec: the live integrity endpoint detects seeded inconsistencies
and reports all-green on clean data."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import update

from igab.db.models import Transaction
from igab.services.integrity_service import IntegrityService
from igab.services.transaction_service import TransactionCreate

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


async def test_clean_budget_reports_all_green(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    services = make_services(db_session)
    await create_transaction(db_session, budget, account, "100.00", TODAY)
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=account.id,
            date=TODAY,
            amount=Decimal("-25.00"),
            payee_name="Store",
            cleared="cleared",
        ),
    )

    resp = await api_client.get(f"/api/v1/budgets/{budget.id}/integrity")
    assert resp.status_code == 200
    report = resp.json()
    assert report["all_passed"] is True, report
    assert {c["name"] for c in report["checks"]} == {
        "split_integrity",
        "transfer_integrity",
        "money_conservation",
        "orphaned_matches",
        "orphaned_categories",
        "stale_pendings",
        "card_envelope_rows",
    }


async def test_seeded_inconsistencies_are_each_detected(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "G")
    cat = await create_category(db_session, budget, group, "C")

    # 1. Split whose lines no longer sum to the parent (forced via raw update)
    header = TransactionCreate(
        account_id=account.id, date=TODAY, amount=Decimal("-100.00"), cleared="cleared"
    )
    splits = [
        TransactionCreate(
            account_id=account.id, date=TODAY, amount=Decimal("-100.00"), category_id=cat.id
        )
    ]
    parent = await services.transactions.create_split(budget.id, header, splits)
    child = (await services.transaction_repo.get_splits(parent.id))[0]
    await db_session.execute(
        update(Transaction).where(Transaction.id == child.id).values(amount=Decimal("-60.00"))
    )

    # 2. One-legged transfer (partner soft-deleted behind the service's back)
    source = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=account.id,
            date=TODAY,
            amount=Decimal("50.00"),
            transfer_account_id=(await create_account(db_session, budget, "Savings")).id,
            cleared="cleared",
        ),
    )
    await db_session.execute(
        update(Transaction).where(Transaction.id == source.transfer_id).values(is_deleted=True)
    )

    # 3. Stale pending from a bank sync
    await create_transaction(
        db_session,
        budget,
        account,
        "-9.00",
        TODAY - timedelta(days=40),
        cleared="pending",
        sync_id="t-stale",
        sync_source="simplefin",
    )

    # 4. Pending match pointing at a deleted transaction
    dead = await create_transaction(
        db_session, budget, account, "-5.00", TODAY, is_deleted=True
    )
    live = await create_transaction(db_session, budget, account, "-5.00", TODAY)
    await services.match_repo.create(
        synced_transaction_id=dead.id, manual_transaction_id=live.id, confidence_score=0.6
    )

    report = await IntegrityService(db_session).run(budget.id)
    by_name = {c.name: c for c in report.checks}

    assert report.all_passed is False
    assert by_name["split_integrity"].passed is False
    assert by_name["transfer_integrity"].passed is False
    assert by_name["money_conservation"].passed is False, (
        "the broken split must surface as a conservation mismatch"
    )
    assert by_name["stale_pendings"].passed is False
    assert by_name["orphaned_matches"].passed is False


async def test_a_row_filed_to_a_card_envelope_is_detected(db_session):
    """Money filed into a card's set-aside envelope shows nowhere: the
    summary overwrites that envelope's balance from card arithmetic. The
    service refuses new ones, so this is seeded behind its back — which is
    exactly how the register's old dropdown produced them."""
    from igab.services.card_payment import ensure_payment_category

    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
    linked = await ensure_payment_category(db_session, visa)
    assert linked is not None
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")

    txn = await create_transaction(
        db_session, budget, checking, "-40.00", TODAY, category=cat
    )
    await db_session.execute(
        update(Transaction).where(Transaction.id == txn.id).values(category_id=linked.id)
    )
    await db_session.flush()

    report = await IntegrityService(db_session).run(budget.id)
    check = next(c for c in report.checks if c.name == "card_envelope_rows")
    assert check.passed is False
    assert check.problem_count == 1
    assert "Visa" in check.details[0]
    assert report.all_passed is False
