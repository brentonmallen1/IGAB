"""Off-budget accounts don't use categories — nothing may nag about them.

Plain rows in tracking accounts (market adjustments, payroll contributions)
are net-worth movement, not unfiled spending: they must not appear in the
per-account uncategorized badge or the review inbox's uncategorized bucket.
Approval still applies everywhere, and the on-budget rules are unchanged —
including the "spending transfer missing its category" case.
"""

from datetime import date, timedelta

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
OLD = TODAY - timedelta(days=10)


async def test_offbudget_rows_never_count_as_uncategorized(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Goals")
    investing = await create_category(db_session, budget, group, "Investing")

    # Checking: one genuinely unfiled row, one categorized spending-transfer
    # leg, and one spending-transfer leg MISSING its category
    await create_transaction(db_session, budget, checking, "-25.00", OLD)
    cat_leg = await create_transaction(
        db_session, budget, checking, "-800.00", OLD, category=investing
    )
    cat_partner = await create_transaction(
        db_session, budget, brokerage, "800.00", OLD, transfer_id=cat_leg.id
    )
    cat_leg.transfer_id = cat_partner.id
    bare_leg = await create_transaction(db_session, budget, checking, "-200.00", OLD)
    bare_partner = await create_transaction(
        db_session, budget, brokerage, "200.00", OLD, transfer_id=bare_leg.id
    )
    bare_leg.transfer_id = bare_partner.id

    # Brokerage: plain uncategorized activity, one row also unapproved
    await create_transaction(db_session, budget, brokerage, "250.00", OLD)
    await create_transaction(db_session, budget, brokerage, "-35.00", OLD)
    await create_transaction(db_session, budget, brokerage, "1150.00", OLD, approved=False)
    await db_session.flush()

    # Badge: checking counts its plain row + the category-less spending
    # transfer; the brokerage never asks for categories
    assert await services.account_repo.get_uncategorized_count(checking.id) == 2
    assert await services.account_repo.get_uncategorized_count(brokerage.id) == 0

    # Review inbox: the same two the badge counted, and no more. These used to
    # disagree — the badge said 2, the inbox said 1 — because the inbox decided
    # "is this a transfer" from `transfer_id` alone and so dropped the
    # category-less spending transfer that genuinely does need filing. The
    # off-budget unapproved row still needs its approval either way.
    review = await services.transaction_repo.count_pending_review(budget.id)
    assert review["uncategorized"] == 2
    assert review["unapproved"] == 1
    assert review["uncategorized"] == await services.account_repo.get_uncategorized_count(
        checking.id
    ), "the badge and the review inbox must count the same rows"


class TestAnUnpairedTransferLegIsStillATransfer:
    """A YNAB import writes legs whose partner never arrives — the partner
    account was skipped, or the pair never matched. Those rows keep the budget's
    balances right and they are still transfers, but every "needs a category"
    rule decided transfer-ness from `transfer_id` alone, so all of them were
    counted as unfiled. One real import produced **1,117**.

    The rule now goes through CASH_FLOW_ROW, which knows a transfer by its payee
    as well as its link — while keeping the case that genuinely does need a
    category: a transfer OUT of the budget is a mortgage payment, and budgeting
    for it is the point.
    """

    async def _world(self, db_session):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking")
        savings = await create_account(db_session, budget, "Savings")
        loan = await create_account(
            db_session, budget, "Mortgage", account_type="mortgage", on_budget=False
        )
        return services, budget, checking, savings, loan

    async def _transfer_payee(self, db_session, budget, target):
        return await create_payee(
            db_session, budget, f"Transfer : {target.name}", transfer_account_id=target.id
        )

    async def test_an_unpaired_on_budget_leg_needs_nothing(self, db_session):
        """The reported bug. The partner never imported, so there is no link —
        but the payee still names an on-budget account, so it is internal
        movement and no category will ever apply."""
        services, budget, checking, savings, _ = await self._world(db_session)
        to_savings = await self._transfer_payee(db_session, budget, savings)
        await create_transaction(db_session, budget, checking, "-500.00", OLD, payee=to_savings)
        await db_session.flush()

        assert await services.account_repo.get_uncategorized_count(checking.id) == 0
        review = await services.transaction_repo.count_pending_review(budget.id)
        assert review["uncategorized"] == 0

    async def test_an_unpaired_leg_out_of_the_budget_still_needs_one(self, db_session):
        """The case the fix must not swallow: money leaving the budget is
        spending, and a mortgage payment is budgeted for. Missing link or not."""
        services, budget, checking, _, loan = await self._world(db_session)
        to_loan = await self._transfer_payee(db_session, budget, loan)
        await create_transaction(db_session, budget, checking, "-1200.00", OLD, payee=to_loan)
        await db_session.flush()

        assert await services.account_repo.get_uncategorized_count(checking.id) == 1
        review = await services.transaction_repo.count_pending_review(budget.id)
        assert review["uncategorized"] == 1

    async def test_a_linked_on_budget_transfer_is_unchanged(self, db_session):
        """The behaviour that already worked must keep working."""
        services, budget, checking, savings, _ = await self._world(db_session)
        out = await create_transaction(db_session, budget, checking, "-300.00", OLD)
        back = await create_transaction(
            db_session, budget, savings, "300.00", OLD, transfer_id=out.id
        )
        out.transfer_id = back.id
        await db_session.flush()

        assert await services.account_repo.get_uncategorized_count(checking.id) == 0
        review = await services.transaction_repo.count_pending_review(budget.id)
        assert review["uncategorized"] == 0

    async def test_an_ordinary_row_still_needs_one(self, db_session):
        """The guard against over-correcting: a plain uncategorised purchase,
        and one whose payee simply has no transfer account, both still count."""
        services, budget, checking, _, _ = await self._world(db_session)
        shop = await create_payee(db_session, budget, "Corner Shop")
        await create_transaction(db_session, budget, checking, "-12.00", OLD, payee=shop)
        await create_transaction(db_session, budget, checking, "-8.00", OLD)
        await db_session.flush()

        assert await services.account_repo.get_uncategorized_count(checking.id) == 2
        review = await services.transaction_repo.count_pending_review(budget.id)
        assert review["uncategorized"] == 2

    async def test_the_badge_and_the_transactions_filter_agree(self, db_session):
        """The user-visible symptom: pressing the badge opened a list longer
        than the badge promised, because the filter excluded neither transfers
        nor off-budget rows."""
        services, budget, checking, savings, loan = await self._world(db_session)
        to_savings = await self._transfer_payee(db_session, budget, savings)
        to_loan = await self._transfer_payee(db_session, budget, loan)
        await create_transaction(db_session, budget, checking, "-500.00", OLD, payee=to_savings)
        await create_transaction(db_session, budget, checking, "-1200.00", OLD, payee=to_loan)
        await create_transaction(db_session, budget, checking, "-12.00", OLD)
        await create_transaction(db_session, budget, savings, "9.00", OLD)
        await db_session.flush()

        review = await services.transaction_repo.count_pending_review(budget.id)
        rows, count, _ = await services.transaction_repo.list_for_budget(
            budget.id, scope="leaf", posted_only=True, uncategorized=True
        )
        assert count == len(rows) == review["uncategorized"]
        assert count == 3, "the mortgage leg and the two plain rows — not the savings leg"
