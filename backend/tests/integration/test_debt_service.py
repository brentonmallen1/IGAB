"""Debt service: balance resolution and payment-history derivation.

Three derivation paths (managed account / linked category / snapshot
interpolation) each produce the trailing-month payment list that drives the
live payoff projection — every path plus its floor-at-zero rule is pinned
here against hand-seeded ledgers.
"""

from datetime import date
from decimal import Decimal

from igab.repositories.debt_repo import DebtRepository
from igab.services.debt_service import DebtService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_debt,
    create_debt_snapshot,
    create_transaction,
    create_user,
    make_services,
)

AS_OF = date(2026, 7, 25)


def make_debt_service(db_session, services) -> DebtService:
    return DebtService(
        DebtRepository(db_session),
        services.account_repo,
        services.category_repo,
        services.transaction_repo,
    )


async def _base(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    return services, budget


class TestBalanceResolution:
    async def test_managed_balance_is_negated_account_balance(self, db_session):
        services, budget = await _base(db_session)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-9480.00", date(2026, 1, 1))
        debt = await create_debt(db_session, budget, linked_account_id=loan.id)
        svc = make_debt_service(db_session, services)

        assert await svc.get_balance(debt) == Decimal("9480.00")
        assert svc.mode(debt) == "managed"

    async def test_managed_balance_floors_at_zero_when_overpaid(self, db_session):
        services, budget = await _base(db_session)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "50.00", date(2026, 1, 1))
        debt = await create_debt(db_session, budget, linked_account_id=loan.id)
        svc = make_debt_service(db_session, services)

        assert await svc.get_balance(debt) == Decimal("0")

    async def test_unmanaged_balance_is_manual(self, db_session):
        services, budget = await _base(db_session)
        debt = await create_debt(db_session, budget, manual_balance=Decimal("4200.00"))
        svc = make_debt_service(db_session, services)

        assert await svc.get_balance(debt) == Decimal("4200.00")
        assert svc.mode(debt) == "unmanaged"

    async def test_unmanaged_without_balance_is_zero(self, db_session):
        services, budget = await _base(db_session)
        debt = await create_debt(db_session, budget)
        svc = make_debt_service(db_session, services)

        assert await svc.get_balance(debt) == Decimal("0")


class TestManagedPaymentHistory:
    async def test_monthly_account_movement_is_the_paydown(self, db_session):
        services, budget = await _base(db_session)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-10000.00", date(2026, 1, 5))
        # Payments in May and June; nothing in the other window months
        await create_transaction(db_session, budget, loan, "275.00", date(2026, 5, 10))
        await create_transaction(db_session, budget, loan, "275.00", date(2026, 6, 10))
        # July (current month) payment must NOT count — incomplete month
        await create_transaction(db_session, budget, loan, "275.00", date(2026, 7, 10))
        debt = await create_debt(db_session, budget, linked_account_id=loan.id)
        svc = make_debt_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(debt, as_of=AS_OF)

        # Window: Jan..Jun. January nets -10000 (origination) → floored to 0.
        assert payments == [
            Decimal("0"),  # Jan: balance increase is not a negative payment
            Decimal("0"),  # Feb
            Decimal("0"),  # Mar
            Decimal("0"),  # Apr
            Decimal("275.00"),  # May
            Decimal("275.00"),  # Jun
        ]

    async def test_live_projection_uses_actual_velocity(self, db_session):
        services, budget = await _base(db_session)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-1000.00", date(2025, 12, 1))
        await create_transaction(db_session, budget, loan, "300.00", date(2026, 5, 10))
        await create_transaction(db_session, budget, loan, "500.00", date(2026, 6, 10))
        debt = await create_debt(
            db_session,
            budget,
            linked_account_id=loan.id,
            interest_rate=Decimal("12.0000"),
            minimum_payment=Decimal("50.00"),
        )
        svc = make_debt_service(db_session, services)

        status = await svc.get_status(debt, as_of=AS_OF)

        # Balance owed: 1000 - 800 paid = 200; avg payment (300+500)/2 = 400
        assert status.current_balance == Decimal("200.00")
        assert status.live is not None
        assert status.live.average_payment == Decimal("400.00")
        # 200 owed at 400/mo pays off in one payment
        assert status.live.payoff_date == date(2026, 8, 25)
        assert not status.baseline.never_pays_off  # 50/mo also retires 200


