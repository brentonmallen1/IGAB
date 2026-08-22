"""YNAB import resolves "Transfer : X" into real transfer payees, and reports
legs it could not pair.

The register names the partner account in the payee column, so the mapping was
always available — it just was not used, and every imported transfer payee came
out as an ordinary payee that merely looked like one. `transfer_account_id` is
what keeps an orphaned leg out of income/expense (see
test_orphaned_transfer_legs.py) and what keeps transfer payees out of payee
pickers and AI suggestions.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Payee
from igab.integrations.ynab.importer import YNABImporter
from igab.integrations.ynab.models import YNABBudget, YNABTransaction
from igab.repositories.category_repo import CategoryGroupRepository

from .factories import create_budget, create_user, make_services
from .invariants import assert_financial_invariants

JAN5 = date(2026, 1, 5)
JAN6 = date(2026, 1, 6)


def _importer(services, db_session, budget, account_types=None, skip_accounts=None):
    return YNABImporter(
        session=db_session,
        budget_id=budget.id,
        account_repo=services.account_repo,
        category_group_repo=CategoryGroupRepository(db_session),
        category_repo=services.category_repo,
        payee_repo=services.payee_repo,
        transaction_repo=services.transaction_repo,
        transaction_service=services.transactions,
        assignment_repo=services.assignment_repo,
        account_types=account_types,
        skip_accounts=skip_accounts,
    )


def _txn(account, payee, amount, *, txn_date=JAN5, category=None, group=None):
    return YNABTransaction(
        account_name=account,
        date=txn_date,
        payee=payee,
        category_group=group,
        category=category,
        memo=None,
        amount=Decimal(amount),
        cleared="cleared",
    )


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    return services, budget


async def _payees(db_session, budget) -> dict[str, Payee]:
    rows = (
        await db_session.execute(select(Payee).where(Payee.budget_id == budget.id))
    ).scalars().all()
    return {p.name: p for p in rows}


class TestTransferPayeesAreLinked:
    async def test_paired_transfer_creates_linked_payees_both_ways(self, db_session):
        services, budget = await _setup(db_session)
        data = YNABBudget(
            transactions=[
                _txn("Checking", "Transfer : Savings", "-500.00"),
                _txn("Savings", "Transfer : Checking", "500.00"),
            ]
        )
        await _importer(services, db_session, budget).import_budget(data)

        accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
        payees = await _payees(db_session, budget)
        assert payees["Transfer : Savings"].transfer_account_id == accounts["Savings"].id
        assert payees["Transfer : Checking"].transfer_account_id == accounts["Checking"].id
        await assert_financial_invariants(db_session, budget.id)

    async def test_orphaned_leg_still_gets_a_linked_payee(self, db_session):
        """The partner leg is missing, so `transfer_id` stays NULL — the payee
        link is the only thing left that says this row is a transfer."""
        services, budget = await _setup(db_session)
        data = YNABBudget(
            transactions=[
                _txn("Checking", "Transfer : Brokerage", "-500.00",
                     group="Savings", category="Investments"),
                _txn("Brokerage", "Transfer : Checking", "500.00"),
            ]
        )
        await _importer(services, db_session, budget).import_budget(data)

        accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
        brokerage_txns = await services.transaction_repo.get_for_account(accounts["Brokerage"].id)
        leg = brokerage_txns[0]
        assert leg.transfer_id is None, "categorized counterpart never entered the pairing pool"

        payees = await _payees(db_session, budget)
        assert payees["Transfer : Checking"].transfer_account_id == accounts["Checking"].id

    async def test_plain_payees_are_not_linked(self, db_session):
        services, budget = await _setup(db_session)
        data = YNABBudget(transactions=[_txn("Checking", "Corner Market", "-60.00")])
        await _importer(services, db_session, budget).import_budget(data)

        payees = await _payees(db_session, budget)
        assert payees["Corner Market"].transfer_account_id is None

    async def test_payee_naming_a_skipped_account_stays_plain(self, db_session):
        """There is no account to point at. It stays an ordinary payee rather
        than being linked somewhere wrong — and is counted as unpaired."""
        services, budget = await _setup(db_session)
        data = YNABBudget(
            transactions=[
                _txn("Checking", "Transfer : Old Account", "-75.00"),
                _txn("Old Account", "Transfer : Checking", "75.00"),
            ]
        )
        result = await _importer(
            services, db_session, budget, skip_accounts={"Old Account"}
        ).import_budget(data)

        payees = await _payees(db_session, budget)
        assert payees["Transfer : Old Account"].transfer_account_id is None
        assert result.transfer_legs_unpaired == 1

    async def test_reimport_is_still_idempotent(self, db_session):
        services, budget = await _setup(db_session)
        data = YNABBudget(
            transactions=[
                _txn("Checking", "Transfer : Savings", "-500.00"),
                _txn("Savings", "Transfer : Checking", "500.00"),
            ]
        )
        await _importer(services, db_session, budget).import_budget(data)
        await _importer(services, db_session, budget).import_budget(data)

        payees = await _payees(db_session, budget)
        assert len([n for n in payees if n.startswith("Transfer : ")]) == 2
        await assert_financial_invariants(db_session, budget.id)


class TestUnpairedLegsAreReported:
    async def test_clean_pair_reports_zero(self, db_session):
        services, budget = await _setup(db_session)
        data = YNABBudget(
            transactions=[
                _txn("Checking", "Transfer : Savings", "-500.00"),
                _txn("Savings", "Transfer : Checking", "500.00"),
            ]
        )
        result = await _importer(services, db_session, budget).import_budget(data)
        assert result.transfer_legs_unpaired == 0

    async def test_missing_partner_is_counted(self, db_session):
        services, budget = await _setup(db_session)
        data = YNABBudget(
            transactions=[_txn("Checking", "Transfer : Nowhere", "-75.00")]
        )
        result = await _importer(services, db_session, budget).import_budget(data)
        assert result.transfer_legs_unpaired == 1

    async def test_amount_mismatch_leaves_both_legs_unpaired(self, db_session):
        """Pairing requires an exact opposite amount. A mismatch is silent
        breakage without this counter — it was 1,117 legs on a real export."""
        services, budget = await _setup(db_session)
        data = YNABBudget(
            transactions=[
                _txn("Checking", "Transfer : Savings", "-500.00"),
                _txn("Savings", "Transfer : Checking", "499.00"),
            ]
        )
        result = await _importer(services, db_session, budget).import_budget(data)
        assert result.transfer_legs_unpaired == 2

    async def test_date_skew_leaves_both_legs_unpaired(self, db_session):
        services, budget = await _setup(db_session)
        data = YNABBudget(
            transactions=[
                _txn("Checking", "Transfer : Savings", "-500.00", txn_date=JAN5),
                _txn("Savings", "Transfer : Checking", "500.00", txn_date=JAN6),
            ]
        )
        result = await _importer(services, db_session, budget).import_budget(data)
        assert result.transfer_legs_unpaired == 2

    async def test_categorized_spending_transfer_orphans_its_counterpart(self, db_session):
        """The structural orphan: the categorized leg never enters the pairing
        pool, so the tracked-side leg has nothing to match."""
        services, budget = await _setup(db_session)
        data = YNABBudget(
            transactions=[
                _txn("Checking", "Transfer : Brokerage", "-500.00",
                     group="Savings", category="Investments"),
                _txn("Brokerage", "Transfer : Checking", "500.00"),
            ]
        )
        result = await _importer(services, db_session, budget).import_budget(data)
        assert result.transfer_legs_unpaired == 1
