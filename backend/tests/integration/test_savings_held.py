"""Saved = moved + held, on a real budget.

`domain/savings.py` says what held is: how much a kept-here Savings envelope's
balance grew, read off the Budget page's Available and floored the way the
page floors it. Each worked check from that module's docstring is a test here,
by name, against real rows — and then every consumer is held to one answer:
the Savings Rate tab, the Overview card, the dialog's contributors and Income
vs Expenses.

Names are the shared invented vocabulary; amounts are round enough to check
on paper. The clock is pinned mid-month so "future-dated" has a meaning.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import update

from igab.db.models import Category, CategoryGroup
from igab.domain.savings import HELD_REASON, HELD_REASON_LABEL
from igab.guide.detection import GuideDetection
from igab.repositories.category_filters import IS_SAVINGS_CATEGORY
from igab.repositories.import_anchor_repo import anchor_rows
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.card_payment import ensure_payment_category
from igab.services.report_basics import savings_contributors
from igab.services.report_service import ReportService
from igab.services.savings_held import held_between, held_by_envelope, held_by_month
from tests.report_clock import report_today

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
    create_user,
)

D = Decimal
TODAY = date(2026, 3, 15)
JAN, FEB, MAR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)


@pytest.fixture(autouse=True)
def _pinned_clock():
    with report_today(TODAY):
        yield


async def _tag(db_session, category, key: str, mode: str | None = None) -> None:
    tags = TagRepository(db_session)
    tag = await tags.get_system_tag(category.budget_id, key)
    assert tag is not None
    await tags.set_category_tags(category.id, [tag.id])
    category.savings_mode = mode
    await db_session.flush()


async def _world(db_session, user=None) -> dict:
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    await seed_system_tags(db_session, budget.id)
    w: dict = {"budget": budget}
    w["checking"] = await create_account(db_session, budget, "Checking")
    w["hysa"] = await create_account(
        db_session,
        budget,
        "Cascade Point HYSA",
        account_type="savings",
        on_budget=False,
        counts_as_savings=True,
    )
    income = await create_category_group(db_session, budget, "Income", is_system=True)
    w["inflow"] = await create_category(db_session, budget, income, "Inflow")
    w["goals"] = await create_category_group(db_session, budget, "Goals")
    w["kept"] = await create_category(db_session, budget, w["goals"], "General Savings")
    await _tag(db_session, w["kept"], "savings", "kept_here")
    return w


async def _pay(db_session, w, amount: str, when: date) -> None:
    await create_transaction(
        db_session, w["budget"], w["checking"], amount, when, category=w["inflow"]
    )


async def _spend(db_session, w, amount: str, when: date, category=None) -> None:
    await create_transaction(
        db_session, w["budget"], w["checking"], f"-{amount}", when, category=category or w["kept"]
    )


async def _saved(db_session, w, start: date, end: date) -> tuple[Decimal, Decimal, Decimal]:
    """(saved, moved, held) over a window, as the dialog serves them."""
    data = await savings_contributors(db_session, w["budget"].id, start, end)
    return data["savings"], data["savings_moved"], data["savings_held"]


# ─── The worked checks ────────────────────────────────────────────────────────


async def test_assigning_to_a_kept_envelope_is_saved(db_session):
    w = await _world(db_session)
    await _pay(db_session, w, "5000", date(2026, 3, 2))
    await create_budget_assignment(db_session, w["budget"], w["kept"], MAR, "500")

    assert await _saved(db_session, w, MAR, TODAY) == (D("500"), D("0"), D("500"))
    tab = await ReportService(db_session).savings_rate(w["budget"].id, months=1)
    assert tab["summary"]["savings"] == D("500")
    assert tab["summary"]["savings_rate"] == 0.1


async def test_spending_from_a_kept_envelope_dissaves(db_session):
    w = await _world(db_session)
    await create_budget_assignment(db_session, w["budget"], w["kept"], FEB, "500")
    await _spend(db_session, w, "120", date(2026, 3, 10))

    assert await _saved(db_session, w, MAR, TODAY) == (D("-120"), D("0"), D("-120"))
    march = (await ReportService(db_session).savings_rate(w["budget"].id, months=1))["months"][0]
    # The repair is still spending: it counts there, and lowers saved.
    assert (march["spending"], march["savings"]) == (D("120"), D("-120"))


async def test_kept_to_tracked_hysa_nets_to_zero(db_session):
    w = await _world(db_session)
    await create_budget_assignment(db_session, w["budget"], w["kept"], FEB, "500")
    await create_transfer(
        db_session,
        w["budget"],
        w["checking"],
        w["hysa"],
        "300",
        date(2026, 3, 5),
        category=w["kept"],
    )

    assert await _saved(db_session, w, MAR, TODAY) == (D("0"), D("300"), D("-300"))


async def test_overspent_kept_envelope_floors_at_zero(db_session):
    """Ready to Assign covered the overspend: the envelope held 100 and now
    holds nothing — held −100, not −250. A month that began overspent starts
    at zero, so the next assignment is held in full."""
    w = await _world(db_session)
    await _spend(db_session, w, "50", date(2026, 1, 10))
    await create_budget_assignment(db_session, w["budget"], w["kept"], FEB, "100")
    await _spend(db_session, w, "250", date(2026, 3, 3))

    assert await held_by_month(db_session, w["budget"].id, [JAN, FEB, MAR], TODAY) == [
        D("0"),
        D("100"),
        D("-100"),
    ]


async def test_pass_through_envelope_saves_nothing_twice(db_session):
    """Never assigned, it sends 800 to the HYSA: moved +800, held max(0, −800)
    − 0 = 0. Saved is 800 — once."""
    w = await _world(db_session)
    await create_transfer(
        db_session,
        w["budget"],
        w["checking"],
        w["hysa"],
        "800",
        date(2026, 3, 5),
        category=w["kept"],
    )

    assert await _saved(db_session, w, MAR, TODAY) == (D("800"), D("800"), D("0"))


async def test_hysa_withdrawal_then_reassign_is_zero(db_session):
    """Drawn back uncategorized, the money lands in Ready to Assign as a
    SAVINGS-class inflow (moved −400); assigned back, it is held +400."""
    w = await _world(db_session)
    await create_budget_assignment(db_session, w["budget"], w["kept"], FEB, "1000")
    await create_transfer(db_session, w["budget"], w["hysa"], w["checking"], "400", MAR)
    await create_budget_assignment(db_session, w["budget"], w["kept"], MAR, "400")

    assert await _saved(db_session, w, MAR, TODAY) == (D("0"), D("-400"), D("400"))


async def test_future_dated_row_is_not_held_until_its_date(db_session):
    w = await _world(db_session)
    await create_budget_assignment(db_session, w["budget"], w["kept"], FEB, "500")
    await _spend(db_session, w, "200", date(2026, 3, 20))
    budget_id = w["budget"].id

    # The page's March Available already holds the row; the held figure does not.
    assert await held_between(db_session, budget_id, MAR, TODAY) == D("0")
    assert await held_between(db_session, budget_id, MAR, date(2026, 3, 19)) == D("0")
    assert await held_between(db_session, budget_id, MAR, date(2026, 3, 20)) == D("-200")
    assert await held_between(db_session, budget_id, MAR, date(2026, 3, 31)) == D("-200")
    with report_today(date(2026, 3, 25)):
        tab = await ReportService(db_session).savings_rate(budget_id, months=1)
    assert tab["summary"]["savings_held"] == D("-200")


async def test_unrecovered_months_fall_back_to_flows(db_session):
    """YNAB ended January at 100 though January alone assigned 200, so no
    earlier balance can be walked back: November and December are unknown.
    A step touching an unknown balance holds 0 — those months' saved is their
    moved alone — and the months after still hold what they held. The window's
    held is the months' held added up, on the tab and in `held_between`.

    The bound, pinned: the December transfer to the HYSA left the envelope,
    which would have held −300, and here it reads 0."""
    w = await _world(db_session)
    budget = w["budget"]
    await create_budget_assignment(db_session, budget, w["kept"], date(2025, 11, 1), "600")
    await create_transfer(
        db_session,
        budget,
        w["checking"],
        w["hysa"],
        "300",
        date(2025, 12, 5),
        category=w["kept"],
    )
    await create_budget_assignment(db_session, budget, w["kept"], JAN, "200")
    await create_budget_assignment(db_session, budget, w["kept"], MAR, "50")
    db_session.add_all(
        anchor_rows(budget.id, JAN, available={w["kept"].id: D("100")}, reserve={}, uncovered={})
    )
    await db_session.flush()

    months = [date(2025, 11, 1), date(2025, 12, 1), JAN, FEB, MAR]
    held = await held_by_month(db_session, budget.id, months, TODAY)
    assert held == [D("0"), D("0"), D("0"), D("0"), D("50")]

    tab = await ReportService(db_session).savings_rate(budget.id, months=5)
    december = tab["months"][1]
    assert (december["savings"], december["savings_moved"], december["savings_held"]) == (
        D("300"),
        D("300"),
        D("0"),
    )
    assert tab["summary"]["savings_held"] == D("50")
    assert await held_between(db_session, budget.id, months[0], TODAY) == D("50")


async def test_monthly_held_telescopes_to_the_window(db_session):
    """January +300 (assign 400, spend 100); February −300 (overspent, floored
    to zero); March +200 (assign 250, 50 on to the HYSA). The months add up to
    the window, and so do any two adjacent windows."""
    w = await _world(db_session)
    budget_id = w["budget"].id
    await create_budget_assignment(db_session, w["budget"], w["kept"], JAN, "400")
    await _spend(db_session, w, "100", date(2026, 1, 12))
    await _spend(db_session, w, "500", date(2026, 2, 12))
    await create_budget_assignment(db_session, w["budget"], w["kept"], MAR, "250")
    await create_transfer(
        db_session,
        w["budget"],
        w["checking"],
        w["hysa"],
        "50",
        date(2026, 3, 10),
        category=w["kept"],
    )

    months = await held_by_month(db_session, budget_id, [JAN, FEB, MAR], TODAY)
    assert months == [D("300"), D("-300"), D("200")]
    whole = await held_between(db_session, budget_id, JAN, TODAY)
    assert whole == sum(months) == D("200")
    for cut in (date(2026, 1, 31), date(2026, 2, 14), date(2026, 3, 9)):
        before = await held_between(db_session, budget_id, JAN, cut)
        after = await held_between(
            db_session, budget_id, cut.fromordinal(cut.toordinal() + 1), TODAY
        )
        assert before + after == whole, cut
    tab = await ReportService(db_session).savings_rate(budget_id, months=3)
    assert tab["summary"]["savings_held"] == whole


async def test_archived_and_hidden_kept_envelopes_still_hold(db_session):
    """Archiving hides an envelope from the grid; the money is still in it."""
    w = await _world(db_session)
    budget = w["budget"]
    await create_budget_assignment(db_session, budget, w["kept"], MAR, "300")
    w["kept"].is_archived = True
    shelf = await create_category_group(db_session, budget, "Old Goals")
    tucked = await create_category(db_session, budget, shelf, "Rainy Day")
    await _tag(db_session, tucked, "savings", "kept_here")
    await create_budget_assignment(db_session, budget, tucked, MAR, "200")
    group = await db_session.get(CategoryGroup, shelf.id)
    group.is_archived = True
    await db_session.flush()

    per = await held_by_envelope(db_session, budget.id, MAR, TODAY)
    assert per == {w["kept"].id: ("General Savings", D("300")), tucked.id: ("Rainy Day", D("200"))}


async def test_income_or_card_envelope_tagged_savings_holds_nothing(db_session):
    """`HOLDS_SAVINGS` leaves out the income group and a card's set-aside:
    neither balance is the household's to call saved."""
    w = await _world(db_session)
    budget = w["budget"]
    await _tag(db_session, w["inflow"], "savings", "kept_here")
    visa = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    payment = await ensure_payment_category(db_session, visa)
    assert payment is not None
    await _tag(db_session, payment, "savings", "kept_here")
    await _pay(db_session, w, "5000", date(2026, 3, 2))
    await create_budget_assignment(db_session, budget, payment, MAR, "200")

    per = await held_by_envelope(db_session, budget.id, MAR, TODAY)
    assert set(per) == {w["kept"].id}
    assert await held_between(db_session, budget.id, MAR, TODAY) == D("0")