class TestLinkedCategoryPaymentHistory:
    async def test_category_outflows_become_payments(self, db_session):
        services, budget = await _base(db_session)
        checking = await create_account(db_session, budget, "Checking")
        everyday = await create_category_group(db_session, budget, "Debt")
        payment_cat = await create_category(db_session, budget, everyday, "Family Loan")
        debt = await create_debt(db_session, budget, manual_balance=Decimal("3000.00"))
        payment_cat.linked_debt_id = debt.id
        await db_session.flush()

        await create_transaction(
            db_session, budget, checking, "-200.00", date(2026, 5, 15), category=payment_cat
        )
        await create_transaction(
            db_session, budget, checking, "-200.00", date(2026, 6, 15), category=payment_cat
        )
        # An inflow (refund) into the category must not offset payments
        await create_transaction(
            db_session, budget, checking, "75.00", date(2026, 6, 20), category=payment_cat
        )
        svc = make_debt_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(debt, as_of=AS_OF)

        assert payments[-2:] == [Decimal("200.00"), Decimal("200.00")]
        assert all(p == Decimal("0") for p in payments[:-2])

    async def test_category_takes_precedence_over_snapshots(self, db_session):
        services, budget = await _base(db_session)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Debt")
        payment_cat = await create_category(db_session, budget, group, "Loan Payment")
        debt = await create_debt(db_session, budget, manual_balance=Decimal("3000.00"))
        payment_cat.linked_debt_id = debt.id
        await db_session.flush()
        # Snapshots that would imply a different (larger) payment history
        await create_debt_snapshot(db_session, debt, date(2026, 4, 1), Decimal("5000.00"))
        await create_debt_snapshot(db_session, debt, date(2026, 6, 1), Decimal("3000.00"))
        await create_transaction(
            db_session, budget, checking, "-150.00", date(2026, 6, 15), category=payment_cat
        )
        svc = make_debt_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(debt, as_of=AS_OF)

        assert payments[-1] == Decimal("150.00")
        assert sum(payments) == Decimal("150.00"), "snapshot deltas must not leak in"


class TestSnapshotPaymentHistory:
    async def test_drop_spread_evenly_across_span(self, db_session):
        services, budget = await _base(db_session)
        debt = await create_debt(db_session, budget, manual_balance=Decimal("4400.00"))
        # 600 drop over 3 months (Mar → Jun) = 200/month for Apr, May, Jun
        await create_debt_snapshot(db_session, debt, date(2026, 3, 10), Decimal("5000.00"))
        await create_debt_snapshot(db_session, debt, date(2026, 6, 10), Decimal("4400.00"))
        svc = make_debt_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(debt, as_of=AS_OF)

        # Window Jan..Jun
        assert payments == [
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("200.00"),
            Decimal("200.00"),
            Decimal("200.00"),
        ]

    async def test_balance_increase_contributes_nothing(self, db_session):
        services, budget = await _base(db_session)
        debt = await create_debt(db_session, budget, manual_balance=Decimal("5500.00"))
        await create_debt_snapshot(db_session, debt, date(2026, 5, 1), Decimal("5000.00"))
        await create_debt_snapshot(db_session, debt, date(2026, 6, 1), Decimal("5500.00"))
        svc = make_debt_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(debt, as_of=AS_OF)

        assert all(p == Decimal("0") for p in payments)

    async def test_no_history_no_live_projection(self, db_session):
        services, budget = await _base(db_session)
        debt = await create_debt(db_session, budget, manual_balance=Decimal("5000.00"))
        svc = make_debt_service(db_session, services)

        status = await svc.get_status(debt, as_of=AS_OF)

        assert status.recent_payments == [Decimal("0")] * 6
        assert status.live is None, "no fabricated dates from insufficient data"
        assert not status.baseline.never_pays_off

    async def test_single_snapshot_no_live_projection(self, db_session):
        services, budget = await _base(db_session)
        debt = await create_debt(db_session, budget, manual_balance=Decimal("5000.00"))
        await create_debt_snapshot(db_session, debt, date(2026, 6, 1), Decimal("5000.00"))
        svc = make_debt_service(db_session, services)

        status = await svc.get_status(debt, as_of=AS_OF)
        assert status.live is None


class TestUnmanagedTotal:
    async def test_sums_only_unmanaged_debts(self, db_session):
        services, budget = await _base(db_session)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-7000.00", date(2026, 1, 1))
        await create_debt(db_session, budget, "Managed", linked_account_id=loan.id)
        await create_debt(db_session, budget, "Family", manual_balance=Decimal("1200.00"))
        await create_debt(db_session, budget, "Medical", manual_balance=Decimal("800.50"))
        svc = make_debt_service(db_session, services)

        assert await svc.unmanaged_total(budget.id) == Decimal("2000.50")


class TestSnapshotUpsert:
    async def test_same_day_snapshot_replaces(self, db_session):
        services, budget = await _base(db_session)
        debt = await create_debt(db_session, budget, manual_balance=Decimal("5000.00"))
        repo = DebtRepository(db_session)

        await repo.upsert_snapshot(debt.id, date(2026, 7, 1), Decimal("4900.00"))
        await repo.upsert_snapshot(debt.id, date(2026, 7, 1), Decimal("4850.00"))

        snapshots = await repo.get_snapshots(debt.id)
        assert len(snapshots) == 1
        assert snapshots[0].balance == Decimal("4850.00")
