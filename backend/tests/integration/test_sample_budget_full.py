"""Full-tier sample budget: the complex-household superset.

Calibrated to a real multi-year YNAB export (notes/YNAB-schema-and-
relationships.md): institution-clustered accounts, 30 months of history,
sinking-fund naming, hidden categories with real history, a managed mortgage
with origination data, a deferred-interest promo, and register texture
(transfer-leg and split-line ratios, mostly-reconciled history). The starter
tier's curated invariants — TBA on target, exactly one overspend — must hold
here too, because the starter is a strict subset of this data.
"""

from datetime import date
from decimal import Decimal

from igab.db.models import Transaction
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
from igab.sample_budget.data import SAMPLE_BUDGET
from igab.sample_budget.generator import SampleBudgetGenerator
from igab.services.budget_service import BudgetService
from igab.services.integrity_service import IntegrityService
from sqlalchemy import select

from .factories import create_budget, create_user

ANCHOR = date(2026, 7, 25)


async def generate_full(session, budget) -> "SampleBudgetGenerator":
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
        tier="full",
    )
    generator.result = await generator.generate(anchor=ANCHOR)  # type: ignore[attr-defined]
    return generator


async def _transactions(session, budget_id) -> list[Transaction]:
    result = await session.execute(
        select(Transaction).where(Transaction.budget_id == budget_id)
    )
    return list(result.scalars().all())


def test_starter_is_a_strict_subset_of_full():
    """Pure spec check: everything tagged for the starter is in the full tier
    too — the tiers can never drift apart."""
    for field in ("accounts", "groups", "payees", "monthly", "weekly", "one_offs",
                  "transfers", "scheduled", "liabilities"):
        for element in getattr(SAMPLE_BUDGET, field):
            if "starter" in element.tiers:
                assert "full" in element.tiers, f"{field}: {element} is starter-only"


async def test_full_tier_shape_and_texture(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    gen = await generate_full(db_session, budget)
    counts = gen.result

    accounts = await AccountRepository(db_session).get_all(budget.id, include_closed=True)
    assert counts.accounts == 16
    types = {a.account_type for a in accounts}
    assert {"checking", "savings", "cash", "credit_card", "loan", "investment",
            "other_asset"} <= types
    assert sum(1 for a in accounts if a.is_closed) == 1
    assert sum(1 for a in accounts if not a.on_budget) >= 8
    # Every account has a classification (the sidebar/net-worth contract)
    assert all(a.classification in ("asset", "liability") for a in accounts)

    txns = await _transactions(db_session, budget.id)
    assert counts.transactions == len(txns)
    assert 1500 <= counts.transactions <= 6000

    # 30 months of history: at least one row in each of the trailing 30 months
    month_keys = {(t.date.year, t.date.month) for t in txns}
    y, m = ANCHOR.year, ANCHOR.month
    for _ in range(30):
        assert (y, m) in month_keys, f"no transactions in {y}-{m:02d}"
        m -= 1
        if m == 0:
            y, m = y - 1, 12

    # Register texture, calibrated to the real export (~10% transfer legs,
    # ~9% split lines, overwhelmingly reconciled history). Transfers run a
    # little hotter than a typical real register on purpose — spending
    # transfers to off-budget accounts are a feature worth showcasing.
    transfer_legs = sum(1 for t in txns if t.transfer_id is not None)
    assert 0.08 <= transfer_legs / len(txns) <= 0.22
    split_lines = sum(1 for t in txns if t.parent_transaction_id is not None)
    assert 0.05 <= split_lines / len(txns) <= 0.14
    reconciled = sum(1 for t in txns if t.cleared == "reconciled")
    assert reconciled / len(txns) >= 0.75

    # Hidden categories exist and some carry real history
    categories = await CategoryRepository(db_session).get_all(budget.id, include_hidden=True)
    hidden = [c for c in categories if c.is_hidden]
    assert len(hidden) >= 5
    hidden_ids = {c.id for c in hidden}
    assert any(t.category_id in hidden_ids for t in txns)

    # Sinking-fund naming conventions survive into the data
    names = {c.name for c in categories}
    assert any("/12" in n for n in names)
    assert any("~" in n for n in names)

    # Multiple accounts reconciled, not just the primary checking
    assert counts.reconciliations >= 3


async def test_full_tier_liabilities(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await generate_full(db_session, budget)

    liability_repo = LiabilityRepository(db_session)
    liabilities = {item.name: item for item in await liability_repo.get_all(budget.id)}
    assert len(liabilities) == 4

    mortgage = liabilities["Maple St Mortgage"]
    assert mortgage.linked_account_id is not None
    assert mortgage.origination_date is not None
    assert mortgage.original_principal == Decimal("300000.00")
    assert mortgage.term_months == 360

    promo = liabilities["Furniture – 0% promo"]
    assert promo.promo_end_date is not None
    assert promo.promo_end_date > ANCHOR
    assert promo.promo_deferred_interest is True


async def test_full_tier_keeps_starter_invariants(db_session):
    """More data, same promises: TBA lands exactly on target, exactly one
    intentional overspend, every financial invariant green."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await generate_full(db_session, budget)

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

    categories = await CategoryRepository(db_session).get_all(budget.id, include_hidden=True)
    names = {c.id: c.name for c in categories}
    overspent = [names[b.category_id] for b in summary.category_balances if b.available < 0]
    assert overspent == ["Dining Out"]

    report = await IntegrityService(db_session).run(budget.id)
    assert report.all_passed, [(c.name, c.details) for c in report.checks if not c.passed]


async def test_full_tier_is_deterministic(db_session):
    user = await create_user(db_session)
    budget_a = await create_budget(db_session, user)
    budget_b = await create_budget(db_session, user)
    await generate_full(db_session, budget_a)
    await generate_full(db_session, budget_b)

    async def signature(budget_id) -> list[tuple]:
        txns = await _transactions(db_session, budget_id)
        payees = await PayeeRepository(db_session).get_all(budget_id)
        payee_names = {p.id: p.name for p in payees}
        return sorted(
            (t.date, t.amount, payee_names.get(t.payee_id), t.cleared, t.is_split)
            for t in txns
        )

    assert await signature(budget_a.id) == await signature(budget_b.id)


async def test_endpoint_accepts_the_tier(api_client):
    response = await api_client.post(
        "/api/v1/budgets/create-sample", json={"name": "Full Tour", "tier": "full"}
    )
    assert response.status_code == 201, response.text
    counts = response.json()["counts"]
    assert counts["accounts"] == 16
    assert counts["transactions"] > 1500
    assert counts["liabilities"] == 4