async def test_sent_out_category_contributes_no_held(db_session):
    """A sent-out Savings envelope counts its outflows (rule 1), never its
    balance: assigning 500 saves nothing, spending 100 saves 100."""
    w = await _world(db_session)
    vacation = await create_category(db_session, w["budget"], w["goals"], "Vacation")
    await _tag(db_session, vacation, "savings")
    await create_budget_assignment(db_session, w["budget"], vacation, MAR, "500")
    await _spend(db_session, w, "100", date(2026, 3, 8), category=vacation)

    assert await _saved(db_session, w, MAR, TODAY) == (D("100"), D("100"), D("0"))
    assert vacation.id not in await held_by_envelope(db_session, w["budget"].id, MAR, TODAY)


async def test_card_charge_from_a_kept_envelope_lowers_held(db_session):
    w = await _world(db_session)
    visa = await create_account(
        db_session, w["budget"], "Sapphire Visa", account_type="credit_card"
    )
    await ensure_payment_category(db_session, visa)
    await create_budget_assignment(db_session, w["budget"], w["kept"], FEB, "500")
    await create_transaction(
        db_session, w["budget"], visa, "-120", date(2026, 3, 6), category=w["kept"]
    )

    assert await held_between(db_session, w["budget"].id, MAR, TODAY) == D("-120")


