"""The emergency fund: what the household chose, and nothing it did not.

Three parts and no guesses (`services/emergency_fund.py`): envelopes tagged
Emergency fund at the Budget page's Available, off-budget savings accounts
marked "counts toward emergency fund", and anything declared as kept elsewhere.
Every surface that quotes the fund reads that one composition.

Invented names and round figures throughout.
"""

import io
import json
import zipfile
from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.dates import add_months, month_start
from igab.guide.repo import GuideRepository
from igab.services.change_log import ChangeRecorder, binding_rows_dump
from igab.services.emergency_fund import emergency_fund
from igab.services.emergency_fund_adoption import ADOPTION_REVISION, adopt
from igab.services.report_basics import savings_contributors
from tests.report_clock import report_today

from .emergency_fund_adoption_cases import (
    PRE_ADOPTION_REVISION,
    assert_chosen_adopted,
    assert_guess_only_adopted,
    build_chosen,
    build_guess_only,
)
from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
    create_user,
    make_services,
    money,
    tag_with_system_tags,
)

D = Decimal
TODAY = date.today()
THIS_MONTH = month_start(TODAY)
LAST_MONTH = add_months(THIS_MONTH, -1)


async def _world(db_session, user=None) -> dict:
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    w: dict = {"budget": budget}
    w["checking"] = await create_account(db_session, budget, "Harborstone Checking")
    w["goals"] = await create_category_group(db_session, budget, "Goals")
    w["fund"] = await create_category(db_session, budget, w["goals"], "Emergency Fund")
    await tag_with_system_tags(db_session, w["fund"], "emergency_fund")
    w["hysa"] = await create_account(
        db_session,
        budget,
        "Cascade Point HYSA",
        account_type="savings",
        on_budget=False,
        counts_as_savings=True,
    )
    return w


async def _flag(db_session, account) -> None:
    account.counts_toward_emergency_fund = True
    await db_session.flush()


async def _declare(api_client, budget, amount: str) -> None:
    r = await api_client.put(
        f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
        json={"mode": "external", "external": True, "external_amount": amount},
    )
    assert r.status_code == 204, r.text


def _parts(parts) -> list[tuple[str, Decimal]]:
    return [(p.name, p.balance) for p in parts]


# ─── What counts ─────────────────────────────────────────────────────────────


async def test_emergency_fund_is_tagged_plus_flagged_plus_external(db_session, api_client):
    w = await _world(db_session, api_client.test_user)
    budget = w["budget"]
    await create_budget_assignment(db_session, budget, w["fund"], THIS_MONTH, "2400.00")
    await create_transaction(db_session, budget, w["hysa"], "6000.00", LAST_MONTH)
    await _flag(db_session, w["hysa"])
    # Neither of these was chosen, so neither counts.
    general = await create_category(db_session, budget, w["goals"], "General Savings")
    await tag_with_system_tags(db_session, general, "savings")
    await create_budget_assignment(db_session, budget, general, THIS_MONTH, "900.00")
    other = await create_account(
        db_session, budget, "Northwind Brokerage", account_type="savings", on_budget=False
    )
    await create_transaction(db_session, budget, other, "4000.00", LAST_MONTH)
    await _declare(api_client, budget, "1000")

    fund = await emergency_fund(db_session, budget.id)

    assert _parts(fund.categories) == [("Emergency Fund", D("2400.00"))]
    assert _parts(fund.accounts) == [("Cascade Point HYSA", D("6000.00"))]
    assert (fund.external.declared, fund.external.amount) == (True, D("1000"))
    assert fund.total == D("9400.00")
    assert fund.set_up is True


async def test_nothing_is_guessed_from_names_or_account_types(db_session, api_client):
    """The old guess found all three of these; none of them was chosen."""
    budget = await create_budget(db_session, api_client.test_user)
    goals = await create_category_group(db_session, budget, "Goals")
    named = await create_category(db_session, budget, goals, "Emergency Fund")
    await tag_with_system_tags(db_session, named, "savings")
    await create_budget_assignment(db_session, budget, named, THIS_MONTH, "1500.00")
    await create_category(db_session, budget, goals, "Rainy Day Buffer")
    savings = await create_account(db_session, budget, "Savings", account_type="savings")
    await create_transaction(db_session, budget, savings, "5000.00", LAST_MONTH)

    fund = await emergency_fund(db_session, budget.id)
    assert (fund.set_up, fund.total, fund.categories, fund.accounts) == (False, None, (), ())

    signals = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()
    signal = next(c for c in signals["concepts"] if c["key"] == "emergency_fund")
    assert (signal["value"], signal["met"], signal["entities"]) == (None, None, {})
    assert signal["fund"]["set_up"] is False


