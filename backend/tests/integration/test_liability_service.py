"""Liability service: balance resolution and payment-history derivation.

Three derivation paths (managed account / linked category / snapshot
interpolation) each produce the trailing-month payment list that drives the
live payoff projection — every path plus its floor-at-zero rule is pinned
here against hand-seeded ledgers.
"""

from datetime import date
from decimal import Decimal

from igab.repositories.liability_repo import LiabilityRepository
from igab.services.liability_service import LiabilityService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_liability,
    create_liability_snapshot,
    create_payee,
    create_transaction,
    create_transfer,
    create_user,
    make_services,
)

AS_OF = date(2026, 7, 25)


def make_liability_service(db_session, services) -> LiabilityService:
    return LiabilityService(
        LiabilityRepository(db_session),
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
        liability = await create_liability(db_session, budget, linked_account_id=loan.id)
        svc = make_liability_service(db_session, services)

        assert await svc.get_balance(liability) == Decimal("9480.00")
        assert svc.mode(liability) == "managed"

    async def test_managed_balance_floors_at_zero_when_overpaid(self, db_session):
        services, budget = await _base(db_session)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "50.00", date(2026, 1, 1))
        liability = await create_liability(db_session, budget, linked_account_id=loan.id)
        svc = make_liability_service(db_session, services)

        assert await svc.get_balance(liability) == Decimal("0")

    async def test_unmanaged_balance_is_manual(self, db_session):
        services, budget = await _base(db_session)
        liability = await create_liability(db_session, budget, manual_balance=Decimal("4200.00"))
        svc = make_liability_service(db_session, services)

        assert await svc.get_balance(liability) == Decimal("4200.00")
        assert svc.mode(liability) == "unmanaged"

    async def test_unmanaged_without_balance_is_zero(self, db_session):
        services, budget = await _base(db_session)
        liability = await create_liability(db_session, budget)
        svc = make_liability_service(db_session, services)

        assert await svc.get_balance(liability) == Decimal("0")


class TestManagedPaymentHistory:
    async def test_transfers_into_the_account_are_the_payments(self, db_session):
        services, budget = await _base(db_session)
        checking = await create_account(db_session, budget, "Checking")
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-10000.00", date(2026, 1, 5))
        # Payments in May and June; nothing in the other window months
        await create_transfer(db_session, budget, checking, loan, "275.00", date(2026, 5, 10))
        await create_transfer(db_session, budget, checking, loan, "275.00", date(2026, 6, 10))
        # July (current month) payment must NOT count — incomplete month
        await create_transfer(db_session, budget, checking, loan, "275.00", date(2026, 7, 10))
        liability = await create_liability(db_session, budget, linked_account_id=loan.id)
        svc = make_liability_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(liability, as_of=AS_OF)

        # Window: Jan..Jun. January's origination is not a payment of any sign.
        assert payments == [
            Decimal("0"),  # Jan: the origination row is not a negative payment
            Decimal("0"),  # Feb
            Decimal("0"),  # Mar
            Decimal("0"),  # Apr
            Decimal("275.00"),  # May
            Decimal("275.00"),  # Jun
        ]

    async def test_live_projection_uses_actual_velocity(self, db_session):
        services, budget = await _base(db_session)
        checking = await create_account(db_session, budget, "Checking")
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-1000.00", date(2025, 12, 1))
        await create_transfer(db_session, budget, checking, loan, "300.00", date(2026, 5, 10))
        await create_transfer(db_session, budget, checking, loan, "500.00", date(2026, 6, 10))
        liability = await create_liability(
            db_session,
            budget,
            linked_account_id=loan.id,
            interest_rate=Decimal("12.0000"),
            minimum_payment=Decimal("50.00"),
        )
        svc = make_liability_service(db_session, services)

        status = await svc.get_status(liability, as_of=AS_OF)

        # Balance owed: 1000 - 800 paid = 200; avg payment (300+500)/2 = 400
        assert status.current_balance == Decimal("200.00")
        assert status.live is not None
        assert status.live.average_payment == Decimal("400.00")
        # 200 owed at 400/mo pays off in one payment
        assert status.live.payoff_date == date(2026, 8, 25)
        assert not status.baseline.never_pays_off  # 50/mo also retires 200


