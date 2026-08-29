"""Off-budget accounts don't use categories — nothing may nag about them.

Plain rows in tracking accounts (market adjustments, payroll contributions)
are net-worth movement, not unfiled spending: they must not appear in the
per-account uncategorized badge or the review inbox's uncategorized bucket.
Approval still applies everywhere, and the on-budget rules are unchanged —
including the "spending transfer missing its category" case.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.api.v1.schemas.transaction import TransactionResponse
from igab.services.transaction_service import SplitSpec, TransactionUpdate
from igab.services.transaction_service import TransactionCreate as SvcTxnCreate

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


class TestTheServedFlagIsTheOnlyRule:
    """`needs_category` on the API row *is* the rule, and the only copy of it.

    The register used to re-derive it in TypeScript from `transfer_id`, and the
    copies drifted: the badge counted 3 while the list below it drew 930 rows
    as unfiled. Fixing one site never fixed the other, because nothing tied
    them together. These tests are that tie — they assert the value the client
    is handed agrees, row for row, with the numbers the counters produce.
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
        # An unpaired leg to an on-budget account (needs nothing), an unpaired
        # leg out of the budget (a mortgage payment — still needs one), and a
        # plain purchase (needs one).
        to_savings = await create_payee(
            db_session, budget, "Transfer : Savings", transfer_account_id=savings.id
        )
        to_loan = await create_payee(
            db_session, budget, "Transfer : Mortgage", transfer_account_id=loan.id
        )
        await create_transaction(db_session, budget, checking, "-500.00", OLD, payee=to_savings)
        await create_transaction(db_session, budget, checking, "-1200.00", OLD, payee=to_loan)
        await create_transaction(db_session, budget, checking, "-12.00", OLD)
        await db_session.flush()
        return services, budget, checking

    async def test_the_flag_matches_the_account_badge_row_for_row(self, db_session):
        services, _, checking = await self._world(db_session)

        rows = await services.transaction_repo.get_for_account(checking.id)
        flagged = [t for t in rows if t.needs_category]

        assert len(flagged) == 2, "the mortgage leg and the plain row, not the savings leg"
        assert len(flagged) == await services.account_repo.get_uncategorized_count(checking.id)

    async def test_the_account_register_filter_agrees_with_its_badge(self, db_session):
        """The sixth site. Every other copy of the rule moved to NEEDS_CATEGORY;
        this filter kept the old two-condition spelling, so the account
        register's Uncategorized filter still listed unpaired transfer legs
        under a badge that had stopped counting them."""
        services, _, checking = await self._world(db_session)

        filtered = await services.transaction_repo.get_for_account(checking.id, uncategorized=True)

        assert len(filtered) == await services.account_repo.get_uncategorized_count(checking.id)
        assert all(t.needs_category for t in filtered)

    async def test_every_listing_path_carries_the_flag(self, db_session):
        """A path that forgets `with_needs_category` leaves the attribute None,
        which TransactionResponse rejects. Assert it is a real bool here so the
        failure lands on this test rather than on a user's register."""
        services, budget, checking = await self._world(db_session)

        by_account = await services.transaction_repo.get_for_account(checking.id)
        by_budget, _, _ = await services.transaction_repo.list_for_budget(budget.id, scope="leaf")
        one = await services.transaction_repo.get_or_raise(by_account[0].id)
        plain = next(t for t in by_account if t.payee_id is None and not t.is_split)
        await services.transactions.convert_to_split(
            budget.id, plain.id, [SplitSpec(amount=plain.amount)]
        )
        lines = await services.transaction_repo.get_splits(plain.id)

        for row in [*by_account, *by_budget, one, *lines]:
            assert isinstance(row.needs_category, bool), f"{row.id} came back unpopulated"

    async def test_the_flag_survives_a_service_update(self, db_session):
        """The sharp edge of computing this in the query: `Session.refresh()`
        takes no loader options, so it reloads the columns and silently drops
        the value. `_record_txn` refreshes before returning on every mutating
        call, so a plain refresh would hand the endpoint None — and only on
        create/update responses, never on a listing. Goes through the service
        for that reason; calling the repo directly would not exercise it."""
        services, budget, checking = await self._world(db_session)
        rows = await services.transaction_repo.get_for_account(checking.id)
        plain = next(t for t in rows if t.needs_category and t.payee_id is None)

        updated = await services.transactions.update(
            budget.id, plain.id, TransactionUpdate(memo="touched")
        )

        assert updated.needs_category is True

    async def test_every_mutating_path_returns_a_serializable_row(self, db_session):
        """The blunt guard. `TransactionResponse` requires `needs_category`, so
        any service path that hands back a row without it 500s the endpoint —
        and only that endpoint, which is how such a gap reaches a user rather
        than CI. Exercised here rather than trusted, because merge in
        particular has no test at the API layer.
        """
        services, budget, checking = await self._world(db_session)
        rows = await services.transaction_repo.get_for_account(checking.id)
        plain = next(t for t in rows if t.needs_category and t.payee_id is None)

        created = await services.transactions.create(
            budget.id,
            SvcTxnCreate(account_id=checking.id, date=OLD, amount=Decimal("-3.00")),
        )
        updated = await services.transactions.update(
            budget.id, plain.id, TransactionUpdate(memo="touched")
        )
        approved = await services.transactions.approve(plain.id, budget.id)
        split = await services.transactions.convert_to_split(
            budget.id, plain.id, [SplitSpec(amount=Decimal("-12.00"))]
        )
        [line] = await services.transaction_repo.get_splits(split.id)
        replaced = await services.transactions.replace_splits(
            budget.id,
            split.id,
            [SplitSpec(amount=Decimal("-5.00"), id=line.id), SplitSpec(amount=Decimal("-7.00"))],
        )
        merge_a = await create_transaction(db_session, budget, checking, "-40.00", OLD)
        merge_b = await create_transaction(db_session, budget, checking, "-40.00", OLD)
        await db_session.flush()
        survivor = await services.transactions.merge(budget.id, [merge_a.id, merge_b.id])
        adjustment = await services.reconciliation.create_adjustment(checking.id, Decimal("5.00"))

        for label, txn in [
            ("create", created),
            ("update", updated),
            ("approve", approved),
            ("convert_to_split", split),
            *[("replace_splits", line) for line in replaced],
            ("merge", survivor),
            ("reconcile adjustment", adjustment),
        ]:
            assert isinstance(TransactionResponse.model_validate(txn).needs_category, bool), (
                f"{label} returned a row the API cannot serialize"
            )

    async def test_a_pending_row_is_filterable_but_is_not_workload(self, db_session):
        """The one place the badge and the Uncategorized filter are *meant* to
        differ, so it is written down rather than left to look like drift.

        A pending uncategorized row matches an Uncategorized search — it is
        uncategorized, and hiding it from a filter makes the filter lie. It is
        not counted by the badge, because the badge is a count of work the user
        can act on and a pending amount is provisional. The gap between the two
        is exactly the pending uncategorized rows and nothing else.
        """
        services, budget, checking = await self._world(db_session)
        await create_transaction(db_session, budget, checking, "-30.00", TODAY, cleared="pending")
        await db_session.flush()

        review = await services.transaction_repo.count_pending_review(budget.id)
        _, filtered, _ = await services.transaction_repo.list_for_budget(
            budget.id, scope="leaf", uncategorized=True
        )
        _, posted_only, _ = await services.transaction_repo.list_for_budget(
            budget.id, scope="leaf", uncategorized=True, posted_only=True
        )

        assert filtered == 3, "the filter shows the pending row alongside the two posted ones"
        assert review["uncategorized"] == 2, "the badge counts only what can be acted on"
        assert posted_only == review["uncategorized"], "and they agree once pending is excluded"