async def test_sent_out_emergency_envelope_pending_available_counts(db_session):
    """Set to sent out, the envelope's outflows count as saved on the rate —
    but what has not been sent yet is still set aside, and the fund reads the
    envelope's Available either way."""
    w = await _world(db_session)
    w["fund"].savings_mode = "sent_out"
    await create_budget_assignment(db_session, w["budget"], w["fund"], THIS_MONTH, "1000.00")
    await create_transfer(
        db_session, w["budget"], w["checking"], w["hysa"], "300.00", TODAY, category=w["fund"]
    )

    fund = await emergency_fund(db_session, w["budget"].id)

    assert _parts(fund.categories) == [("Emergency Fund", D("700.00"))]
    assert fund.total == D("700.00")


async def test_flag_inert_after_account_moves_on_budget(db_session):
    w = await _world(db_session)
    await create_transaction(db_session, w["budget"], w["hysa"], "6000.00", LAST_MONTH)
    await _flag(db_session, w["hysa"])
    assert _parts((await emergency_fund(db_session, w["budget"].id)).accounts) == [
        ("Cascade Point HYSA", D("6000.00"))
    ]

    w["hysa"].on_budget = True
    await db_session.flush()

    fund = await emergency_fund(db_session, w["budget"].id)
    assert fund.accounts == ()
    assert fund.total == D("0.00"), "the tagged envelope is still chosen, and empty"


async def test_emergency_fund_mode_changes_the_rate_not_the_fund_total(db_session):
    """$5,000 of pay, $500 assigned to the fund and $200 of it moved to a
    savings account the fund does not count. Kept here (the tag's default):
    moved 200 plus held 300 is 500 saved. Sent out: the 200 that left is saved
    and the 300 still in the envelope is not. The fund reads $300 both ways."""
    today = date(2026, 3, 15)
    march = date(2026, 3, 1)
    with report_today(today):
        w = await _world(db_session)
        budget = w["budget"]
        income = await create_category_group(db_session, budget, "Income", is_system=True)
        inflow = await create_category(db_session, budget, income, "Inflow")
        await create_transaction(
            db_session, budget, w["checking"], "5000.00", date(2026, 3, 2), category=inflow
        )
        await create_budget_assignment(db_session, budget, w["fund"], march, "500.00")
        await create_transfer(
            db_session,
            budget,
            w["checking"],
            w["hysa"],
            "200.00",
            date(2026, 3, 5),
            category=w["fund"],
        )

        kept = await savings_contributors(db_session, budget.id, march, today)
        kept_fund = await emergency_fund(db_session, budget.id)

        w["fund"].savings_mode = "sent_out"
        await db_session.flush()
        sent = await savings_contributors(db_session, budget.id, march, today)
        sent_fund = await emergency_fund(db_session, budget.id)

    assert (kept["savings_moved"], kept["savings_held"], kept["savings"]) == (
        D("200.00"),
        D("300.00"),
        D("500.00"),
    )
    assert (sent["savings_moved"], sent["savings_held"], sent["savings"]) == (
        D("200.00"),
        D("0"),
        D("200.00"),
    )
    assert kept_fund.total == sent_fund.total == D("300.00")


async def test_dismissed_concept_still_reports_the_composition(db_session, api_client):
    """Dismissing the Guide's step stops the Guide talking about the fund. The
    reports still show what was chosen: the tag is a budget fact."""
    w = await _world(db_session, api_client.test_user)
    budget = w["budget"]
    await create_budget_assignment(db_session, budget, w["fund"], THIS_MONTH, "1200.00")
    r = await api_client.put(
        f"/api/v1/{budget.id}/guide/bindings/emergency_fund", json={"mode": "dismissed"}
    )
    assert r.status_code == 204

    essentials = (await api_client.get(f"/api/v1/{budget.id}/reports/essentials")).json()
    coverage = (await api_client.get(f"/api/v1/{budget.id}/reports/emergency-fund")).json()
    for served in (essentials["emergency_fund"], coverage["fund"]):
        assert served["set_up"] is True
        assert money(served["total"]) == D("1200.00")
        assert [c["name"] for c in served["categories"]] == ["Emergency Fund"]

    signals = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()
    signal = next(c for c in signals["concepts"] if c["key"] == "emergency_fund")
    assert signal["tracked"] is False
    assert signal["fund"] is None
    checkup = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()
    assert not [f for f in checkup["findings"] if f["concept_key"] == "emergency_fund"]


