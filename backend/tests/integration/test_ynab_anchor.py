"""Full-position anchoring of a YNAB import, end to end.

An imported budget's walks start from YNAB's own displayed position at the
boundary (db.models.ImportAnchor) instead of re-deriving history. These pin
the writer (the importer), the seeds' round-trip, the parity-by-construction
claim — including on a file that contradicts itself — and the unanchored
fallbacks. Fixture figures are hand-computed from the committed CSVs: the
plan's last month is Aug 2026, so B = Aug and the openings are July's.
"""

import io
import zipfile
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import ImportAnchor
from igab.services.account_hygiene import AccountHygieneService

from .ynab_agreement import FIXTURES, fixture_zip, import_export, parity

JUL, AUG = date(2026, 7, 1), date(2026, 8, 1)
TYPES = {
    "Checking": ("checking", True),
    "Savings": ("savings", True),
    "Visa": ("credit_card", True),
    "Brokerage": ("investment", False),
}
D = Decimal


async def _imported(db_session, tmp_path, **kwargs):
    return await import_export(db_session, fixture_zip(tmp_path), account_types=TYPES, **kwargs)


async def _anchor_rows(db_session, budget_id):
    rows = (
        (await db_session.execute(select(ImportAnchor).where(ImportAnchor.budget_id == budget_id)))
        .scalars()
        .all()
    )
    return rows


async def test_the_import_writes_the_anchor_from_julys_own_figures(db_session, tmp_path):
    """Every category's July Available lands as a row (zeros included — the
    rows are how the walks know the budget is anchored), the Visa's uncovered
    50 (owes 50, CCP 0) lands on the card, and every row carries B−1."""
    services, budget_id, ynab_budget = await _imported(db_session, tmp_path)
    rows = await _anchor_rows(db_session, budget_id)
    assert rows, "the import wrote no anchor"
    assert {r.month for r in rows} == {JUL}

    by_kind: dict[str, list[ImportAnchor]] = {}
    for r in rows:
        by_kind.setdefault(r.kind, []).append(r)
    # Seven spendable categories in the July plan (the CCP row seeds the
    # card, not a category; the Inflow group is system and holds no money).
    assert len(by_kind["available"]) == 7
    amounts = sorted(r.amount for r in by_kind["available"])
    # Utilities ended July 50 overspent — the raw negative is the opening,
    # floored at the boundary exactly as any month end would be.
    assert amounts[0] == D("-50")
    assert all(a == 0 for a in amounts[1:])
    assert "reserve" not in by_kind  # July CCP Available is zero — skipped
    (uncovered,) = by_kind["uncovered"]
    assert uncovered.amount == D("50")


async def test_the_summary_serves_the_anchor_month_and_the_opening_leg(db_session, tmp_path):
    services, budget_id, _ = await _imported(db_session, tmp_path)
    summary = await services.budgets.get_budget_summary(budget_id, AUG)
    assert summary.anchor_month == AUG
    visa = next(c for c in summary.cards if c.name == "Visa")
    assert visa.opening == D("0")
    assert visa.uncovered == D("50")
    assert visa.reserve_discrepancy == D("0")


async def test_an_incoherent_export_still_anchors_and_still_matches(db_session, tmp_path):
    """The feature's whole point: a file whose month-by-month history
    contradicts itself still hands over a displayed position, and the
    anchored budget matches that position by construction — the cash-form
    parity holds where the history-form could not."""
    plan = (FIXTURES / "Parity Budget - Plan.csv").read_text()
    # Corrupt JUNE's Groceries Available — pre-anchor history. July's rows,
    # the ones the anchor reads, are untouched.
    broken = plan.replace(
        '"Jun 2026","Everyday: Groceries","Everyday","Groceries",$300.00,-$350.00,-$50.00',
        '"Jun 2026","Everyday: Groceries","Everyday","Groceries",$300.00,-$350.00,$999.00',
    )
    assert broken != plan
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "Broken Budget - Register.csv",
            (FIXTURES / "Parity Budget - Register.csv").read_text(),
        )
        zf.writestr("Broken Budget - Plan.csv", broken)
    path = tmp_path / "broken.zip"
    path.write_bytes(buf.getvalue())

    services, budget_id, ynab_budget = await import_export(db_session, path, account_types=TYPES)
    rows = await _anchor_rows(db_session, budget_id)
    assert rows, "an incoherent file is still what the user saw — anchor it"

    report = await parity(
        services,
        budget_id,
        ynab_budget,
        AUG,
        accounts=TYPES,
        credit_card_accounts={"Visa"},
        tracking_accounts={"Brokerage"},
        anchor=AUG,
    )
    assert not report.consistency.self_consistent
    assert report.matches, (
        report.expected_ready_to_assign,
        report.igab_ready_to_assign,
    )


async def test_a_register_only_export_imports_unanchored(db_session, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "Bare Budget - Register.csv", (FIXTURES / "Parity Budget - Register.csv").read_text()
        )
    path = tmp_path / "bare.zip"
    path.write_bytes(buf.getvalue())
    # The parser names the missing Plan CSV as an error; that is the point.
    services, budget_id, _ = await import_export(
        db_session, path, account_types=TYPES, expect_errors=True
    )
    assert await _anchor_rows(db_session, budget_id) == []
    summary = await services.budgets.get_budget_summary(budget_id, AUG)
    assert summary.anchor_month is None


async def test_hygiene_never_asks_an_anchored_budget_for_a_start_date(db_session, tmp_path):
    """`card_debt_predates_budget`'s action text promised exactly what the
    anchor now is; on an anchored budget the finding stays silent."""
    _, budget_id, _ = await _imported(db_session, tmp_path)
    report = await AccountHygieneService(db_session).run(budget_id)
    assert "card_debt_predates_budget" not in {f.kind for f in report.findings}