# ─── Consumers ────────────────────────────────────────────────────────────────


async def _mixed_month(db_session) -> dict:
    """Income 5,000; a sent-out Vacation flight 250; the kept envelope assigned
    600 in February, 400 more in March, 300 of it on to the HYSA; an
    uncategorized 200 straight to the HYSA; and a kept envelope that did
    nothing this month.

    moved = 250 + 300 + 200 = 750; held = 400 − 300 = 100; saved = 850."""
    w = await _world(db_session)
    budget = w["budget"]
    w["vacation"] = await create_category(db_session, budget, w["goals"], "Vacation")
    await _tag(db_session, w["vacation"], "savings")
    w["idle"] = await create_category(db_session, budget, w["goals"], "Emergency Fund")
    await _tag(db_session, w["idle"], "savings", "kept_here")
    await create_budget_assignment(db_session, budget, w["idle"], FEB, "900")
    await _pay(db_session, w, "5000", date(2026, 3, 2))
    await create_budget_assignment(db_session, budget, w["kept"], FEB, "600")
    await create_budget_assignment(db_session, budget, w["kept"], MAR, "400")
    await _spend(db_session, w, "250", date(2026, 3, 4), category=w["vacation"])
    await create_transfer(
        db_session, budget, w["checking"], w["hysa"], "300", date(2026, 3, 6), category=w["kept"]
    )
    await create_transfer(db_session, budget, w["checking"], w["hysa"], "200", date(2026, 3, 7))
    return w


