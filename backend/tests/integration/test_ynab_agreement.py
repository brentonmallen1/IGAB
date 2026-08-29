"""An imported budget agrees with the export it came from — see ynab_agreement.py.

The numbers below are hand-computed from the fixture CSVs; the docstrings
show the arithmetic so a reviewer can check them without running anything.
"""

import os
from datetime import date
from decimal import Decimal

import pytest

from .ynab_agreement import (
    assert_ynab_agreement,
    cents,
    fixture_zip,
    import_export,
    oracle_for,
    parity,
    real_export_path,
)

JUN, JUL, AUG, SEP = date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)
TYPES = {
    "Checking": ("checking", True),
    "Savings": ("savings", True),
    "Visa": ("credit_card", True),
    "Brokerage": ("investment", False),
}
CARDS = {"Visa"}
TRACKING = {"Brokerage"}


async def _imported(db_session, tmp_path, **kwargs):
    return await import_export(db_session, fixture_zip(tmp_path), account_types=TYPES, **kwargs)


async def test_the_oracle_reads_the_fixture_the_way_ynab_does(db_session, tmp_path):
    """Inflow 5000 + 1000 + 3000 + 3000 + 3000 = 15000 through August.
    Assigned over every month = 3600 rent + 100 utilities + 850 groceries
    + 60 dining + 40 household + 500 investing + 20 gym = 5170.
    Utilities ended July 50 overspent, all of it cash → written off.
    Groceries ended June 50 overspent, all of it on the Visa → NOT written
    off; that 50 rides on the card, which owes 350 − 300 = 50 with no
    reserve behind it. YNAB: 15000 − 5170 − 50 = 9780. IGAB nets the card:
    9780 − 50 = 9730."""
    _, _, ynab_budget = await _imported(db_session, tmp_path)
    o = oracle_for(
        ynab_budget, AUG, accounts=TYPES, credit_card_accounts=CARDS, tracking_accounts=TRACKING
    )
    assert o.inflow == Decimal("15000.00")
    assert o.assigned == Decimal("5170.00")
    assert o.cash_overspending_written_off == Decimal("50.00")
    assert o.rta == Decimal("9780.00")
    assert o.card_balances == Decimal("-50.00")
    assert o.ccp_available == Decimal("0.00")
    assert o.uncovered_current == Decimal("0")
    assert o.uncovered_card_debt == Decimal("50.00")
    assert o.uncategorized_net == Decimal("0")  # the brokerage's rows are tracking
    assert o.expected_igab == Decimal("9730.00")
    assert o.available[("Everyday", "Groceries")] == Decimal("300.00")
    assert ("Credit Card Payments", "Visa") not in o.available


async def test_every_envelope_and_ready_to_assign_agree_in_every_month(db_session, tmp_path):
    """June: Groceries −50 in both (credit overspending is visible while the
    month is open, so YNAB and IGAB agree exactly: 9000 − 5170 = 3830).
    July: Utilities −50 in both. August: Groceries 300, everything else 0,
    and Ready to Assign 9730 against YNAB's 9780 — the reset card debt."""
    services, budget_id, ynab_budget = await _imported(db_session, tmp_path)
    await assert_ynab_agreement(
        services,
        budget_id,
        ynab_budget,
        months=(JUN, JUL, AUG),
        accounts=TYPES,
        credit_card_accounts=CARDS,
        tracking_accounts=TRACKING,
    )
    report = await parity(
        services,
        budget_id,
        ynab_budget,
        AUG,
        accounts=TYPES,
        credit_card_accounts=CARDS,
        tracking_accounts=TRACKING,
    )
    assert report.matches
    assert report.igab_ready_to_assign == cents("9730")
    assert report.ynab_ready_to_assign == cents("9780")
    assert report.uncovered_card_debt == cents("50")
    june = await parity(
        services,
        budget_id,
        ynab_budget,
        JUN,
        accounts=TYPES,
        credit_card_accounts=CARDS,
        tracking_accounts=TRACKING,
    )
    assert june.igab_ready_to_assign == june.ynab_ready_to_assign == cents("3830")


