"""Every row says where it came from — Transaction.created_via — and the
change log's `source` follows from it (one mapping, change_log.source_for).

Before this only the AI paths stamped anything: a sync-created row and a
hand-typed one were indistinguishable once the bank matched the latter, and
the sync's rows were logged as manual entries.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import ChangeLog
from igab.services.change_log import source_for
from igab.services.transaction_service import SplitSpec, TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date(2026, 7, 10)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    return services, budget, checking


async def _create_source(db_session, txn_id):
    await db_session.flush()
    row = (
        (
            await db_session.execute(
                select(ChangeLog).where(ChangeLog.entity_id == txn_id, ChangeLog.action == "create")
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    return row.source


def test_source_follows_origin():
    assert source_for("manual") == "manual"
    assert source_for("import") == "import"
    assert source_for("sync") == "system"
    assert source_for("scheduled") == "system"
    assert source_for("ai_receipt") == "ai" and source_for("ai_nl") == "ai"
    assert source_for(None) == "manual", "unknown origin reads as the user's"


async def test_manual_create_is_stamped_manual_and_logs_manual(db_session):
    services, budget, checking = await _setup(db_session)
    txn = await services.transactions.create(
        budget.id, TransactionCreate(account_id=checking.id, date=TODAY, amount=Decimal("-5"))
    )
    assert txn.created_via == "manual"
    assert await _create_source(db_session, txn.id) == "manual"


async def test_sync_created_row_is_stamped_sync_and_logs_system(db_session):
    services, budget, checking = await _setup(db_session)
    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("-5"),
            sync_id="t-1",
            sync_source="simplefin",
            cleared="cleared",
            approved=False,
        ),
    )
    assert txn.created_via == "sync" and txn.has_sync_source is True
    assert await _create_source(db_session, txn.id) == "system"


async def test_file_import_rows_are_stamped_import(db_session):
    services, budget, checking = await _setup(db_session)
    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id, date=TODAY, amount=Decimal("-5"), import_id="csv:1"
        ),
    )
    assert txn.created_via == "import"
    assert await _create_source(db_session, txn.id) == "import"


async def test_ai_rows_keep_their_stamp_and_log_ai(db_session):
    services, budget, checking = await _setup(db_session)
    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id, date=TODAY, amount=Decimal("-5"), created_via="ai_receipt"
        ),
    )
    assert txn.created_via == "ai_receipt"
    assert await _create_source(db_session, txn.id) == "ai"


async def test_transfer_far_leg_and_split_lines_inherit_provenance(db_session):
    services, budget, checking = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")
    leg = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("-50"),
            transfer_account_id=savings.id,
            created_via="ai_nl",
        ),
    )
    partner = await services.transaction_repo.get(leg.transfer_id)
    assert leg.created_via == "ai_nl" and partner.created_via == "ai_nl"

    receipt = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id, date=TODAY, amount=Decimal("-30"), created_via="ai_receipt"
        ),
    )
    await services.transactions.convert_to_split(
        budget.id, receipt.id, [SplitSpec(amount=Decimal("-10")), SplitSpec(amount=Decimal("-20"))]
    )
    lines = await services.transaction_repo.get_splits(receipt.id)
    assert {c.created_via for c in lines} == {"ai_receipt"}, (
        "lines are not 'manual' under an AI parent"
    )


async def test_legacy_null_created_via_still_serializes(api_client, db_session):
    from igab.api.v1.schemas.transaction import TransactionResponse

    user = api_client.test_user
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    legacy = await create_transaction(db_session, budget, checking, "-1.00", TODAY)
    legacy.created_via = None
    await db_session.flush()
    services = make_services(db_session)
    row = await services.transaction_repo.get_or_raise(legacy.id)
    assert TransactionResponse.model_validate(row).created_via is None


async def test_matched_manual_row_keeps_its_origin(db_session):
    """The bank matching a hand-typed row adds a bank source; it does not
    make the row the bank's."""
    services, budget, checking = await _setup(db_session)
    manual = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id, date=TODAY, amount=Decimal("-50"), cleared="uncleared"
        ),
    )
    bank = await create_transaction(
        db_session,
        budget,
        checking,
        "-50.00",
        TODAY,
        sync_id="t-9",
        sync_source="simplefin",
        bank_posted_date=TODAY,
        bank_amount="-50.00",
        created_via="sync",
    )
    survivor = await services.transactions.merge(budget.id, [manual.id, bank.id])
    assert survivor.id == manual.id
    assert survivor.created_via == "manual" and survivor.has_sync_source is True
