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
        "card_payment_envelope_pairing",
        "card_reserve_identity",
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


class TestTheCardReserveIdentity:
    """`set_aside + uncovered == -balance`, with its three bounds and no
    exclusion clause.

    The old form excused "a card with no assignments and no inflows that
    predate their reservations" — precisely the histories that broke it, so
    nothing ever asked. These are the cases the clause used to cover.
    """

    async def _card_budget(self, db_session):
        from igab.services.card_payment import ensure_payment_category

        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking")
        visa = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card"
        )
        linked = await ensure_payment_category(db_session, visa)
        group = await create_category_group(db_session, budget, "Everyday")
        cat = await create_category(db_session, budget, group, "Groceries")
        return budget, checking, visa, linked, cat

    async def _check(self, db_session, budget):
        report = await IntegrityService(db_session).run(budget.id)
        return next(c for c in report.checks if c.name == "card_reserve_identity")

    async def test_a_healthy_budget_passes(self, db_session):
        budget, _checking, visa, _linked, cat = await self._card_budget(db_session)
        services = make_services(db_session)
        await services.budgets.set_assignment(
            budget.id, cat.id, TODAY.replace(day=1), Decimal("100.00")
        )
        await create_transaction(db_session, budget, visa, "-60.00", TODAY, category=cat)
        assert (await self._check(db_session, budget)).passed is True

    async def test_a_repayment_of_ridden_debt_passes(self, db_session):
        """The Refused Repayment, end to end. Nothing assigned, so the charge
        rides; the repayment next month discharges it. Under the old rule the
        release was refused, the reserve outlived the debt, and the envelope
        carried a red the identity would have named."""
        budget, _checking, visa, _linked, cat = await self._card_budget(db_session)
        first = TODAY.replace(day=1)
        await create_transaction(
            db_session, budget, visa, "-100.00", first - timedelta(days=1), category=cat
        )
        await create_transaction(db_session, budget, visa, "100.00", first, category=cat)
        assert (await self._check(db_session, budget)).passed is True

    async def test_a_reserve_raised_by_assignment_passes(self, db_session):
        """T1. Money deliberately assigned to the card puts its reserve ahead
        of its debt — allowed, and the clause this replaces used to exclude
        every such card from the check entirely."""
        budget, _checking, visa, linked, cat = await self._card_budget(db_session)
        first = TODAY.replace(day=1)
        await create_transaction(db_session, budget, visa, "-40.00", TODAY, category=cat)
        await make_services(db_session).budgets.set_assignment(
            budget.id, linked.id, first, Decimal("250.00")
        )
        assert (await self._check(db_session, budget)).passed is True

    async def test_a_credit_balance_a_third_party_paid_passes(self, db_session):
        """T3. An uncategorized, non-transfer inflow on the card: someone else
        paid it. It touches no envelope, and the credit balance it leaves is
        theirs — not a drifted reserve."""
        budget, _checking, visa, _linked, cat = await self._card_budget(db_session)
        await create_transaction(db_session, budget, visa, "-40.00", TODAY, category=cat)
        await create_transaction(db_session, budget, visa, "400.00", TODAY)
        assert (await self._check(db_session, budget)).passed is True

    async def test_a_card_credit_filed_as_income_passes(self, db_session):
        """The Watchman's Arithmetic, finding two. A rewards credit on the card
        filed to Ready to Assign rather than left uncategorized: still nobody's
        envelope money, still an outside credit. The complement was spelled
        `category_id IS NULL`, so this row reached no term and the check
        reported its amount as drift forever."""
        budget, _checking, visa, _linked, cat = await self._card_budget(db_session)
        income_group = await create_category_group(db_session, budget, "Income", is_system=True)
        income = await create_category(db_session, budget, income_group, "Inflow")
        await make_services(db_session).budgets.set_assignment(
            budget.id, cat.id, TODAY.replace(day=1), Decimal("100.00")
        )
        await create_transaction(db_session, budget, visa, "-100.00", TODAY, category=cat)
        await create_transaction(db_session, budget, visa, "25.00", TODAY, category=income)
        assert (await self._check(db_session, budget)).passed is True

    async def test_a_reserve_moved_back_out_passes(self, db_session):
        """The Watchman's Arithmetic, finding one. Moving money back out of a
        card's payment envelope drives its lifetime assignment total negative;
        unfloored, T1's `L - R` reported that shortfall as unexplained drift on
        a card with nothing over-reserved. The loudest number on this page was
        the one that was not real."""
        budget, _checking, visa, linked, cat = await self._card_budget(db_session)
        first = TODAY.replace(day=1)
        services = make_services(db_session)
        await services.budgets.set_assignment(budget.id, cat.id, first, Decimal("100.00"))
        await create_transaction(db_session, budget, visa, "-100.00", TODAY, category=cat)
        await services.budgets.set_assignment(budget.id, linked.id, first, Decimal("-100.00"))
        assert (await self._check(db_session, budget)).passed is True

    async def test_a_reserve_that_outlived_its_debt_is_named(self, db_session):
        """The failure direction, seeded directly: a set-aside with nothing
        behind it. Without a case that fails, the check above proves nothing.
        """
        from igab.domain.cards import reserve_discrepancy

        zero = Decimal("0")
        # 100 reserved against a card owing nothing, no assignment, no payment,
        # no residual, no outside credit — the shape the old code produced on
        # every refund that posted before its purchase.
        assert reserve_discrepancy(
            Decimal("100"), zero, zero, zero, zero, zero
        ) == Decimal("100")