async def test_contributors_sum_to_the_card_with_held_rows(db_session):
    w = await _mixed_month(db_session)

    data = await savings_contributors(db_session, w["budget"].id, MAR, date(2026, 3, 31))

    assert (data["savings"], data["savings_moved"], data["savings_held"]) == (
        D("850"),
        D("750"),
        D("100"),
    )
    assert sum((c["total"] for c in data["savings_contributors"]), D("0")) == data["savings"]
    by_name = {c["name"]: c for c in data["savings_contributors"]}
    assert set(by_name) == {"Cascade Point HYSA", "Vacation", "General Savings"}
    assert by_name["General Savings"] == {
        "kind": "category",
        "id": w["kept"].id,
        "name": "General Savings",
        "reason": HELD_REASON,
        "reason_label": HELD_REASON_LABEL,
        "total": D("100.00"),
        "count": 1,
    }
    # The idle envelope held nothing this month and is omitted, not a zero row.
    assert "Emergency Fund" not in by_name
    assert by_name["Cascade Point HYSA"]["total"] == D("500.00")


async def test_the_overview_card_the_savings_rate_tab_and_the_dialog_agree(db_session):
    w = await _mixed_month(db_session)
    budget_id = w["budget"].id
    svc = ReportService(db_session)

    card = await svc.dashboard_metrics(budget_id, MAR, date(2026, 3, 31))
    tab = await svc.savings_rate(budget_id, months=1)
    dialog = await savings_contributors(db_session, budget_id, tab["start_date"], tab["end_date"])

    assert card["savings_rate"] == tab["summary"]["savings_rate"] == 0.17
    assert float(dialog["savings"] / dialog["income"]) == card["savings_rate"]
    assert tab["summary"]["savings_held"] == dialog["savings_held"] == D("100")
    assert tab["summary"]["savings_held"] == await held_between(db_session, budget_id, MAR, TODAY)
    assert tab["months"][0]["savings"] == tab["summary"]["savings"] == D("850")

    resp_month = (await svc.income_vs_expense(budget_id, months=1))[0]
    assert resp_month["savings"] == tab["summary"]["savings"]


