"""Post-import hygiene: things that are probably wrong, not provably.

The budget this exists for: a real 47-account YNAB import where four assets
had been given debt types, understating net worth by ~$2.8M and spawning four
phantom companion liabilities, and 1,117 transfer legs arrived unpaired.
Everything was internally consistent — `IntegrityService` had nothing to say,
correctly — and the budget was still wrong.

Each check is tested with and without its condition, because a panel that
cries wolf gets dismissed once and never read again.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.db.models import Liability
from igab.services.account_hygiene import AccountHygieneService

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

TODAY = date.today()
RECENT = TODAY - timedelta(days=10)
LONG_AGO = TODAY - timedelta(days=800)


async def _world(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    return services, budget


async def _run(db_session, budget) -> dict[str, object]:
    report = await AccountHygieneService(db_session).run(budget.id)
    return {f.kind: f for f in report.findings}


class TestATrackedThingInsideTheBudget:
    """Leads the panel because it is the only finding here that corrupts a
    number the user reads daily: to_be_assigned is total account balance minus
    category balances, so a house inside the budget inflates every envelope."""

    async def test_a_house_on_budget_is_reported(self, db_session):
        services, budget = await _world(db_session)
        await create_account(db_session, budget, "Ferry House", on_budget=True)
        await db_session.flush()

        findings = await _run(db_session, budget)
        assert "tracked_name_on_budget" in findings

    async def test_the_same_house_off_budget_is_not(self, db_session):
        services, budget = await _world(db_session)
        await create_account(
            db_session, budget, "Ferry House", account_type="other_asset", on_budget=False
        )
        await db_session.flush()

        assert "tracked_name_on_budget" not in await _run(db_session, budget)

    async def test_an_ordinary_checking_account_is_not(self, db_session):
        services, budget = await _world(db_session)
        await create_account(db_session, budget, "Redwood Checking", on_budget=True)
        await db_session.flush()

        assert "tracked_name_on_budget" not in await _run(db_session, budget)


class TestADebtHoldingAPositiveBalance:
    async def test_a_large_positive_balance_on_a_debt_type_is_reported(self, db_session):
        """The $2.8M case: an asset given a debt type is subtracted from net
        worth instead of added, so the error is twice the balance."""
        services, budget = await _world(db_session)
        house = await create_account(
            db_session, budget, "Ferry", account_type="mortgage", on_budget=False
        )
        await create_transaction(db_session, budget, house, "1219535.99", RECENT)
        await db_session.flush()

        assert "liability_positive_balance" in await _run(db_session, budget)

    async def test_a_normal_loan_is_not(self, db_session):
        services, budget = await _world(db_session)
        loan = await create_account(
            db_session, budget, "Auto", account_type="auto_loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-14200.00", RECENT)
        await db_session.flush()

        assert "liability_positive_balance" not in await _run(db_session, budget)

    async def test_a_credit_card_resting_slightly_in_credit_is_not(self, db_session):
        """The false positive that would cost us the finding above. Paying a
        card in full and getting a small refund is normal, and a panel that
        flags it is one people stop reading."""
        services, budget = await _world(db_session)
        card = await create_account(
            db_session, budget, "Visa", account_type="credit_card", on_budget=True
        )
        await create_transaction(db_session, budget, card, "42.00", RECENT)
        await db_session.flush()

        assert "liability_positive_balance" not in await _run(db_session, budget)

    async def test_a_pending_row_does_not_move_the_balance(self, db_session):
        """Matches AccountRepository.get_balance — pending amounts are
        provisional, so a finding must not appear and vanish at posting."""
        services, budget = await _world(db_session)
        loan = await create_account(
            db_session, budget, "Auto", account_type="auto_loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "50000.00", RECENT, cleared="pending")
        await db_session.flush()

        assert "liability_positive_balance" not in await _run(db_session, budget)


class TestUnpairedTransferLegs:
    """The 1,117. This is the finding's real home: the import reported them in
    a toast that vanished, with no way to reach the rows."""

    async def test_a_leg_with_no_partner_is_reported_with_its_count(self, db_session):
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        savings = await create_account(db_session, budget, "Savings")
        to_savings = await create_payee(
            db_session, budget, "Transfer : Savings", transfer_account_id=savings.id
        )
        await create_transaction(db_session, budget, checking, "-500.00", RECENT, payee=to_savings)
        await create_transaction(db_session, budget, checking, "-25.00", RECENT, payee=to_savings)
        await db_session.flush()

        finding = (await _run(db_session, budget))["unpaired_transfer_legs"]
        assert finding.transaction_count == 2

    async def test_a_properly_linked_transfer_is_not(self, db_session):
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        savings = await create_account(db_session, budget, "Savings")
        out = await create_transaction(db_session, budget, checking, "-300.00", RECENT)
        back = await create_transaction(
            db_session, budget, savings, "300.00", RECENT, transfer_id=out.id
        )
        out.transfer_id = back.id
        await db_session.flush()

        assert "unpaired_transfer_legs" not in await _run(db_session, budget)

    async def test_an_ordinary_payee_is_not(self, db_session):
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        shop = await create_payee(db_session, budget, "Corner Shop")
        await create_transaction(db_session, budget, checking, "-12.00", RECENT, payee=shop)
        await create_transaction(db_session, budget, checking, "-8.00", RECENT)
        await db_session.flush()

        assert "unpaired_transfer_legs" not in await _run(db_session, budget)

    async def test_the_count_matches_the_transactions_filter_it_links_to(self, db_session):
        """A panel that disagrees with the list it sends you to is worse than
        no panel — that exact mismatch is what made the needs-a-category badge
        untrustworthy."""
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        savings = await create_account(db_session, budget, "Savings")
        to_savings = await create_payee(
            db_session, budget, "Transfer : Savings", transfer_account_id=savings.id
        )
        for amount in ("-500.00", "-25.00", "-7.00"):
            await create_transaction(db_session, budget, checking, amount, RECENT, payee=to_savings)
        await db_session.flush()

        finding = (await _run(db_session, budget))["unpaired_transfer_legs"]
        _, count, _ = await services.transaction_repo.list_for_budget(
            budget.id, unpaired_transfers=True
        )
        assert finding.transaction_count == count == 3


class TestDormantOpenAccounts:
    async def test_an_account_quiet_for_years_is_reported(self, db_session):
        services, budget = await _world(db_session)
        old = await create_account(db_session, budget, "Old Savings")
        await create_transaction(db_session, budget, old, "5.00", LONG_AGO)
        await db_session.flush()

        assert "dormant_open_account" in await _run(db_session, budget)

    async def test_a_recently_used_account_is_not(self, db_session):
        services, budget = await _world(db_session)
        live = await create_account(db_session, budget, "Checking")
        await create_transaction(db_session, budget, live, "5.00", RECENT)
        await db_session.flush()

        assert "dormant_open_account" not in await _run(db_session, budget)

    async def test_an_already_closed_account_is_not(self, db_session):
        """It has been dealt with. Suggesting it again is how a panel becomes
        noise the user dismisses permanently."""
        services, budget = await _world(db_session)
        old = await create_account(db_session, budget, "Old Savings")
        old.is_closed = True
        await create_transaction(db_session, budget, old, "5.00", LONG_AGO)
        await db_session.flush()

        assert "dormant_open_account" not in await _run(db_session, budget)

    async def test_a_brand_new_empty_account_is_not(self, db_session):
        """No transactions is not the same as no recent transactions. Nagging
        about an account someone opened this morning is the opposite of help."""
        services, budget = await _world(db_session)
        await create_account(db_session, budget, "Just Opened")
        await db_session.flush()

        assert "dormant_open_account" not in await _run(db_session, budget)


class TestStaleCompanionLiabilities:
    """Closes the known gap from companion liabilities: retyping an account
    away from a debt type leaves its companion behind at $0."""

    async def test_a_payoff_record_on_a_non_debt_account_is_reported(self, db_session):
        services, budget = await _world(db_session)
        asset = await create_account(
            db_session, budget, "Ferry", account_type="other_asset", on_budget=False
        )
        db_session.add(
            Liability(
                budget_id=budget.id,
                name="Ferry",
                linked_account_id=asset.id,
                liability_type="mortgage",
                manual_balance=Decimal("0"),
            )
        )
        await db_session.flush()

        assert "stale_companion_liability" in await _run(db_session, budget)

    async def test_a_payoff_record_on_a_real_debt_is_not(self, db_session):
        services, budget = await _world(db_session)
        loan = await create_account(
            db_session, budget, "Auto", account_type="auto_loan", on_budget=False
        )
        db_session.add(
            Liability(
                budget_id=budget.id,
                name="Auto",
                linked_account_id=loan.id,
                liability_type="auto_loan",
                manual_balance=Decimal("0"),
            )
        )
        await db_session.flush()

        assert "stale_companion_liability" not in await _run(db_session, budget)


class TestCardRowsFiledAsIncome:
    """A charge on a card filed to an income category, which reaches no
    envelope at all. Untested until the predicate it asks with moved to
    `row_category(IN_SYSTEM_GROUP)`; the file's own rule is that each check is
    tested with and without its condition, and this one had neither."""

    async def _world_with_a_card(self, db_session):
        services, budget = await _world(db_session)
        card = await create_account(
            db_session, budget, "Visa", account_type="credit_card", on_budget=True
        )
        income_group = await create_category_group(db_session, budget, "Income", is_system=True)
        income = await create_category(db_session, budget, income_group, "Inflow")
        everyday = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, everyday, "Groceries")
        return budget, card, income, groceries

    async def test_a_card_charge_filed_to_income_is_reported(self, db_session):
        budget, card, income, _ = await self._world_with_a_card(db_session)
        await create_transaction(db_session, budget, card, "-30.00", RECENT, category=income)
        await create_transaction(db_session, budget, card, "-12.00", RECENT, category=income)
        await db_session.flush()

        finding = (await _run(db_session, budget))["card_rows_filed_as_income"]
        assert finding.transaction_count == 2

    async def test_an_uncategorized_card_charge_is_not(self, db_session):
        """The NULL-category case. The old spelling dropped these by inner
        joining Category; the EXISTS form has to drop them too, and the check
        would be useless if it did not — an uncategorized charge is the state
        this finding tells you to move toward."""
        budget, card, _, _ = await self._world_with_a_card(db_session)
        await create_transaction(db_session, budget, card, "-30.00", RECENT)
        await db_session.flush()

        assert "card_rows_filed_as_income" not in await _run(db_session, budget)

    async def test_a_card_charge_in_a_real_envelope_is_not(self, db_session):
        budget, card, _, groceries = await self._world_with_a_card(db_session)
        await create_transaction(db_session, budget, card, "-30.00", RECENT, category=groceries)
        await db_session.flush()

        assert "card_rows_filed_as_income" not in await _run(db_session, budget)

    async def test_a_cash_charge_filed_to_income_is_not(self, db_session):
        """Deliberately excluded: on a cash account this is YNAB's own
        convention for a reconciliation adjustment, and flagging those would
        bury the signal."""
        budget, _card, income, _ = await self._world_with_a_card(db_session)
        checking = await create_account(db_session, budget, "Redwood Checking")
        await create_transaction(db_session, budget, checking, "-30.00", RECENT, category=income)
        await db_session.flush()

        assert "card_rows_filed_as_income" not in await _run(db_session, budget)

    async def test_a_card_inflow_filed_to_income_is_not(self, db_session):
        """The other side of the same misfiling, and not this check's job: a
        credit filed to income is money arriving, not a charge. It is named by
        `txn_filters.UNCLAIMED_CARD_ROW` instead, which is what stops the
        card reserve identity reporting it as drift."""
        budget, card, income, _ = await self._world_with_a_card(db_session)
        await create_transaction(db_session, budget, card, "50.00", RECENT, category=income)
        await db_session.flush()

        assert "card_rows_filed_as_income" not in await _run(db_session, budget)


class TestMoneyInAnArchivedEnvelope:
    """Archiving refuses to leave a balance behind. This finds the ones that
    predate that rule — and they are invisible now, because the budget grid no
    longer draws archived envelopes and the toggle that used to reach them is
    gone."""

    async def _archived_holding(self, db_session, amount: str | None):
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Redwood Checking")
        income_group = await create_category_group(db_session, budget, "Income", is_system=True)
        inflow = await create_category(db_session, budget, income_group, "Inflow")
        await create_transaction(db_session, budget, checking, "500.00", RECENT, category=inflow)
        group = await create_category_group(db_session, budget, "Everyday")
        cat = await create_category(db_session, budget, group, "Gym")
        await db_session.flush()
        if amount is not None:
            await services.budgets.set_assignment(
                budget.id, cat.id, TODAY.replace(day=1), Decimal(amount)
            )
        # Flipped directly: this is what the app did before the archive flow
        # existed, and it is the state those budgets are in.
        cat.is_archived = True
        await db_session.flush()
        return budget, cat

    async def test_a_balance_left_behind_is_reported(self, db_session):
        budget, _cat = await self._archived_holding(db_session, "75.00")
        finding = (await _run(db_session, budget))["money_in_an_archived_envelope"]
        assert "Gym" in finding.detail
        assert "1 archived envelope" in finding.title

    async def test_an_empty_archived_envelope_is_not(self, db_session):
        budget, _cat = await self._archived_holding(db_session, None)
        assert "money_in_an_archived_envelope" not in await _run(db_session, budget)

    async def test_a_live_envelope_holding_money_is_not(self, db_session):
        """The control. Money in an envelope the budget draws is just a
        budget — the defect is money somewhere nobody can see."""
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Redwood Checking")
        income_group = await create_category_group(db_session, budget, "Income", is_system=True)
        inflow = await create_category(db_session, budget, income_group, "Inflow")
        await create_transaction(db_session, budget, checking, "500.00", RECENT, category=inflow)
        group = await create_category_group(db_session, budget, "Everyday")
        cat = await create_category(db_session, budget, group, "Gym")
        await db_session.flush()
        await services.budgets.set_assignment(
            budget.id, cat.id, TODAY.replace(day=1), Decimal("75.00")
        )

        assert "money_in_an_archived_envelope" not in await _run(db_session, budget)


async def test_a_healthy_budget_reports_nothing(db_session):
    """The outcome worth earning. If a clean budget still produces findings,
    the panel is decoration and will be dismissed on sight."""
    services, budget = await _world(db_session)
    checking = await create_account(db_session, budget, "Redwood Checking")
    card = await create_account(
        db_session, budget, "Visa", account_type="credit_card", on_budget=True
    )
    shop = await create_payee(db_session, budget, "Corner Shop")
    await create_transaction(db_session, budget, checking, "-12.00", RECENT, payee=shop)
    await create_transaction(db_session, budget, card, "-40.00", RECENT, payee=shop)
    await db_session.flush()

    report = await AccountHygieneService(db_session).run(budget.id)
    assert report.clean, [f.kind for f in report.findings]


class TestUnlinkedCardPayments:
    """The gap between the two pairing rules.

    `_unpaired_transfer_legs` finds rows whose PAYEE already names another
    account. Two synced legs of one card payment arrive with ordinary bank
    payees on both sides, so it never sees them — and `repair_transfers` is
    payee-based too. The amount-based pass runs only over rows a sync just
    created, so a budget that already holds both legs had no path to the
    answer at all.

    A real card read "paid to the card 0.00" against three payments totalling
    five figures, all sitting in the "credits that came from nowhere" term.
    Amounts here are invented and rescaled.
    """

    async def test_a_card_credit_matching_a_cash_debit_is_reported(self, db_session):
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        card = await create_account(db_session, budget, "Card", account_type="credit_card")
        await create_transaction(db_session, budget, checking, "-460.00", RECENT)
        await create_transaction(db_session, budget, card, "460.00", RECENT)
        await db_session.flush()

        finding = (await _run(db_session, budget))["unlinked_card_payments"]
        assert finding.transaction_count == 1
        assert card.id in finding.account_ids

    async def test_a_category_on_the_cash_leg_still_reports(self, db_session):
        """The real shape, and the reason nothing linked it. Linking an
        on-budget pair must clear the category — an internal transfer is not
        spending — and a person's category is never cleared unattended, so
        `pair_legs` holds the pair for review. Held for review is exactly what
        this finding exists to surface: silence there is what produced a card
        reading 'paid 0.00' beside a balance that visibly fell."""
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        card = await create_account(db_session, budget, "Card", account_type="credit_card")
        group = await create_category_group(db_session, budget, "Bills")
        envelope = await create_category(db_session, budget, group, "Card Payment")
        await create_transaction(db_session, budget, checking, "-460.00", RECENT, category=envelope)
        await create_transaction(db_session, budget, card, "460.00", RECENT)
        await db_session.flush()

        finding = (await _run(db_session, budget))["unlinked_card_payments"]
        assert finding.transaction_count == 1

    async def test_an_already_linked_payment_is_not(self, db_session):
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        card = await create_account(db_session, budget, "Card", account_type="credit_card")
        out = await create_transaction(db_session, budget, checking, "-460.00", RECENT)
        back = await create_transaction(
            db_session, budget, card, "460.00", RECENT, transfer_id=out.id
        )
        out.transfer_id = back.id
        await db_session.flush()

        assert "unlinked_card_payments" not in await _run(db_session, budget)

    async def test_a_refund_with_no_cash_partner_is_not(self, db_session):
        """A card credit that is genuinely a refund has no matching debit, so
        nothing is claimed about it. The finding must not fire on every
        inflow — that is how a panel gets dismissed and stops being read."""
        services, budget = await _world(db_session)
        await create_account(db_session, budget, "Checking")
        card = await create_account(db_session, budget, "Card", account_type="credit_card")
        await create_transaction(db_session, budget, card, "460.00", RECENT)
        await db_session.flush()

        assert "unlinked_card_payments" not in await _run(db_session, budget)

    async def test_two_cash_accounts_moving_money_is_not_a_card_payment(self, db_session):
        """Scoped to cards on purpose: a checking-to-savings pair is the other
        finding's business, and reporting it here would double-count it."""
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        savings = await create_account(db_session, budget, "Savings", account_type="savings")
        await create_transaction(db_session, budget, checking, "-460.00", RECENT)
        await create_transaction(db_session, budget, savings, "460.00", RECENT)
        await db_session.flush()

        assert "unlinked_card_payments" not in await _run(db_session, budget)

    async def test_a_payment_older_than_the_lookback_is_not(self, db_session):
        """`pair_legs` compares every outflow against every inflow in the
        window, so the window is bounded and says so rather than quietly
        getting slower as a budget grows."""
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        card = await create_account(db_session, budget, "Card", account_type="credit_card")
        await create_transaction(db_session, budget, checking, "-460.00", LONG_AGO)
        await create_transaction(db_session, budget, card, "460.00", LONG_AGO)
        await db_session.flush()

        assert "unlinked_card_payments" not in await _run(db_session, budget)
