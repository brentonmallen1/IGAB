"""A budget built the way an anchored YNAB import leaves it, for the tests
that need one by hand: accounts marked `from_import`, history stamped
`created_via='ynab'`, anchor rows at B−1 = June, so B = July. Shared by the
late-arrival and history-mode suites so the two read one fixture."""

from datetime import date
from decimal import Decimal

from igab.db.models import ImportAnchor
from igab.domain.import_identity import YNAB_ORIGIN
from igab.services.card_payment import ensure_payment_category

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

JUN, JUL = date(2026, 6, 1), date(2026, 7, 1)
D = Decimal


class AnchoredBudget:
    """What `_imported` built, by name."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


async def build_anchored_budget(db_session, user=None) -> AnchoredBudget:
    """June is B−1. Checking took 3,000 in and spent 200 on Groceries; the Visa
    charged 100 to Dining that nobody funded. YNAB's June figures — the anchor
    — say Groceries ends June at 50 and the Visa arrives owing 100 uncovered.
    July assigns Groceries 300 and Dining 100."""
    services = make_services(db_session)
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
    for account in (checking, visa):
        account.from_import = True
    linked = await ensure_payment_category(db_session, visa)
    income = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    dining = await create_category(db_session, budget, everyday, "Dining")

    for account, amount, day, category in (
        (checking, "3000.00", date(2026, 6, 2), inflow),
        (checking, "-200.00", date(2026, 6, 10), groceries),
        (visa, "-100.00", date(2026, 6, 12), dining),
    ):
        await create_transaction(
            db_session, budget, account, amount, day, category=category, created_via=YNAB_ORIGIN
        )
    db_session.add_all(
        [
            ImportAnchor(
                budget_id=budget.id,
                month=JUN,
                kind="available",
                category_id=groceries.id,
                amount=D("50"),
            ),
            ImportAnchor(
                budget_id=budget.id,
                month=JUN,
                kind="available",
                category_id=dining.id,
                amount=D("0"),
            ),
            ImportAnchor(
                budget_id=budget.id,
                month=JUN,
                kind="uncovered",
                account_id=visa.id,
                amount=D("100"),
            ),
        ]
    )
    await db_session.flush()
    await services.budgets.set_assignment(budget.id, groceries.id, JUL, D("300"))
    await services.budgets.set_assignment(budget.id, dining.id, JUL, D("100"))
    return AnchoredBudget(
        services=services,
        budget=budget,
        checking=checking,
        visa=visa,
        linked=linked,
        groceries=groceries,
        dining=dining,
    )