class TestInterestRowsAreNotNegativePayments:
    """The regression the user reported from a YNAB mortgage: a $3,000
    payment beside a −$1,618 interest row read as a $1,382 payment, which the
    schedule — accruing the same interest again from the rate — called
    "never pays off". The payment is the transfer in; the interest row is
    what the ledger says interest was; the balance still moves by the net."""

    async def _mortgage(self, db_session):
        services, budget = await _base(db_session)
        checking = await create_account(db_session, budget, "Checking")
        loan = await create_account(
            db_session, budget, "Mortgage", account_type="mortgage", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-620000.00", date(2026, 3, 1))
        for month in (4, 5, 6):
            await create_transfer(
                db_session, budget, checking, loan, "3000.00", date(2026, month, 1)
            )
            await create_transaction(
                db_session, budget, loan, "-1618.00", date(2026, month, 2), memo="Interest"
            )
        liability = await create_liability(
            db_session,
            budget,
            "Mortgage",
            liability_type=None,
            linked_account_id=loan.id,
            interest_rate=Decimal("3.125"),
            minimum_payment=Decimal("3000.00"),
        )
        return services, budget, checking, loan, liability

    async def test_the_payment_is_the_transfer_not_the_net_movement(self, db_session):
        services, _, _, _, liability = await self._mortgage(db_session)
        svc = make_liability_service(db_session, services)
        payments = await svc.get_recent_monthly_payments(liability, as_of=AS_OF)
        assert payments[-3:] == [Decimal("3000.00")] * 3

        status = await svc.get_status(liability, as_of=AS_OF)
        assert status.average_payment == Decimal("3000.00")
        assert status.live is not None
        assert status.live.never_pays_off is False
        # The ledger's own interest is reported beside the payment.
        assert status.recent_interest[-3:] == [Decimal("1618.00")] * 3
        assert status.average_interest == Decimal("1618.00")

    async def test_the_balance_and_its_history_still_move_by_the_net(self, db_session):
        services, _, _, _, liability = await self._mortgage(db_session)
        svc = make_liability_service(db_session, services)
        # 620000 − 3 × (3000 − 1618)
        assert await svc.get_balance(liability) == Decimal("615854.00")
        history = dict(await svc.get_balance_history(liability, as_of=AS_OF))
        assert history[date(2026, 4, 1)] == Decimal("618618.00")

    async def test_a_balance_adjustment_is_neither_payment_nor_interest(self, db_session):
        """YNAB writes a positive adjustment onto a loan when its interest
        estimate ran high. Not a payment — and said so."""
        services, budget, _, loan, liability = await self._mortgage(db_session)
        await create_transaction(
            db_session, budget, loan, "1384.71", date(2026, 6, 10), memo="Balance adjustment"
        )
        svc = make_liability_service(db_session, services)
        status = await svc.get_status(liability, as_of=AS_OF)
        assert status.average_payment == Decimal("3000.00")
        assert status.recent_interest[-1] == Decimal("1618.00")
        assert status.uncounted_deposits == Decimal("1384.71")

    async def test_an_unpaired_transfer_leg_still_counts(self, db_session):
        """A YNAB leg whose partner never imported is a transfer by its payee
        (TRANSFER_LEG), and so a payment."""
        services, budget = await _base(db_session)
        checking = await create_account(db_session, budget, "Checking")
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        from_checking = await create_payee(
            db_session, budget, "Transfer : Checking", transfer_account_id=checking.id
        )
        await create_transaction(db_session, budget, loan, "-5000.00", date(2026, 1, 5))
        await create_transaction(
            db_session, budget, loan, "400.00", date(2026, 5, 10), payee=from_checking
        )
        await create_transaction(
            db_session, budget, loan, "400.00", date(2026, 6, 10), payee=from_checking
        )
        liability = await create_liability(db_session, budget, linked_account_id=loan.id)
        svc = make_liability_service(db_session, services)
        payments = await svc.get_recent_monthly_payments(liability, as_of=AS_OF)
        assert payments[-2:] == [Decimal("400.00"), Decimal("400.00")]

    async def test_a_plain_deposit_is_not_a_payment_but_is_reported(self, db_session):
        services, budget = await _base(db_session)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-5000.00", date(2026, 1, 5))
        await create_transaction(db_session, budget, loan, "400.00", date(2026, 5, 10))
        await create_transaction(db_session, budget, loan, "400.00", date(2026, 6, 10))
        liability = await create_liability(db_session, budget, linked_account_id=loan.id)
        svc = make_liability_service(db_session, services)
        status = await svc.get_status(liability, as_of=AS_OF)
        assert status.recent_payments == [Decimal("0")] * 6
        assert status.average_payment is None
        assert status.uncounted_deposits == Decimal("800.00")


class TestLinkedCategoryPaymentHistory:
    async def test_category_outflows_become_payments(self, db_session):
        services, budget = await _base(db_session)
        checking = await create_account(db_session, budget, "Checking")
        everyday = await create_category_group(db_session, budget, "Liabilities")
        payment_cat = await create_category(db_session, budget, everyday, "Family Loan")
        liability = await create_liability(db_session, budget, manual_balance=Decimal("3000.00"))
        payment_cat.linked_liability_id = liability.id
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
        svc = make_liability_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(liability, as_of=AS_OF)

        assert payments[-2:] == [Decimal("200.00"), Decimal("200.00")]
        assert all(p == Decimal("0") for p in payments[:-2])

    async def test_category_takes_precedence_over_snapshots(self, db_session):
        services, budget = await _base(db_session)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Liabilities")
        payment_cat = await create_category(db_session, budget, group, "Loan Payment")
        liability = await create_liability(db_session, budget, manual_balance=Decimal("3000.00"))
        payment_cat.linked_liability_id = liability.id
        await db_session.flush()
        # Snapshots that would imply a different (larger) payment history
        await create_liability_snapshot(db_session, liability, date(2026, 4, 1), Decimal("5000.00"))
        await create_liability_snapshot(db_session, liability, date(2026, 6, 1), Decimal("3000.00"))
        await create_transaction(
            db_session, budget, checking, "-150.00", date(2026, 6, 15), category=payment_cat
        )
        svc = make_liability_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(liability, as_of=AS_OF)

        assert payments[-1] == Decimal("150.00")
        assert sum(payments) == Decimal("150.00"), "snapshot deltas must not leak in"


class TestSnapshotPaymentHistory:
    async def test_drop_spread_evenly_across_span(self, db_session):
        services, budget = await _base(db_session)
        liability = await create_liability(db_session, budget, manual_balance=Decimal("4400.00"))
        # 600 drop over 3 months (Mar → Jun) = 200/month for Apr, May, Jun
        await create_liability_snapshot(
            db_session, liability, date(2026, 3, 10), Decimal("5000.00")
        )
        await create_liability_snapshot(
            db_session, liability, date(2026, 6, 10), Decimal("4400.00")
        )
        svc = make_liability_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(liability, as_of=AS_OF)

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
        liability = await create_liability(db_session, budget, manual_balance=Decimal("5500.00"))
        await create_liability_snapshot(db_session, liability, date(2026, 5, 1), Decimal("5000.00"))
        await create_liability_snapshot(db_session, liability, date(2026, 6, 1), Decimal("5500.00"))
        svc = make_liability_service(db_session, services)

        payments = await svc.get_recent_monthly_payments(liability, as_of=AS_OF)

        assert all(p == Decimal("0") for p in payments)

    async def test_no_history_no_live_projection(self, db_session):
        services, budget = await _base(db_session)
        liability = await create_liability(db_session, budget, manual_balance=Decimal("5000.00"))
        svc = make_liability_service(db_session, services)

        status = await svc.get_status(liability, as_of=AS_OF)

        assert status.recent_payments == [Decimal("0")] * 6
        assert status.live is None, "no fabricated dates from insufficient data"
        assert not status.baseline.never_pays_off

    async def test_single_snapshot_no_live_projection(self, db_session):
        services, budget = await _base(db_session)
        liability = await create_liability(db_session, budget, manual_balance=Decimal("5000.00"))
        await create_liability_snapshot(db_session, liability, date(2026, 6, 1), Decimal("5000.00"))
        svc = make_liability_service(db_session, services)

        status = await svc.get_status(liability, as_of=AS_OF)
        assert status.live is None


class TestUnmanagedTotal:
    async def test_sums_only_unmanaged_liabilities(self, db_session):
        services, budget = await _base(db_session)
        loan = await create_account(
            db_session, budget, "Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-7000.00", date(2026, 1, 1))
        await create_liability(db_session, budget, "Managed", linked_account_id=loan.id)
        await create_liability(db_session, budget, "Family", manual_balance=Decimal("1200.00"))
        await create_liability(db_session, budget, "Medical", manual_balance=Decimal("800.50"))
        svc = make_liability_service(db_session, services)

        assert await svc.unmanaged_total(budget.id) == Decimal("2000.50")


class TestSnapshotUpsert:
    async def test_same_day_snapshot_replaces(self, db_session):
        services, budget = await _base(db_session)
        liability = await create_liability(db_session, budget, manual_balance=Decimal("5000.00"))
        repo = LiabilityRepository(db_session)

        await repo.upsert_snapshot(liability.id, date(2026, 7, 1), Decimal("4900.00"))
        await repo.upsert_snapshot(liability.id, date(2026, 7, 1), Decimal("4850.00"))

        snapshots = await repo.get_snapshots(liability.id)
        assert len(snapshots) == 1
        assert snapshots[0].balance == Decimal("4850.00")
