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

from sqlalchemy import select

from igab.db.models import ChangeLog, Liability
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.account_hygiene import AccountHygieneService, FindingItem, HygieneFinding
from igab.services.undo_service import UndoService

from .factories import (
    create_account,
    create_budget,
    create_card_payment,
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


def _months(count: int) -> list[date]:
    """`count` consecutive month starts ending at the current one — oldest
    first, so a stream reads in the order it happened."""
    months = [RECENT.replace(day=1)]
    for _ in range(count - 1):
        months.append((months[-1] - timedelta(days=1)).replace(day=1))
    return list(reversed(months))


async def _world(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    return services, budget


async def _run(db_session, budget) -> dict[str, HygieneFinding]:
    report = await AccountHygieneService(db_session).run(budget.id)
    return {f.kind: f for f in report.findings}


def _words(finding: HygieneFinding) -> str:
    """Every sentence a finding shows, for "is this named anywhere" checks."""
    parts = [finding.title, finding.summary, finding.action, finding.why or ""]
    for item in finding.items:
        parts += [item.label, item.note or ""]
    return " ".join(parts)


def _item(finding: HygieneFinding, label: str) -> FindingItem:
    [item] = [i for i in finding.items if i.label == label]
    return item


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


class TestAClosedAccountStillHoldingMoney:
    """Closed and on-budget is not a contradiction — the commonest closed
    account in any budget is a checking account closed at a change of banks,
    and it was on budget for its whole life. Forcing them apart would be worse
    than the gap: `on_budget` is read at query time, so flipping it on close
    would reclassify every historical row on the account.

    What IS a contradiction is a closed on-budget account holding money.
    Closing moves none, so the balance goes on funding Ready to Assign from an
    account no longer in the sidebar, and nothing said so.
    """

    async def test_a_closed_checking_account_with_a_balance_is_reported(self, db_session):
        services, budget = await _world(db_session)
        old = await create_account(db_session, budget, "First National Checking", on_budget=True)
        await create_transaction(db_session, budget, old, "400.00", RECENT)
        old.is_closed = True
        await db_session.flush()

        findings = await _run(db_session, budget)
        assert "closed_account_holds_money" in findings
        item = _item(findings["closed_account_holds_money"], "First National Checking")
        # Raw, for the client to format — never written into a sentence.
        assert item.amount == Decimal("400.00")

    async def test_an_emptied_one_is_not(self, db_session):
        """The normal close: transfer the money out, then close. A finding here
        would fire on every tidy account anyone ever put away."""
        services, budget = await _world(db_session)
        old = await create_account(db_session, budget, "First National Checking", on_budget=True)
        await create_transaction(db_session, budget, old, "400.00", RECENT)
        await create_transaction(db_session, budget, old, "-400.00", RECENT)
        old.is_closed = True
        await db_session.flush()

        assert "closed_account_holds_money" not in await _run(db_session, budget)

    async def test_an_open_account_with_a_balance_is_not(self, db_session):
        """Money in an open account is the ordinary state of a budget."""
        services, budget = await _world(db_session)
        live = await create_account(db_session, budget, "Redwood Checking", on_budget=True)
        await create_transaction(db_session, budget, live, "400.00", RECENT)
        await db_session.flush()

        assert "closed_account_holds_money" not in await _run(db_session, budget)

    async def test_a_closed_tracking_account_is_not(self, db_session):
        """A brokerage holds no envelope money whatever its balance, so
        closing one changes no budget figure. This is also the case that made
        the whole question concrete — a closed asset account whose value never
        belonged in the budget."""
        services, budget = await _world(db_session)
        brokerage = await create_account(
            db_session,
            budget,
            "Cascade Point Brokerage",
            account_type="investment",
            on_budget=False,
        )
        await create_transaction(db_session, budget, brokerage, "52000.00", RECENT)
        brokerage.is_closed = True
        await db_session.flush()

        assert "closed_account_holds_money" not in await _run(db_session, budget)

    async def test_a_closed_card_is_left_to_the_cards_section(self, db_session):
        """Not reported twice. `get_budget_summary` already keeps a closed
        card's row on the budget page, tagged, until its balance and set-aside
        both reach zero — with the actions sitting next to it."""
        services, budget = await _world(db_session)
        card = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
        )
        await create_transaction(db_session, budget, card, "-950.00", RECENT)
        card.is_closed = True
        await db_session.flush()

        assert "closed_account_holds_money" not in await _run(db_session, budget)

    async def test_an_overdrawn_closed_account_counts_too(self, db_session):
        """A negative balance is money the budget is counting against you, and
        hiding the account does not settle it."""
        services, budget = await _world(db_session)
        old = await create_account(db_session, budget, "Harborview Cash", on_budget=True)
        await create_transaction(db_session, budget, old, "-120.00", RECENT)
        old.is_closed = True
        await db_session.flush()

        assert "closed_account_holds_money" in await _run(db_session, budget)


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

    async def test_a_card_reconciliation_adjustment_is_not(self, db_session):
        """YNAB writes the identical income-filed adjustment row when you
        reconcile a *card*, and the cash-account skip did not reach it: a real
        import's hygiene sweep read twelve of these as card charges filed as
        income. A ledger correction is not spending to give an envelope, so
        the skip follows the payee (`BALANCE_ADJUSTMENT_PAYEES`), not the
        account classification."""
        budget, card, income, _ = await self._world_with_a_card(db_session)
        adjustment = await create_payee(db_session, budget, "Reconciliation Balance Adjustment")
        await create_transaction(
            db_session, budget, card, "-45.00", RECENT, category=income, payee=adjustment
        )
        await db_session.flush()

        assert "card_rows_filed_as_income" not in await _run(db_session, budget)

    async def test_a_card_starting_balance_is_not(self, db_session):
        """Same convention, written once per account instead of once per
        reconcile: YNAB's opening row on a card is filed to Inflow and
        imported verbatim. IGAB's own starting balances never get here — they
        are written uncategorized — so any row shaped like this came from an
        import, carrying YNAB's filing."""
        budget, card, income, _ = await self._world_with_a_card(db_session)
        opening = await create_payee(db_session, budget, "Starting Balance")
        await create_transaction(
            db_session, budget, card, "-800.00", RECENT, category=income, payee=opening
        )
        await db_session.flush()

        assert "card_rows_filed_as_income" not in await _run(db_session, budget)

    async def test_adjustment_rows_do_not_hide_real_misfilings(self, db_session):
        """The skip must subtract the convention rows, not silence the check:
        the same sweep that flagged thirteen adjustment rows also held three
        genuine misfiled charges, and those are the finding's whole point."""
        budget, card, income, _ = await self._world_with_a_card(db_session)
        adjustment = await create_payee(db_session, budget, "Reconciliation Balance Adjustment")
        merchant = await create_payee(db_session, budget, "Nordstrom")
        await create_transaction(
            db_session, budget, card, "-45.00", RECENT, category=income, payee=adjustment
        )
        await create_transaction(
            db_session, budget, card, "-60.00", RECENT, category=income, payee=adjustment
        )
        await create_transaction(
            db_session, budget, card, "-30.00", RECENT, category=income, payee=merchant
        )
        await db_session.flush()

        finding = (await _run(db_session, budget))["card_rows_filed_as_income"]
        assert finding.transaction_count == 1


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
        assert [i.label for i in finding.items] == ["Gym"]
        assert _item(finding, "Gym").amount == Decimal("75.00")
        assert "1 archived envelope" in finding.title
        # It once said "these predate that rule" about an envelope assigned to
        # the same month. It does not guess how the money got there.
        assert "predate" not in _words(finding)

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
        [item] = finding.items
        assert item.label == "Card"
        assert item.amount == Decimal("460.00")
        assert item.note == "from Checking, filed to Card Payment"
        assert item.account_id == card.id

    async def test_a_charge_beside_a_deposit_is_not_a_payment(self, db_session):
        """The reverse direction — money OUT of the card, IN to checking — is
        a cash advance or a coincidence. Calling it a payment would ask the
        user to link a charge as if it had paid the card down."""
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        card = await create_account(db_session, budget, "Card", account_type="credit_card")
        await create_transaction(db_session, budget, card, "-460.00", RECENT)
        await create_transaction(db_session, budget, checking, "460.00", RECENT)
        await db_session.flush()

        assert "unlinked_card_payments" not in await _run(db_session, budget)

    async def test_a_payment_from_before_the_card_joined_the_budget_is_not(self, db_session):
        """Opening position, not unfiled work. A real budget reported nine
        payments that all predated their cards' start dates; linking them
        spent each card's Set aside on debt the budget never carried, and
        returned the money to envelopes that had been archived."""
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        card = await create_account(db_session, budget, "Card", account_type="credit_card")
        card.budget_start_date = RECENT + timedelta(days=1)
        await create_transaction(db_session, budget, checking, "-460.00", RECENT)
        await create_transaction(db_session, budget, card, "460.00", RECENT)
        await db_session.flush()

        assert "unlinked_card_payments" not in await _run(db_session, budget)

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


class TestLinkingCardPaymentsInBulk:
    """The finding's "Link them" button: the confirmed pairs, as one undo.

    Nine payments on a real budget were each "open one and pick its partner"
    — nine trips through the register for one decision.
    """

    async def _pair(self, db_session, budget, amount="460.00", name="Card"):
        checking = await create_account(db_session, budget, f"{name} Checking")
        card = await create_account(db_session, budget, name, account_type="credit_card")
        group = await create_category_group(db_session, budget, f"{name} Bills")
        envelope = await create_category(db_session, budget, group, f"{name} Payment")
        out = await create_transaction(
            db_session, budget, checking, f"-{amount}", RECENT, category=envelope
        )
        back = await create_transaction(db_session, budget, card, amount, RECENT)
        await db_session.flush()
        return out, back

    async def _link(self, api_client, budget, pairs):
        r = await api_client.post(
            f"/api/v1/{budget.id}/accounts/hygiene/link-card-payments",
            json={"pairs": [[str(o), str(i)] for o, i in pairs]},
        )
        assert r.status_code == 200, r.text
        return r.json()

    async def test_the_confirmed_pair_is_linked_and_the_envelope_cleared(
        self, db_session, api_client
    ):
        budget = await create_budget(db_session, api_client.test_user)
        out, back = await self._pair(db_session, budget)
        [item] = (await _run(db_session, budget))["unlinked_card_payments"].items
        assert item.transaction_ids == [out.id, back.id]

        assert await self._link(api_client, budget, [(out.id, back.id)]) == {
            "linked": 1,
            "skipped": 0,
        }
        db_session.expunge_all()
        repo = TransactionRepository(db_session)
        linked_out = await repo.get_or_raise(out.id)
        assert linked_out.transfer_id == back.id
        # A transfer is not spending: the envelope gets the money back.
        assert linked_out.category_id is None
        assert "unlinked_card_payments" not in await _run(db_session, budget)

    async def test_every_pair_undoes_as_one_step(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        first = await self._pair(db_session, budget, "460.00")
        second = await self._pair(db_session, budget, "125.00", name="Other Card")
        await self._link(
            api_client, budget, [(first[0].id, first[1].id), (second[0].id, second[1].id)]
        )

        changes = list(
            (
                await db_session.execute(
                    select(ChangeLog).where(
                        ChangeLog.budget_id == budget.id, ChangeLog.entity_type == "transaction"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(changes) == 4
        assert len({c.batch_id for c in changes}) == 1, "one undo, not one per pair"
        await UndoService(db_session).undo_batch(budget.id, changes[0].batch_id)
        db_session.expunge_all()
        restored = await TransactionRepository(db_session).get_or_raise(first[0].id)
        assert restored.transfer_id is None
        assert restored.category_id is not None

    async def test_a_pair_the_finding_does_not_report_is_refused(self, db_session, api_client):
        """Recomputed on the server, never taken on the client's word: two
        rows the finding would not pair are left alone, not linked."""
        budget = await create_budget(db_session, api_client.test_user)
        out, _back = await self._pair(db_session, budget)
        checking = await create_account(db_session, budget, "Savings", account_type="savings")
        stranger = await create_transaction(db_session, budget, checking, "999.00", RECENT)
        await db_session.flush()

        assert await self._link(api_client, budget, [(out.id, stranger.id)]) == {
            "linked": 0,
            "skipped": 1,
        }
        db_session.expunge_all()
        assert (await TransactionRepository(db_session).get_or_raise(out.id)).transfer_id is None


class TestCardReserveDiagnostics:
    """The findings that explain a card whose Set aside went wrong.

    Each one is a shape a ten-year import actually produced: a reserve driven
    below zero, an inflow filed to an envelope that never charged the card, a
    payment landing on the wrong card, debt older than the budget, and the
    hand-made card's envelope the migration left behind. Amounts are
    invented and rescaled, as everywhere."""

    async def _card_world(self, db_session):
        services, budget = await _world(db_session)
        checking = await create_account(db_session, budget, "Checking")
        card = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
        )
        group = await create_category_group(db_session, budget, "Everyday")
        cat = await create_category(db_session, budget, group, "Groceries")
        return services, budget, checking, card, group, cat

    async def test_a_payment_past_set_aside_is_told_by_its_cause_not_by_its_sign(self, db_session):
        """Pre-budget debt, one funded month, and a full-statement payment:
        Set aside reads 200 − 500 = −300 while the card still owes 1,700.

        A finding used to name every card below zero. A negative Set aside is
        overspending now — the card draws red on the budget page and the 1st
        covers it from Ready to Assign — so the page says that part, and the
        only finding here is the one that says why: the debt predates the
        budget."""
        services, budget, checking, card, _group, cat = await self._card_world(db_session)
        await create_transaction(db_session, budget, card, "-2000.00", LONG_AGO)
        await services.budgets.set_assignment(
            budget.id, cat.id, RECENT.replace(day=1), Decimal("200.00")
        )
        await create_transaction(db_session, budget, card, "-200.00", RECENT, category=cat)
        await create_card_payment(services, budget, checking, card, "500.00", RECENT)

        findings = await _run(db_session, budget)
        naming = {kind for kind, f in findings.items() if card.id in f.account_ids}
        assert naming == {"card_debt_predates_budget"}

    async def test_an_inflow_via_an_envelope_that_never_charged_the_card(self, db_session):
        """The reimbursed shape: a shared-expenses envelope that never touched
        this card receives money on it. Nothing was riding to release, so the
        reserve fell outright — and the finding names the envelope."""
        services, budget, _checking, card, group, _cat = await self._card_world(db_session)
        shared = await create_category(db_session, budget, group, "Shared Expenses")
        await create_transaction(db_session, budget, card, "-800.00", LONG_AGO)
        await create_transaction(db_session, budget, card, "300.00", RECENT, category=shared)

        findings = await _run(db_session, budget)
        # The card is red on the budget page; only this finding says where
        # the money went. It stood aside for the below-zero finding once.
        item = _item(findings["residual_on_uncharged_category"], "Shared Expenses")
        assert item.amount == Decimal("300.00")
        assert item.note == "on Sapphire Visa"

    async def test_an_uncharged_inflow_on_a_card_still_above_zero_is_reported_too(self, db_session):
        """Funded charges keep the card above zero, so it is not red — the
        envelope that kept the refund is still worth a line."""
        services, budget, _checking, card, group, cat = await self._card_world(db_session)
        shared = await create_category(db_session, budget, group, "Shared Expenses")
        await services.budgets.set_assignment(
            budget.id, cat.id, RECENT.replace(day=1), Decimal("500.00")
        )
        await create_transaction(db_session, budget, card, "-500.00", RECENT, category=cat)
        await create_transaction(db_session, budget, card, "300.00", RECENT, category=shared)

        findings = await _run(db_session, budget)
        finding = findings["residual_on_uncharged_category"]
        item = _item(finding, "Shared Expenses")
        assert item.amount == Decimal("300.00")
        assert item.note == "on Sapphire Visa"
        assert finding.account_ids == [card.id]

    async def test_an_inflow_is_not_sent_to_another_card_because_its_envelope_charged_one(
        self, db_session
    ):
        """A real budget: a refund of a doubled charge, on the card that was
        charged, filed to an envelope whose other spending was on a second
        card — and a finding told the user to move it to that second card's
        register. Where an envelope's spending sits says nothing about where
        a refund belongs, so nothing may name the other card."""
        services, budget, _checking, card, group, _cat = await self._card_world(db_session)
        other = await create_account(
            db_session, budget, "Nordvik Store Card", account_type="credit_card", on_budget=True
        )
        shopping = await create_category(db_session, budget, group, "Shopping")
        await services.budgets.set_assignment(
            budget.id, shopping.id, RECENT.replace(day=1), Decimal("300.00")
        )
        await create_transaction(db_session, budget, other, "-300.00", RECENT, category=shopping)
        await create_transaction(db_session, budget, card, "300.00", RECENT, category=shopping)

        findings = await _run(db_session, budget)
        assert "card_inflow_belongs_to_other_card" not in findings
        # The unlinked-payment finding may still ask whether the two rows are
        # one movement (same amount, same day — a balance transfer looks like
        # this); what must be gone is the guess that the refund belongs there.
        assert [
            k
            for k, f in findings.items()
            if "Nordvik" in _words(f) and k != "unlinked_card_payments"
        ] == []
        # The Sapphire is in credit, so it has no negative line; the refund's
        # envelope is named where the money is — on this card, not another.
        assert _item(findings["residual_on_uncharged_category"], "Shopping").note == (
            "on Sapphire Visa"
        )

    async def test_the_same_inflow_on_a_ledger_envelope_is_silent(self, db_session):
        """The identical rows minus the funding. Nothing of the household's
        was ever reserved through this envelope, so the inflow stranded
        nothing — the Sapphire's reserve fell beside a Sapphire debt that
        fell with it, and 'move it to the other card' would be bookkeeping
        advice about money that is not at risk."""
        services, budget, _checking, card, group, _cat = await self._card_world(db_session)
        other = await create_account(
            db_session, budget, "Nordvik Store Card", account_type="credit_card", on_budget=True
        )
        shopping = await create_category(db_session, budget, group, "Shared Expenses")
        await create_transaction(db_session, budget, other, "-300.00", RECENT, category=shopping)
        await create_transaction(db_session, budget, card, "300.00", RECENT, category=shopping)

        assert "card_inflow_belongs_to_other_card" not in await _run(db_session, budget)

    async def test_debt_older_than_the_budgets_first_reserving_is_named(self, db_session):
        """A card synced in with bank history: charges long before anything
        reserved. Only fires once reserving HAS begun — a card with no
        reserving at all is unfiled spending, which its own row explains."""
        services, budget, _checking, card, _group, cat = await self._card_world(db_session)
        await create_transaction(db_session, budget, card, "-500.00", LONG_AGO)
        await services.budgets.set_assignment(
            budget.id, cat.id, RECENT.replace(day=1), Decimal("100.00")
        )
        await create_transaction(db_session, budget, card, "-100.00", RECENT, category=cat)

        finding = (await _run(db_session, budget))["card_debt_predates_budget"]
        item = _item(finding, "Sapphire Visa")
        assert item.note is not None
        assert item.note.startswith(f"charged since {LONG_AGO:%B %Y}, nothing set aside until")
        assert item.amount == Decimal("500.00")
        assert finding.account_ids == [card.id]
        # It used to say "set the account's budget start date" — which only
        # quiets Needs a category; the card's figures never read it.
        assert "start date" not in finding.action

    async def test_an_envelope_that_happens_to_match_a_negative_reserve_is_not_blamed(
        self, db_session
    ):
        """A report from a real budget: Medical held 316 while a card's Set
        aside read -310, and hygiene said Medical was a payment fund that had
        kept the card's money. Medical had never touched the card. Nothing
        but the two amounts connected them, so no finding may name it."""
        services, budget, checking, card, group, cat = await self._card_world(db_session)
        medical = await create_category(db_session, budget, group, "Medical")
        await services.budgets.set_assignment(
            budget.id, medical.id, RECENT.replace(day=1), Decimal("316.00")
        )
        await create_transaction(db_session, budget, card, "-2000.00", LONG_AGO)
        await services.budgets.set_assignment(
            budget.id, cat.id, RECENT.replace(day=1), Decimal("200.00")
        )
        await create_transaction(db_session, budget, card, "-200.00", RECENT, category=cat)
        await create_card_payment(services, budget, checking, card, "510.00", RECENT)

        findings = await _run(db_session, budget)
        assert not any("Medical" in _words(f) for f in findings.values())

    async def test_a_recurring_inflow_stream_on_a_charging_envelope_is_reported(self, db_session):
        """The 42-month shape the probe found on a real import: the envelope
        DOES charge this card, so the two misfiled-inflow findings skip it on
        their existence test — while its inflows cumulatively outrun its
        charges and every month's residual drains the reserve. Two residual
        months is the line: a stream, not a refund overshoot."""
        services, budget, _checking, card, _group, cat = await self._card_world(db_session)
        month_2 = RECENT.replace(day=1)
        month_1 = (month_2 - timedelta(days=1)).replace(day=1)
        await create_transaction(db_session, budget, card, "-800.00", LONG_AGO)
        await services.budgets.set_assignment(
            budget.id, cat.id, LONG_AGO.replace(day=1), Decimal("50.00")
        )
        await create_transaction(db_session, budget, card, "-50.00", LONG_AGO, category=cat)
        await create_transaction(db_session, budget, card, "200.00", month_1, category=cat)
        await create_transaction(db_session, budget, card, "200.00", month_2, category=cat)

        findings = await _run(db_session, budget)
        finding = findings["recurring_card_residual"]
        assert _item(finding, "Groceries").note == "on Sapphire Visa, over 2 months"
        assert finding.account_ids == [card.id]
        # The charged() guard used to make these two the only vocabulary, and
        # this shape fit neither — that silence is the bug this finding fixes.
        assert "residual_on_uncharged_category" not in findings
        assert "card_inflow_belongs_to_other_card" not in findings

    async def _ledger_stream(self, db_session, budget, card, checking, cat, months):
        """One person's spending, tracked as a running tab and settled onto
        the card. Never funded, square at every month end.

        The first month is charged on the card and settled back through
        checking, so it is covered: it reserves 100, and its outflow is what
        `charged()` reads. Every month after is 100 on the card, 40 somewhere
        else, and one 140 repayment onto the card — so that pair nets to an
        inflow of 40 a month. The first two of those release the reserve the
        opening month built; once it is gone the rest is residual, month
        after month, monotone by construction. That is the whole mechanic:
        the repayment paid the card down 40 more than was charged to it, so
        the household pays the card 40 less from its own cash."""
        await create_transaction(db_session, budget, card, "-100.00", months[0], category=cat)
        await create_transaction(db_session, budget, checking, "100.00", months[0], category=cat)
        for month in months[1:]:
            await create_transaction(db_session, budget, card, "-100.00", month, category=cat)
            await create_transaction(db_session, budget, checking, "-40.00", month, category=cat)
            await create_transaction(db_session, budget, card, "140.00", month, category=cat)

    async def test_a_receivable_ledger_settled_onto_the_card_is_silent(self, db_session):
        """The workflow the exception exists for, and it is a household
        keeping its budget correctly.

        Residual lands in three separate months on a pair that does charge
        this card — `recurring_card_residual`'s exact signature. It would fire
        every month forever, and the loudest finding a careful household ever
        got would be its own bookkeeping."""
        services, budget, checking, card, group, _cat = await self._card_world(db_session)
        ledger = await create_category(db_session, budget, group, "Shared Expenses")
        await create_transaction(db_session, budget, card, "-800.00", LONG_AGO)
        await self._ledger_stream(db_session, budget, card, checking, ledger, _months(6))

        findings = await _run(db_session, budget)
        assert "recurring_card_residual" not in findings
        assert "residual_on_uncharged_category" not in findings
        assert "card_inflow_belongs_to_other_card" not in findings

    async def test_the_same_stream_on_a_funded_envelope_is_still_reported(self, db_session):
        """The gate is not a mute, and funding is the only variable: the same
        rows, plus one month years back where 20 was assigned and spent on
        this card. That makes it an envelope — the household's own money was
        reserved through it — and inflows outrunning that reserve are
        draining something real. Available reads 0 in both tests, which is
        why availability alone cannot be the rule."""
        services, budget, checking, card, group, _cat = await self._card_world(db_session)
        envelope = await create_category(db_session, budget, group, "Shared Expenses")
        await create_transaction(db_session, budget, card, "-800.00", LONG_AGO)
        await services.budgets.set_assignment(
            budget.id, envelope.id, LONG_AGO.replace(day=1), Decimal("20.00")
        )
        await create_transaction(db_session, budget, card, "-20.00", LONG_AGO, category=envelope)
        await self._ledger_stream(db_session, budget, card, checking, envelope, _months(6))

        findings = await _run(db_session, budget)
        assert _item(findings["recurring_card_residual"], "Shared Expenses").amount is not None

    async def test_a_ledger_that_never_charged_the_card_is_silent(self, db_session):
        """The steady state, with no opening month to reserve anything: every
        month nets to an inflow, so the pair never reads as having charged
        this card and the residual lands in the uncharged finding instead.
        Same envelope, same answer — the gate is on the category, not on
        which of the three findings the shape happens to reach."""
        services, budget, checking, card, group, _cat = await self._card_world(db_session)
        ledger = await create_category(db_session, budget, group, "Shared Expenses")
        for month in _months(2)[1:]:
            await create_transaction(db_session, budget, card, "-100.00", month, category=ledger)
            await create_transaction(db_session, budget, checking, "-40.00", month, category=ledger)
            await create_transaction(db_session, budget, card, "140.00", month, category=ledger)

        findings = await _run(db_session, budget)
        assert "residual_on_uncharged_category" not in findings
        assert "recurring_card_residual" not in findings

    async def test_a_ledger_that_kept_the_inflow_is_still_reported(self, db_session):
        """Never funded, but the repayments ran past the charges and 30 of
        the card's reserve is now sitting in the envelope. Available reads
        positive, so the complaint the finding makes — the envelope keeps the
        money — is simply true, and re-filing the inflow is a real remedy."""
        services, budget, _checking, card, group, _cat = await self._card_world(db_session)
        ledger = await create_category(db_session, budget, group, "Shared Expenses")
        await create_transaction(db_session, budget, card, "-800.00", LONG_AGO)
        for month in _months(2)[1:]:
            await create_transaction(db_session, budget, card, "-100.00", month, category=ledger)
            await create_transaction(db_session, budget, card, "130.00", month, category=ledger)

        findings = await _run(db_session, budget)
        item = _item(findings["residual_on_uncharged_category"], "Shared Expenses")
        assert item.amount == Decimal("30.00")

    async def test_a_single_refund_overshoot_is_not_a_stream(self, db_session):
        """One month of residual on an envelope that charges the card is an
        ordinary oversized refund; flagging every such month is how a panel
        gets dismissed once and never read again."""
        services, budget, _checking, card, _group, cat = await self._card_world(db_session)
        await create_transaction(db_session, budget, card, "-800.00", LONG_AGO)
        await services.budgets.set_assignment(
            budget.id, cat.id, LONG_AGO.replace(day=1), Decimal("50.00")
        )
        await create_transaction(db_session, budget, card, "-50.00", LONG_AGO, category=cat)
        await create_transaction(db_session, budget, card, "300.00", RECENT, category=cat)

        findings = await _run(db_session, budget)
        assert "recurring_card_residual" not in findings
        assert "residual_on_uncharged_category" not in findings