async def test_emergency_fund_binding_refuses_entities(db_session, api_client):
    """The concept binds to nothing now. A client still sending the old
    manual mode is refused rather than storing rows nothing reads."""
    w = await _world(db_session, api_client.test_user)
    budget = w["budget"]
    path = f"/api/v1/{budget.id}/guide/bindings/emergency_fund"

    for entity_ids in ({"category": [str(w["fund"].id)]}, {"account": [str(w["hysa"].id)]}):
        r = await api_client.put(path, json={"mode": "manual", "entity_ids": entity_ids})
        assert r.status_code == 422, r.text
        assert "Emergency fund" in r.json()["detail"]
    assert await GuideRepository(db_session).bindings(budget.id) == []

    # Kept elsewhere is still an answer, and an empty selection is no selection.
    r = await api_client.put(
        path,
        json={"mode": "manual", "entity_ids": {"category": []}, "external": True},
    )
    assert r.status_code == 204, r.text
    assert [b.mode for b in await GuideRepository(db_session).bindings(budget.id)] == ["external"]


# ─── One total ───────────────────────────────────────────────────────────────


async def test_every_surface_quotes_one_total(db_session, api_client):
    """The Guide signal, the Essentials report, the Emergency Fund report's
    headline and its newest point, all $9,400 — envelope, account and the
    declared amount. Nothing moves this month, so the newest complete month
    and today agree."""
    w = await _world(db_session, api_client.test_user)
    budget = w["budget"]
    bills = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, bills, "Rent")
    await tag_with_system_tags(db_session, rent, "essential")
    for back in (3, 2, 1):
        month = add_months(THIS_MONTH, -back)
        await create_transaction(
            db_session, budget, w["checking"], "-1000.00", month + timedelta(days=4), category=rent
        )
    earlier = add_months(THIS_MONTH, -2)
    await create_budget_assignment(db_session, budget, w["fund"], earlier, "2400.00")
    await create_transaction(db_session, budget, w["hysa"], "6000.00", earlier)
    await _flag(db_session, w["hysa"])
    await _declare(api_client, budget, "1000")

    signals = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()
    signal = next(c for c in signals["concepts"] if c["key"] == "emergency_fund")
    essentials = (await api_client.get(f"/api/v1/{budget.id}/reports/essentials")).json()
    coverage = (
        await api_client.get(f"/api/v1/{budget.id}/reports/emergency-fund", params={"months": 3})
    ).json()

    picker = (await api_client.get(f"/api/v1/{budget.id}/emergency-fund")).json()

    totals = {
        "picker": money(picker["fund"]["total"]),
        "signal value": money(signal["value"]),
        "signal fund": money(signal["fund"]["total"]),
        "essentials": money(essentials["emergency_fund"]["total"]),
        "coverage fund": money(coverage["fund"]["total"]),
        "newest point": money(coverage["series"][-1]["fund_balance"]),
    }
    assert set(totals.values()) == {D("9400.00")}, totals
    assert money(signal["detected_value"]) == D("8400.00")


# ─── The Budget page's number ────────────────────────────────────────────────


class TestTheFundReadsTheBudgetPagesNumber:
    """The fund's envelope figure decides whether the roadmap says someone has
    no emergency fund, so it is the Budget page's Available — not a running
    total of assignments and activity."""

    async def _both(self, db_session, w):
        fund = await emergency_fund(db_session, w["budget"].id)
        page = await make_services(db_session).budgets.get_category_balance(
            w["fund"].id, THIS_MONTH
        )
        return fund.categories[0].balance, page.available

    async def test_a_covered_overspend_does_not_follow_the_envelope(self, db_session):
        w = await _world(db_session)
        await create_budget_assignment(db_session, w["budget"], w["fund"], LAST_MONTH, "100.00")
        await create_transaction(
            db_session, w["budget"], w["checking"], "-150.00", LAST_MONTH, category=w["fund"]
        )
        await create_budget_assignment(db_session, w["budget"], w["fund"], THIS_MONTH, "200.00")

        assert await self._both(db_session, w) == (D("200.00"), D("200.00"))

    async def test_an_assignment_for_a_future_month_is_not_money_you_have_now(self, db_session):
        w = await _world(db_session)
        await create_budget_assignment(db_session, w["budget"], w["fund"], THIS_MONTH, "100.00")
        later = add_months(THIS_MONTH, 10)
        await create_budget_assignment(db_session, w["budget"], w["fund"], later, "500.00")

        assert await self._both(db_session, w) == (D("100.00"), D("100.00"))

    async def test_the_floor_is_per_envelope_not_across_the_total(self, db_session):
        """One envelope $50 over and one $50 under hold $0 and $50."""
        w = await _world(db_session)
        under = await create_category(db_session, w["budget"], w["goals"], "Second Cushion")
        await tag_with_system_tags(db_session, under, "emergency_fund")
        await create_transaction(
            db_session, w["budget"], w["checking"], "-50.00", LAST_MONTH, category=w["fund"]
        )
        await create_budget_assignment(db_session, w["budget"], under, LAST_MONTH, "50.00")

        fund = await emergency_fund(db_session, w["budget"].id)

        assert fund.total == D("50.00")