async def test_income_vs_expense_net_stays_money_moved(db_session):
    """`net` reconciles to the accounts, and held money never left them: it is
    income − expenses − moved − debt, and differs from subtracting saved by
    exactly the held part."""
    w = await _mixed_month(db_session)

    row = (await ReportService(db_session).income_vs_expense(w["budget"].id, months=1))[0]

    assert (row["savings"], row["savings_moved"], row["savings_held"]) == (
        D("850"),
        D("750"),
        D("100"),
    )
    assert (
        row["net"] == row["income"] - row["expenses"] - row["savings_moved"] - row["debt_principal"]
    )
    assert row["net"] == D("4250")
    gap = row["net"] - (row["income"] - row["expenses"] - row["savings"] - row["debt_principal"])
    assert gap == row["savings_held"] != 0


async def test_the_endpoints_serve_both_parts(api_client, db_session):
    w = await _world(db_session, api_client.test_user)
    budget = w["budget"]
    await _pay(db_session, w, "5000", date(2026, 3, 2))
    await create_budget_assignment(db_session, budget, w["kept"], MAR, "500")
    await db_session.flush()

    rate = await api_client.get(f"/api/v1/{budget.id}/reports/savings-rate", params={"months": 1})
    assert rate.status_code == 200, rate.text
    assert D(rate.json()["summary"]["savings_held"]) == D("500")
    ive = await api_client.get(f"/api/v1/{budget.id}/reports/income-expense", params={"months": 1})
    assert ive.status_code == 200, ive.text
    assert D(ive.json()["months"][0]["savings_moved"]) == D("0")
    contrib = await api_client.get(
        f"/api/v1/{budget.id}/reports/savings-contributors",
        params={"start_date": "2026-03-01", "end_date": "2026-03-31"},
    )
    assert contrib.status_code == 200, contrib.text
    assert contrib.json()["savings_contributors"][0]["reason_label"] == HELD_REASON_LABEL


# ─── What stays money-moved ───────────────────────────────────────────────────


async def test_sankey_spent_mode_is_money_moved(db_session):
    """The Cash Flow chart draws rows that left: its savings trunk is the
    300 that went to the HYSA, never the 500 held, and it says so."""
    w = await _world(db_session)
    await _pay(db_session, w, "5000", date(2026, 3, 2))
    await create_budget_assignment(db_session, w["budget"], w["kept"], MAR, "800")
    await create_transfer(
        db_session,
        w["budget"],
        w["checking"],
        w["hysa"],
        "300",
        date(2026, 3, 6),
        category=w["kept"],
    )

    sankey = await ReportService(db_session).cash_flow_sankey(
        w["budget"].id, MAR, TODAY, mode="spent"
    )

    assert sankey["total_savings"] == D("300")
    trunk = next(n for n in sankey["nodes"] if n["id"] == "g___savings__")
    assert trunk["name"] == "To savings accounts"
    links = {(link["source"], link["target"]): link["value"] for link in sankey["links"]}
    assert links[("__budget__", "g___savings__")] == D("300")