class TestACategoryMayNotLandOnATrackingAccount:
    """The write half of the rule (domain/transfers.py, general clause).

    The read half — the activity sums exclude off-budget rows — is pinned in
    test_tba_terms.py. Here: every service path that could put a category on
    a tracking row refuses or declines, and the hygiene repair cleans up the
    rows that predate the rule.
    """

    async def _setup(self, db_session):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking")
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        return services, budget, checking, brokerage, groceries

    async def test_create_with_a_category_is_refused(self, db_session):
        import pytest

        from igab.domain.exceptions import InvariantViolation

        services, budget, _, brokerage, groceries = await self._setup(db_session)
        with pytest.raises(InvariantViolation, match="tracking account"):
            await services.transactions.create(
                budget.id,
                SvcTxnCreate(
                    account_id=brokerage.id,
                    date=TODAY,
                    amount=Decimal("-50.00"),
                    category_id=groceries.id,
                ),
            )

    async def test_update_cannot_add_one_either(self, db_session):
        import pytest

        from igab.domain.exceptions import InvariantViolation

        services, budget, _, brokerage, groceries = await self._setup(db_session)
        row = await create_transaction(db_session, budget, brokerage, "-50.00", OLD)
        with pytest.raises(InvariantViolation, match="tracking account"):
            await services.transactions.update(
                budget.id, row.id, TransactionUpdate(category_id=groceries.id)
            )

    async def test_split_lines_are_covered_too(self, db_session):
        import pytest

        from igab.domain.exceptions import InvariantViolation

        services, budget, _, brokerage, groceries = await self._setup(db_session)
        parent = await create_transaction(
            db_session, budget, brokerage, "-100.00", OLD, is_split=True
        )
        with pytest.raises(InvariantViolation, match="tracking account"):
            await services.transactions.replace_splits(
                budget.id,
                parent.id,
                [
                    SplitSpec(amount=Decimal("-60.00"), category_id=groceries.id),
                    SplitSpec(amount=Decimal("-40.00"), category_id=None),
                ],
            )

    async def test_auto_categorize_declines_rather_than_errors(self, db_session):
        """A synced tracking row must not inherit the payee's checking-side
        category — the recurring creator of these rows in the wild — and a
        skip is the right shape for a background sync, not a 422."""
        services, budget, checking, brokerage, groceries = await self._setup(db_session)
        payee = await create_payee(db_session, budget, "Vanguard")
        await create_transaction(
            db_session, budget, checking, "-200.00", OLD, category=groceries, payee=payee
        )
        await db_session.flush()

        row = await services.transactions.create(
            budget.id,
            SvcTxnCreate(
                account_id=brokerage.id,
                date=TODAY,
                amount=Decimal("-200.00"),
                payee_id=payee.id,
            ),
        )
        assert row.category_id is None, "payee memory must not reach a tracking row"

        # Same payee on checking still auto-categorizes — the rule is about
        # the account, not the payee.
        on_budget_row = await services.transactions.create(
            budget.id,
            SvcTxnCreate(
                account_id=checking.id,
                date=TODAY,
                amount=Decimal("-200.00"),
                payee_id=payee.id,
            ),
        )
        assert on_budget_row.category_id == groceries.id

    async def test_hygiene_finds_and_repair_strips_and_undo_restores(self, db_session):
        from sqlalchemy import select

        from igab.db.models import ChangeLog
        from igab.services.account_hygiene import AccountHygieneService
        from igab.services.undo_service import UndoService

        services, budget, _, brokerage, groceries = await self._setup(db_session)
        # Pre-rule rows, written the way an import writes them.
        bad1 = await create_transaction(
            db_session, budget, brokerage, "-450.00", OLD, category=groceries
        )
        bad2 = await create_transaction(
            db_session, budget, brokerage, "-50.00", OLD, category=groceries
        )
        await db_session.flush()

        report = await AccountHygieneService(db_session).run(budget.id)
        finding = next(f for f in report.findings if f.kind == "categorized_tracking_rows")
        assert finding.transaction_count == 2

        result = await services.transactions.repair_tracking_categories(budget.id)
        assert result == {"stripped": 2}
        await db_session.flush()
        db_session.expunge_all()
        assert (await services.transaction_repo.get_or_raise(bad1.id)).category_id is None
        assert (await services.transaction_repo.get_or_raise(bad2.id)).category_id is None

        # Clean now: the finding is gone and a second run strips nothing.
        report = await AccountHygieneService(db_session).run(budget.id)
        assert all(f.kind != "categorized_tracking_rows" for f in report.findings)
        assert await services.transactions.repair_tracking_categories(budget.id) == {
            "stripped": 0
        }

        # One batch, one undo — both categories come back.
        changes = list(
            (
                await db_session.execute(
                    select(ChangeLog)
                    .where(ChangeLog.budget_id == budget.id, ChangeLog.entity_type == "transaction")
                    .order_by(ChangeLog.seq)
                )
            )
            .scalars()
            .all()
        )
        assert len({c.batch_id for c in changes}) == 1
        await UndoService(db_session).undo_batch(budget.id, changes[0].batch_id)
        db_session.expunge_all()
        assert (await services.transaction_repo.get_or_raise(bad1.id)).category_id == groceries.id
        assert (await services.transaction_repo.get_or_raise(bad2.id)).category_id == groceries.id