# ─── Adoption ────────────────────────────────────────────────────────────────


@pytest.fixture
def snapshot_store(tmp_path, monkeypatch):
    from igab.config import settings

    monkeypatch.setattr(settings, "BACKUPS_DIR", str(tmp_path))
    return tmp_path


async def _export_at(api_client, budget_id, revision: str) -> bytes:
    """The budget's snapshot, its manifest saying it was taken at `revision`."""
    resp = await api_client.get(f"/api/v1/budgets/{budget_id}/snapshot")
    assert resp.status_code == 200, resp.text
    source = zipfile.ZipFile(io.BytesIO(resp.content))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "manifest.json":
                manifest = json.loads(data)
                manifest["alembic_revision"] = revision
                data = json.dumps(manifest).encode()
            target.writestr(item, data)
    return out.getvalue()


async def _restore(api_client, budget, body: bytes) -> None:
    resp = await api_client.post(
        f"/api/v1/budgets/{budget.id}/snapshot/restore",
        files={"file": ("snapshot.igab.zip", body, "application/zip")},
        data={"confirm_name": budget.name, "pre_snapshot": "false"},
    )
    assert resp.status_code == 200, resp.text


async def test_restoring_a_pre_adoption_snapshot_adopts_like_the_migration(
    db_session, api_client, snapshot_store
):
    """The same cases `test_migrations_adopt_emergency_bindings` runs through
    the migration, run through a restore of a snapshot taken before it."""
    chosen_budget = await create_budget(db_session, api_client.test_user)
    chosen = await db_session.run_sync(lambda s: build_chosen(s.connection(), chosen_budget.id))
    guess_budget = await create_budget(db_session, api_client.test_user)
    await db_session.run_sync(lambda s: build_guess_only(s.connection(), guess_budget.id))
    await db_session.commit()

    for budget in (chosen_budget, guess_budget):
        await _restore(
            api_client, budget, await _export_at(api_client, budget.id, PRE_ADOPTION_REVISION)
        )

    await db_session.run_sync(lambda s: assert_chosen_adopted(s.connection(), chosen))
    await db_session.run_sync(lambda s: assert_guess_only_adopted(s.connection(), guess_budget.id))


async def test_a_current_snapshot_is_not_restamped(db_session, api_client, snapshot_store):
    """Taken after adoption, a snapshot has no old rows to convert — and the
    adopter's guesses would be false alarms: a category named Rainy Day gets no
    notice, and a Savings + Emergency fund envelope the household left on the
    default is not stamped sent out."""
    budget = await create_budget(db_session, api_client.test_user)
    goals = await create_category_group(db_session, budget, "Goals")
    both = await create_category(db_session, budget, goals, "House Cushion")
    await tag_with_system_tags(db_session, both, "savings", "emergency_fund")
    await create_category(db_session, budget, goals, "Rainy Day")
    await db_session.commit()

    await _restore(api_client, budget, await _export_at(api_client, budget.id, ADOPTION_REVISION))

    await db_session.refresh(both)
    assert both.savings_mode is None
    state = await GuideRepository(db_session).state(budget.id)
    assert not [key for key in state if key.startswith("notice:emergency_fund")]


async def test_pre_upgrade_binding_undo_conflicts(db_session, api_client):
    """An emergency-fund binding edit recorded before the upgrade names rows
    the adoption removed. Undoing it raises the conflict — it must not put back
    manual rows nothing reads and call that undone."""
    w = await _world(db_session, api_client.test_user)
    budget = w["budget"]
    repo = GuideRepository(db_session)
    # What the old `set_binding` wrote and recorded.
    created = await repo.replace_concept(
        budget.id,
        "emergency_fund",
        [{"mode": "manual", "entity_type": "category", "entity_id": w["fund"].id}],
    )
    await ChangeRecorder(db_session).record(
        budget_id=budget.id,
        entity_type="guide_binding",
        entity_id=budget.id,
        action="update",
        before={"_concept_key": "emergency_fund", "_rows": []},
        after={"_concept_key": "emergency_fund", "_rows": binding_rows_dump(created)},
    )
    await adopt(db_session, budget.id)
    await db_session.commit()

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/undo")

    assert resp.status_code == 409, resp.text
    assert await repo.bindings(budget.id) == []
