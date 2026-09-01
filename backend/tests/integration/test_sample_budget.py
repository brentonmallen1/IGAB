"""Sample budget generation: entity coverage, financial shape, and integrity.

The generator promises a demo-ready budget for ANY anchor date: TBA exactly
on target, exactly one intentionally overspent category, and every invariant
green. These tests pin those promises with a fixed anchor plus the endpoint
flow with today's date.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Budget, BudgetMember, ScheduledTransaction, Transaction
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.repositories.target_repo import TargetRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.sample_budget.generator import SampleBudgetGenerator
from igab.services.budget_service import BudgetService
from igab.services.integrity_service import IntegrityService

from .factories import create_budget, create_user

ANCHOR = date(2026, 7, 25)


async def generate_sample(session, budget) -> "SampleBudgetGenerator":
    await seed_system_tags(session, budget.id)
    generator = SampleBudgetGenerator(
        session,
        budget.id,
        account_repo=AccountRepository(session),
        category_group_repo=CategoryGroupRepository(session),
        category_repo=CategoryRepository(session),
        payee_repo=PayeeRepository(session),
        transaction_repo=TransactionRepository(session),
        assignment_repo=BudgetAssignmentRepository(session),
        tag_repo=TagRepository(session),
        target_repo=TargetRepository(session),
        scheduled_repo=ScheduledTransactionRepository(session),
        reconciliation_repo=ReconciliationRepository(session),
        liability_repo=LiabilityRepository(session),
    )
    generator.result = await generator.generate(anchor=ANCHOR)  # type: ignore[attr-defined]
    return generator


async def _transactions(session, budget_id) -> list[Transaction]:
    result = await session.execute(select(Transaction).where(Transaction.budget_id == budget_id))
    return list(result.scalars().all())


async def test_generation_covers_every_entity_kind(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    gen = await generate_sample(db_session, budget)
    counts = gen.result

    accounts = await AccountRepository(db_session).get_all(budget.id)
    types = {a.account_type for a in accounts}
    assert counts.accounts == 5
    assert {"checking", "savings", "credit_card", "auto_loan", "investment"} <= types

    txns = await _transactions(db_session, budget.id)
    assert counts.transactions == len(txns)
    assert counts.transactions < 1000

    # Split parent with children that sum to it
    parents = [t for t in txns if t.is_split]
    assert parents
    parent = parents[0]
    children = [t for t in txns if t.parent_transaction_id == parent.id]
    assert len(children) >= 2
    assert sum((c.amount for c in children), Decimal("0")) == parent.amount

    # At least one zero-sum mutually linked transfer pair
    by_id = {t.id: t for t in txns}
    linked = [t for t in txns if t.transfer_id is not None]
    assert linked
    leg = linked[0]
    partner = by_id[leg.transfer_id]
    assert partner.transfer_id == leg.id
    assert leg.amount == -partner.amount

    # Targets: three distinct types
    categories = await CategoryRepository(db_session).get_all(budget.id, include_archived=True)
    targets = await TargetRepository(db_session).get_by_category_ids([c.id for c in categories])
    assert {t.target_type for t in targets} >= {
        "needed_for_spending",
        "savings_balance",
        "monthly_funding",
    }

    # Scheduled transactions, incl. a transfer and a twice-monthly paycheck
    scheduled = await ScheduledTransactionRepository(db_session).get_all(budget.id)
    assert len(scheduled) == 5
    assert any(s.transfer_account_id is not None for s in scheduled)
    assert any(s.frequency == "twice_monthly" and s.second_day_of_month == 15 for s in scheduled)

    # Reconciliation snapshot matches the sum of reconciled checking rows
    checking = next(a for a in accounts if a.account_type == "checking")
    snaps = await ReconciliationRepository(db_session).get_history(checking.id)
    assert len(snaps) == 1
    reconciled_sum = sum(
        (
            t.amount
            for t in txns
            if t.account_id == checking.id
            and t.cleared == "reconciled"
            and t.parent_transaction_id is None
        ),
        Decimal("0"),
    )
    assert snaps[0].statement_balance == reconciled_sum
    assert checking.last_reconciled_balance == reconciled_sum

    # Tag links on categories and payees; Visa Payment linked to the card
    tag_repo = TagRepository(db_session)
    cat_tags = await tag_repo.get_tags_for_categories([c.id for c in categories])
    assert any(tags for tags in cat_tags.values())
    payees = await PayeeRepository(db_session).get_all(budget.id)
    payee_tags = await tag_repo.get_tags_for_payees([p.id for p in payees])
    assert any(tags for tags in payee_tags.values())
    visa_payment = next(c for c in categories if c.name == "Visa Payment")
    visa_account = next(a for a in accounts if a.account_type == "credit_card")
    assert visa_payment.linked_account_id == visa_account.id

    # Liabilities: one managed (linked to Car Loan account), one unmanaged (with
    # snapshots), plus the Visa's companion — every liability-classified account
    # gets one, credit cards included, so the loan features are never a record
    # the user has to know to create.
    liability_repo = LiabilityRepository(db_session)
    liabilities = await liability_repo.get_all(budget.id)
    assert counts.liabilities == 3
    assert len(liabilities) == 3
    for account in accounts:
        if account.classification == "liability":
            assert await liability_repo.get_by_linked_account(account.id) is not None, account.name

    car_loan_acct = next(a for a in accounts if a.name == "Car Loan")
    managed = next(li for li in liabilities if li.linked_account_id == car_loan_acct.id)
    assert managed.name == "Car Loan"
    # Nothing stored: it reads "Auto Loan" off the account, which is now typed
    # specifically enough to say so.
    assert managed.liability_type is None
    assert car_loan_acct.account_type == "auto_loan"
    # The specced terms survive: the companion pass fills gaps, never overwrites
    assert managed.interest_rate == Decimal("6.25")

    visa = next(li for li in liabilities if li.linked_account_id == visa_account.id)
    assert visa.interest_rate is None and visa.minimum_payment is None
    # Nothing stored: a managed liability reads its kind off its account, so a
    # companion storing one would be the duplicate field this model removed.
    assert visa.liability_type is None

    unmanaged = next(li for li in liabilities if li.linked_account_id is None)
    assert unmanaged.name == "Dental Payment Plan"
    assert unmanaged.liability_type == "medical"
    assert unmanaged.manual_balance == Decimal("855.00")
    snapshots = await liability_repo.get_snapshots(unmanaged.id)
    assert len(snapshots) == 3


async def test_dates_span_the_window_and_scheduled_are_future(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await generate_sample(db_session, budget)

    txns = await _transactions(db_session, budget.id)
    window_start = ANCHOR - timedelta(days=398)  # 13 months, with slack
    assert all(window_start <= t.date <= ANCHOR for t in txns)

    # At least one transaction in each of the trailing 12 months
    month_keys = {(t.date.year, t.date.month) for t in txns}
    y, m = ANCHOR.year, ANCHOR.month
    for _ in range(12):
        assert (y, m) in month_keys
        m -= 1
        if m == 0:
            y, m = y - 1, 12

    result = await db_session.execute(
        select(ScheduledTransaction).where(ScheduledTransaction.budget_id == budget.id)
    )
    for sched in result.scalars():
        assert sched.next_occurrence_date > ANCHOR


async def test_budget_summary_hits_target_with_one_overspend(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await generate_sample(db_session, budget)

    service = BudgetService(
        AccountRepository(db_session),
        CategoryRepository(db_session),
        CategoryGroupRepository(db_session),
        BudgetAssignmentRepository(db_session),
        TransactionRepository(db_session),
    )
    summary = await service.get_budget_summary(budget.id, ANCHOR.replace(day=1))
    assert summary.to_be_assigned == Decimal("150.00")
    assert summary.total_overspent == Decimal("45.00")

    categories = await CategoryRepository(db_session).get_all(budget.id, include_archived=True)
    names = {c.id: c.name for c in categories}
    overspent = [
        names[b.category_id]
        for b in summary.category_balances
        if b.available < 0 and not b.is_card_payment
    ]
    assert overspent == ["Dining Out"]
    # The demo's card is healthy: every charge came out of a funded envelope,
    # so the cash it gave up is reserved and waiting, and the card owes an
    # ordinary statement balance with nothing Uncovered behind it.
    #
    # This used to assert the opposite — the Visa was paid $600/month against
    # roughly $315 of spending, so its envelope ran NEGATIVE and "Try a sample
    # budget" opened on a card holding thousands of the user's money. That is
    # a real state with a name (`credit-balance` in card_scenarios.py) and it
    # belongs to a card that demonstrates it, not to the first row a new user
    # ever sees.
    card_envelopes = [b for b in summary.category_balances if b.is_card_payment]
    assert card_envelopes and all(b.available > 0 for b in card_envelopes)
    assert all(c.card_credit == Decimal("0") for c in summary.cards)
    # And Uncovered decomposes exactly: the 420 the card arrived with, plus
    # the 45 of this month's deliberate overspend, which was swiped on the
    # card and so rides there instead of charging Ready to Assign. Nothing
    # else — every other charge came out of a funded envelope and reserved its
    # own cash. That sum is the whole credit model in one assertion.
    assert [c.uncovered for c in summary.cards] == [Decimal("420.00") + summary.total_overspent]


async def test_integrity_all_green(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await generate_sample(db_session, budget)

    report = await IntegrityService(db_session).run(budget.id)
    assert report.all_passed, [(c.name, c.details) for c in report.checks if not c.passed]


async def test_same_anchor_runs_are_identical(db_session):
    user = await create_user(db_session)
    budget_a = await create_budget(db_session, user)
    budget_b = await create_budget(db_session, user)
    await generate_sample(db_session, budget_a)
    await generate_sample(db_session, budget_b)

    async def signature(budget_id) -> list[tuple]:
        txns = await _transactions(db_session, budget_id)
        payees = await PayeeRepository(db_session).get_all(budget_id)
        payee_names = {p.id: p.name for p in payees}
        return sorted(
            (t.date, t.amount, payee_names.get(t.payee_id), t.cleared, t.is_split) for t in txns
        )

    assert await signature(budget_a.id) == await signature(budget_b.id)


async def test_endpoint_creates_and_auto_suffixes(api_client):
    first = await api_client.post("/api/v1/budgets/create-sample", json={})
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["budget"]["name"] == "Sample Budget"
    assert body["counts"]["transactions"] > 0
    assert body["counts"]["scheduled"] == 5
    assert body["counts"]["liabilities"] == 3

    second = await api_client.post("/api/v1/budgets/create-sample", json={})
    assert second.status_code == 201
    assert second.json()["budget"]["name"] == "Sample Budget 2"


async def test_endpoint_result_is_demo_ready_today(api_client, db_session):
    """The endpoint path (anchor = today) also lands on the exact targets."""
    response = await api_client.post("/api/v1/budgets/create-sample", json={"name": "Tour"})
    assert response.status_code == 201
    budget_id = uuid.UUID(response.json()["budget"]["id"])

    from igab.utils.clock import today_utc

    service = BudgetService(
        AccountRepository(db_session),
        CategoryRepository(db_session),
        CategoryGroupRepository(db_session),
        BudgetAssignmentRepository(db_session),
        TransactionRepository(db_session),
    )
    summary = await service.get_budget_summary(budget_id, today_utc().replace(day=1))
    assert summary.to_be_assigned == Decimal("150.00")
    assert summary.total_overspent == Decimal("45.00")

    report = await IntegrityService(db_session).run(budget_id)
    assert report.all_passed

    result = await db_session.execute(select(Budget).where(Budget.id == budget_id))
    assert result.scalar_one().name == "Tour"


async def test_cli_helper_grants_owner_membership(db_session):
    """`just sample-budget` must leave the budget reachable by its owner.

    Authorization resolves through budget_members only, so a budget created
    without an owner row is invisible to the very user it was generated for.
    """
    from igab.sample_budget.__main__ import create_sample_budget_for_user

    user = await create_user(db_session)
    await create_sample_budget_for_user(user, "CLI Demo", db_session)

    # The membership-scoped listing is exactly what the budget selector runs.
    result = await db_session.execute(
        select(Budget)
        .join(BudgetMember, BudgetMember.budget_id == Budget.id)
        .where(BudgetMember.user_id == user.id)
    )
    budgets = result.scalars().all()
    assert [b.name for b in budgets] == ["CLI Demo"]

    role = await db_session.execute(
        select(BudgetMember.role).where(
            BudgetMember.budget_id == budgets[0].id,
            BudgetMember.user_id == user.id,
        )
    )
    assert role.scalar_one() == "owner"
