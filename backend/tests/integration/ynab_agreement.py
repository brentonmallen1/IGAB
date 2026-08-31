"""Differential testing of an import against the export it came from.

A YNAB export carries YNAB's own answers — each category's month-end
Available, every inflow and assignment — and `oracle.py` turns those into
the Ready to Assign YNAB showed. Importing the same file and asking IGAB the
same questions must give the same answers, or the difference must be the one
IGAB makes on purpose (card debt YNAB parks unfunded). `class_agreement.py`
is the same idea for the activity classifier; `invariants.py` for splits,
transfers and conservation.

The fixture under tests/fixtures/ynab is hand-computed and reviewable as
text: a checking, a savings (dormant), a credit card and a tracking
account; a categorized transfer to the tracking account, a plain transfer,
a card payment, a split, one month cash-overspent, one credit-overspent, a
card-payment reserve category, a hidden group, a starting balance, and a
future-dated row. Every figure in the Plan is YNAB's rule applied by hand.
"""

from __future__ import annotations

import io
import os
import uuid
import zipfile
from collections.abc import Collection
from datetime import date
from decimal import Decimal
from pathlib import Path

from igab.domain.money import quantize_cents
from igab.integrations.ynab.importer import YNABImporter
from igab.integrations.ynab.models import YNABBudget
from igab.integrations.ynab.oracle import ynab_rta
from igab.integrations.ynab.parity import ParityReport, check_parity
from igab.integrations.ynab.parser import YNABParser
from igab.repositories.category_repo import CategoryGroupRepository

from .factories import Services, create_budget, create_user, make_services

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "ynab"


def fixture_zip(tmp_path: Path, name: str = "Parity Budget") -> Path:
    """The two committed CSVs, zipped the way YNAB ships them."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for part in ("Register", "Plan"):
            zf.writestr(f"{name} - {part}.csv", (FIXTURES / f"{name} - {part}.csv").read_text())
    path = tmp_path / f"{name}.zip"
    path.write_bytes(buf.getvalue())
    return path


def real_export_path() -> Path | None:
    """An opt-in real export: IGAB_YNAB_EXPORT=<zip>. Personal data never
    lands in the repo; the same assertions run against it locally."""
    raw = os.environ.get("IGAB_YNAB_EXPORT")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_file() else None


async def import_export(
    db_session,
    zip_path: Path,
    *,
    account_types: dict[str, tuple[str, bool]] | None = None,
    skip_accounts: set[str] | None = None,
    close_accounts: set[str] | None = None,
) -> tuple[Services, uuid.UUID, YNABBudget]:
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    ynab_budget = YNABParser().parse_zip(zip_path)
    importer = YNABImporter(
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
        close_accounts=close_accounts,
    )
    result = await importer.import_budget(ynab_budget)
    assert result.errors == [], result.errors
    return services, budget.id, ynab_budget


async def parity(
    services: Services,
    budget_id: uuid.UUID,
    ynab_budget: YNABBudget,
    month: date,
    *,
    accounts: Collection[str] | None = None,
    credit_card_accounts: Collection[str] = (),
    tracking_accounts: Collection[str] = (),
) -> ParityReport:
    return await check_parity(
        services.budgets,
        services.category_repo,
        budget_id,
        ynab_budget,
        month,
        accounts=accounts,
        credit_card_accounts=credit_card_accounts,
        tracking_accounts=tracking_accounts,
    )


async def assert_ynab_agreement(
    services: Services,
    budget_id: uuid.UUID,
    ynab_budget: YNABBudget,
    *,
    months: Collection[date],
    accounts: Collection[str] | None = None,
    credit_card_accounts: Collection[str] = (),
    tracking_accounts: Collection[str] = (),
) -> None:
    """Every envelope's balance equals YNAB's Available in every month asked
    for, and Ready to Assign equals the oracle's expectation in each."""
    for month in months:
        report = await parity(
            services,
            budget_id,
            ynab_budget,
            month,
            accounts=accounts,
            credit_card_accounts=credit_card_accounts,
            tracking_accounts=tracking_accounts,
        )
        # First, because an export that contradicts itself makes every
        # figure below it a measurement of the file rather than of IGAB.
        assert report.consistency.self_consistent, (
            f"{month:%b %Y}: the export disagrees with itself — "
            f"{report.consistency.carryover_rows_violating}/"
            f"{report.consistency.carryover_rows_checked} plan rows break YNAB's own "
            f"running balance, {report.consistency.activity_cells_disagreeing}/"
            f"{report.consistency.activity_cells_checked} Activity cells disagree with "
            "the register shipped beside them. Envelope parity means nothing here."
        )
        assert report.categories_compared > 0, f"{month:%b %Y}: nothing to compare"
        assert report.categories_unmatched == 0, (
            f"{month:%b %Y}: {report.categories_unmatched} envelope(s) YNAB priced "
            "matched no IGAB category — a name or casing the importer stored differently"
        )
        assert report.categories_differing == 0, (
            f"{month:%b %Y}: {report.categories_differing} envelope(s) differ from YNAB "
            f"({report.categories_pending} more differ only by uncleared rows) — "
            + "; ".join(f"{d.name}: IGAB {d.igab} vs YNAB {d.ynab}" for d in report.top_differences)
        )
        assert report.igab_ready_to_assign == report.expected_ready_to_assign, (
            f"{month:%b %Y}: Ready to Assign {report.igab_ready_to_assign} vs "
            f"expected {report.expected_ready_to_assign} (YNAB {report.ynab_ready_to_assign}, "
            f"uncovered card debt {report.uncovered_card_debt})"
        )
        # Card reserves were asserted in exactly one place — `test_real_export`,
        # which skips without an export on disk and therefore never ran in CI.
        # So the one figure that disagreed with YNAB on a clean multi-year
        # import was the one figure this shared helper could not see. A card
        # reserve is inside `total_category_balance`, so every over-reserved
        # dollar leaves Ready to Assign one for one: the assertion above and
        # this one are the same money seen twice.
        assert report.cards_differing == 0, (
            f"{month:%b %Y}: {report.cards_differing}/{report.cards_compared} card "
            "reserve(s) differ from what YNAB had set aside — "
            + "; ".join(
                f"{d.name}: IGAB {d.igab} vs YNAB {d.ynab}" for d in report.card_differences
            )
        )


def oracle_for(ynab_budget: YNABBudget, month: date, **kwargs):
    return ynab_rta(ynab_budget, month, **kwargs)


def cents(value: Decimal | str) -> Decimal:
    return quantize_cents(Decimal(value))