async def test_retirement_contributions_ignore_held(db_session):
    """Retirement is money moved into the marked accounts. A kept-here
    envelope's balance is saved, and is not a contribution to anything."""
    today = date.today()
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await seed_system_tags(db_session, budget.id)
    checking = await create_account(db_session, budget, "Checking")
    ira = await create_account(
        db_session, budget, "Vertex Roth IRA", account_type="investment", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Goals")
    kept = await create_category(db_session, budget, group, "Retirement Savings")
    await _tag(db_session, kept, "savings", "kept_here")
    await create_transaction(db_session, budget, checking, "10000", today)
    await create_budget_assignment(db_session, budget, kept, today.replace(day=1), "4000")
    await create_transfer(db_session, budget, checking, ira, "1000", today, category=kept)

    found = await GuideDetection(db_session).retirement_contributions(
        budget.id, bound={"account": (ira.id,)}
    )

    assert found.value == D("10.00")


# ─── Nothing kept here, nothing changed ───────────────────────────────────────

#: Every savings figure the full sample serves at a pinned anchor once each of
#: its savings categories is set to sent out — the shape every budget had
#: before savings modes existed. Held is zero everywhere, so each figure is the
#: money-moved figure the savings rate always served.
#:
#: Pinned before the sample itself changed as `test_sent_out_figures_unchanged
#: _by_this_branch`, against the sample's pre-branch figures. The sample now
#: keeps Emergency Fund and General Savings here and moves money from them to
#: Harborstone Reserve and Cascade Point HYSA, and Vacation is a sinking fund,
#: so the golden was regenerated from the new sample with its kept-here
#: envelopes stripped back to sent out. What it pins is unchanged: a budget with
#: only sent-out categories reads exactly as money moved.
GOLDEN = json.loads((Path(__file__).parent / "savings_golden_sample.json").read_text())


async def _served_figures(db_session, budget) -> tuple[dict, dict]:
    """(the figures the golden pins, the savings-rate tab they came from)."""
    svc = ReportService(db_session)
    tab = await svc.savings_rate(budget.id, 12)
    ive = await svc.income_vs_expense(budget.id, 12)
    d1 = await svc.dashboard_metrics(budget.id, MAR, date(2026, 3, 31))
    d6 = await svc.dashboard_metrics(budget.id, date(2025, 10, 1), date(2026, 3, 31))
    c = await savings_contributors(db_session, budget.id, tab["start_date"], tab["end_date"])
    served = {
        "summary": {
            k: str(tab["summary"][k])
            for k in (
                "income",
                "spending",
                "savings",
                "debt_principal",
                "savings_rate",
                "savings_rate_with_debt",
            )
        },
        "months": [
            [
                str(m["month"]),
                str(m["savings"]),
                str(m["savings_rate"]),
                str(m["savings_rate_with_debt"]),
            ]
            for m in tab["months"]
        ],
        "ive": [[str(r["month"]), str(r["savings"]), str(r["net"])] for r in ive],
        "dash": [str(d1["savings_rate"]), str(d6["savings_rate"])],
        "contrib": [
            str(c["savings"]),
            [[x["name"], x["reason"], str(x["total"])] for x in c["savings_contributors"]],
        ],
    }
    return served, tab


async def test_a_budget_with_only_sent_out_categories_reads_as_money_moved(db_session, monkeypatch):
    import tests.integration.test_sample_budget_reports as sample

    monkeypatch.setattr(sample, "ANCHOR", TODAY)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await sample._generate(db_session, budget, "full")
    await db_session.execute(
        update(Category)
        .where(Category.budget_id == budget.id, IS_SAVINGS_CATEGORY)
        .values(savings_mode="sent_out")
        .execution_options(synchronize_session=False)
    )

    served, tab = await _served_figures(db_session, budget)

    assert served == GOLDEN
    assert tab["summary"]["savings_held"] == 0
    assert tab["summary"]["savings"] == tab["summary"]["savings_moved"]
    assert all(m["savings_held"] == 0 for m in tab["months"])
    assert all(m["savings"] == m["savings_moved"] for m in tab["months"])
    assert all(reason != HELD_REASON for _, reason, _ in served["contrib"][1])