class TestHistoryBeforeAnAccountJoinedTheBudget:
    """Rows older than `Account.budget_start_date` are opening position.

    A synced account arrives with whatever history the bank kept. A card
    carried in on the 29th came with three months of it, and every guess made
    against that history landed in an envelope funded for one month — so the
    grid filled with red for money spent before the budget knew the card
    existed. That debt is not overspending anyone can act on: it belongs in
    the card's Uncovered, retired by assigning to the card.

    So those rows are left uncategorized deliberately, and this is what stops
    the app asking about them forever. Asserted through the served flag, the
    account badge and the register filter together, because all three read the
    one expression (`NEEDS_CATEGORY`) and the whole point of that consolidation
    was that they can never again answer differently.
    """

    async def _world(self, db_session, start=None):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        card = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card"
        )
        card.budget_start_date = start
        # One row on each side of the line, both plain purchases with no
        # category — identical in every respect except their date.
        await create_transaction(db_session, budget, card, "-40.00", TODAY - timedelta(days=30))
        await create_transaction(db_session, budget, card, "-25.00", TODAY - timedelta(days=2))
        await db_session.flush()
        return services, card

    async def test_with_no_start_date_both_rows_still_need_a_category(self, db_session):
        """Every account until someone answers the question. The migration adds
        a nullable column and moves no number anywhere."""
        services, card = await self._world(db_session, start=None)

        rows = await services.transaction_repo.get_for_account(card.id)
        assert [t.needs_category for t in rows] == [True, True]
        assert await services.account_repo.get_uncategorized_count(card.id) == 2

    async def test_a_row_before_the_start_date_is_not_unfiled_work(self, db_session):
        services, card = await self._world(db_session, start=TODAY - timedelta(days=7))

        rows = await services.transaction_repo.get_for_account(card.id)
        flagged = [t for t in rows if t.needs_category]

        assert len(flagged) == 1, "only the row dated after the account joined"
        assert flagged[0].amount == Decimal("-25.00")
        # The badge and the register filter read the same expression, so they
        # cannot disagree with the flag above or with each other.
        assert await services.account_repo.get_uncategorized_count(card.id) == 1
        filtered = await services.transaction_repo.get_for_account(card.id, uncategorized=True)
        assert [t.amount for t in filtered] == [Decimal("-25.00")]

    async def test_a_row_on_the_start_date_itself_counts(self, db_session):
        """The boundary is inclusive: the day you joined is a day you budgeted."""
        services, card = await self._world(db_session, start=TODAY - timedelta(days=30))

        assert await services.account_repo.get_uncategorized_count(card.id) == 2

    async def test_one_account_start_date_does_not_reach_another(self, db_session):
        """The predicate is correlated to the row's own account. Written as a
        bare column comparison it would have cross-joined every account in the
        budget and multiplied the badge by their number."""
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
        card.budget_start_date = TODAY
        checking = await create_account(db_session, budget, "Checking")
        await create_transaction(db_session, budget, card, "-40.00", TODAY - timedelta(days=30))
        await create_transaction(db_session, budget, checking, "-40.00", TODAY - timedelta(days=30))
        await db_session.flush()

        assert await services.account_repo.get_uncategorized_count(card.id) == 0
        assert await services.account_repo.get_uncategorized_count(checking.id) == 1