async def test_closing_every_dormant_account_leaves_ready_to_assign_unchanged(db_session, tmp_path):
    """Savings last moved in June and holds 1200. The import offers to close
    accounts like it; closing must not move Ready to Assign."""
    services, budget_id, ynab_budget = await _imported(db_session, tmp_path)
    before = (await services.budgets.get_budget_summary(budget_id, AUG)).to_be_assigned

    accounts = {a.name: a for a in await services.account_repo.get_all(budget_id)}
    await services.account_repo.update(accounts["Savings"].id, is_closed=True)
    after = (await services.budgets.get_budget_summary(budget_id, AUG)).to_be_assigned
    assert after == before == cents("9730")

    # And a fresh import that closes it on the way in says the same.
    closed_services, closed_id, closed_ynab = await _imported(
        db_session, tmp_path, close_accounts={"Savings"}
    )
    assert (await closed_services.budgets.get_budget_summary(closed_id, AUG)).to_be_assigned == (
        cents("9730")
    )


async def test_a_future_dated_row_does_not_touch_this_months_figure(db_session, tmp_path):
    """The September rent is in the register. August's Ready to Assign reads
    the month it is about; September's carries the same figure, because the
    rent lands in an envelope the moment its month is viewed."""
    services, budget_id, ynab_budget = await _imported(db_session, tmp_path)
    august = await services.budgets.get_budget_summary(budget_id, AUG)
    september = await services.budgets.get_budget_summary(budget_id, SEP)
    assert august.to_be_assigned == cents("9730")
    assert september.to_be_assigned == cents("9730")
    # The header, deliberately, still shows the money leaving.
    accounts = {a.name: a for a in await services.account_repo.get_all(budget_id)}
    assert await services.account_repo.get_balance(accounts["Checking"].id) == cents("7680")


@pytest.mark.skipif(real_export_path() is None, reason="set IGAB_YNAB_EXPORT=<zip> to run")
async def test_real_export(db_session):
    """The same assertions against a real export (never committed). Set
    IGAB_YNAB_RTA to the figure YNAB showed at export time to also pin the
    oracle itself, IGAB_YNAB_MONTH=YYYY-MM to pick the month, and
    IGAB_YNAB_CREDIT_CARDS=Name,Name for the card accounts."""
    path = real_export_path()
    assert path is not None
    cards = {n.strip() for n in os.environ.get("IGAB_YNAB_CREDIT_CARDS", "").split(",") if n}
    tracking = {n.strip() for n in os.environ.get("IGAB_YNAB_TRACKING", "").split(",") if n}
    types = {c: ("credit_card", True) for c in cards}
    types.update({t: ("investment", False) for t in tracking})
    services, budget_id, ynab_budget = await import_export(db_session, path, account_types=types)
    raw_month = os.environ.get("IGAB_YNAB_MONTH")
    if raw_month:
        year, month = (int(x) for x in raw_month.split("-"))
        month_date = date(year, month, 1)
    else:
        month_date = max(row.month for row in ynab_budget.plan_rows)
    report = await parity(
        services,
        budget_id,
        ynab_budget,
        month_date,
        accounts=None,
        credit_card_accounts=cards,
        tracking_accounts=tracking,
    )
    expected_rta = os.environ.get("IGAB_YNAB_RTA")
    if expected_rta:
        assert report.ynab_ready_to_assign == cents(expected_rta)
    assert report.consistency.self_consistent, (
        f"the export disagrees with itself: "
        f"{report.consistency.carryover_rows_violating}/"
        f"{report.consistency.carryover_rows_checked} plan rows break YNAB's own running "
        f"balance, {report.consistency.activity_cells_disagreeing}/"
        f"{report.consistency.activity_cells_checked} Activity cells disagree with the "
        "register. Nothing below can be read as an IGAB result."
    )
    assert report.categories_differing == 0, report.top_differences
    assert report.igab_ready_to_assign == report.expected_ready_to_assign, (
        f"IGAB {report.igab_ready_to_assign} vs expected {report.expected_ready_to_assign} "
        f"(YNAB {report.ynab_ready_to_assign}, uncovered card debt {report.uncovered_card_debt}, "
        f"uncategorized {report.uncategorized_net}, "
        f"{report.categories_pending} envelope(s) pending approval)"
    )
