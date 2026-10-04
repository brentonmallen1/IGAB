"""An imported budget's history mode (`Budget.history_mode`).

'anchored' starts the walks at the import month from YNAB's figures;
'rederived' keeps the anchor rows and reads none of them, so every month is
worked out from the first transaction and is editable. These pin that the
switch is one switch — every anchor reader flips with it — and that it is
reversible to the cent, survives undo, and is refused where it means nothing.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select

from igab.db.models import Budget, BudgetSnapshotMeta, ImportAnchor
from igab.services.transaction_service import TransactionCreate

from .anchored_budget import JUL, JUN, build_anchored_budget
from .factories import create_budget

D = Decimal
AUG = date(2026, 8, 1)


def _figures(summary):
    """Everything a month serves that the mode can move, as plain values."""
    return (
        summary.to_be_assigned,
        sorted(
            (c.category_id, c.assigned, c.activity, c.available) for c in summary.category_balances
        ),
        sorted((c.account_id, c.set_aside, c.uncovered, c.balance) for c in summary.cards),
        summary.anchor_month,
    )


async def _july(db_session, budget_id):
    """July's figures through a fresh service, built the way a request builds
    it — with the snapshot cache, and with its own anchor repository, whose
    per-request memo must not outlive a switch made by another request."""
    from igab.guide.detection import budget_service_from

    return _figures(await budget_service_from(db_session).get_budget_summary(budget_id, JUL))


async def _set(api_client, budget_id, mode):
    return await api_client.put(f"/api/v1/budgets/{budget_id}/history", json={"mode": mode})


async def test_the_setting_reads_anchored_with_the_import_month(db_session, api_client):
    b = await build_anchored_budget(db_session, api_client.test_user)
    resp = await api_client.get(f"/api/v1/budgets/{b.budget.id}/history")
    assert resp.status_code == 200, resp.text
    # Built the way an older import was: an anchor, but no stored YNAB months.
    assert resp.json() == {
        "mode": "anchored",
        "import_month": JUL.isoformat(),
        "keeps_history": False,
    }


async def test_rederived_reads_exactly_the_unanchored_walk(db_session, api_client):
    """Re-derived is not a third behaviour: it is the budget with no anchor,
    which is the path every native budget runs. Compared against the same
    budget with its anchor rows deleted."""
    b = await build_anchored_budget(db_session, api_client.test_user)
    resp = await _set(api_client, b.budget.id, "rederived")
    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "rederived"
    rederived = await _july(db_session, b.budget.id)
    assert rederived[3] is None, "no anchor month is served, so the client clamps nothing"

    await db_session.execute(delete(ImportAnchor).where(ImportAnchor.budget_id == b.budget.id))
    await db_session.flush()
    unanchored = await _july(db_session, b.budget.id)
    assert rederived == unanchored


async def test_switching_back_restores_the_anchored_figures_to_the_cent(db_session, api_client):
    b = await build_anchored_budget(db_session, api_client.test_user)
    before = await _july(db_session, b.budget.id)
    await _set(api_client, b.budget.id, "rederived")
    moved = await _july(db_session, b.budget.id)
    assert moved != before, "re-deriving June's history moves July"
    await _set(api_client, b.budget.id, "anchored")
    assert await _july(db_session, b.budget.id) == before


async def test_rederived_turns_the_late_arrival_rule_off(db_session, api_client):
    """With no anchor in force there is no import month to arrive late into:
    a June row counts in June."""
    b = await build_anchored_budget(db_session, api_client.test_user)
    await _set(api_client, b.budget.id, "rederived")
    row = await b.services.transactions.create(
        b.budget.id,
        TransactionCreate(
            account_id=b.checking.id,
            date=date(2026, 6, 28),
            amount=D("-40.00"),
            category_id=b.groceries.id,
            cleared="cleared",
        ),
    )
    loaded = await b.services.transaction_repo.get(row.id)
    assert (loaded.counts_in_month, loaded.predates_import) == (JUN, False)


async def test_the_switch_clears_the_snapshot_cache(db_session, api_client):
    """The cache bakes the anchor into its rows; a cache built under one mode
    is wrong under the other."""
    b = await build_anchored_budget(db_session, api_client.test_user)
    await _july(db_session, b.budget.id)  # builds the cache
    assert (await db_session.execute(select(BudgetSnapshotMeta))).first() is not None
    await _set(api_client, b.budget.id, "rederived")
    assert (await db_session.execute(select(BudgetSnapshotMeta))).first() is None


async def test_undo_switches_back(db_session, api_client):
    """Change-logged like any budget setting: ⌘Z puts the budget back on its
    anchored figures, and the cache rebuilds under the right mode."""
    b = await build_anchored_budget(db_session, api_client.test_user)
    before = await _july(db_session, b.budget.id)
    await _set(api_client, b.budget.id, "rederived")
    await _july(db_session, b.budget.id)  # cache under rederived
    undone = await api_client.post(f"/api/v1/{b.budget.id}/changes/undo")
    assert undone.status_code == 200, undone.text
    budget = await db_session.get(Budget, b.budget.id)
    await db_session.refresh(budget)
    assert budget.history_mode == "anchored"
    assert await _july(db_session, b.budget.id) == before


async def test_a_budget_never_imported_has_no_setting(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    resp = await api_client.get(f"/api/v1/budgets/{budget.id}/history")
    assert resp.json() == {"mode": "anchored", "import_month": None, "keeps_history": False}
    refused = await _set(api_client, budget.id, "rederived")
    assert refused.status_code == 409
    await db_session.refresh(budget)
    assert budget.history_mode == "anchored"


async def test_setting_the_mode_it_already_has_records_nothing(db_session, api_client):
    """No change, no change-log row — an undo must not land on a no-op."""
    from igab.db.models import ChangeLog

    b = await build_anchored_budget(db_session, api_client.test_user)
    await db_session.flush()
    count = select(ChangeLog).where(ChangeLog.budget_id == b.budget.id)
    before = len((await db_session.execute(count)).all())
    assert (await _set(api_client, b.budget.id, "anchored")).status_code == 200
    assert len((await db_session.execute(count)).all()) == before


async def test_an_import_can_choose_to_rederive(db_session, api_client, tmp_path):
    """Chosen on the preview screen: the import still writes its anchor, so
    the choice can be switched later, and stores the mode."""
    from .ynab_agreement import fixture_zip

    for mode in ("anchored", "rederived"):
        resp = await api_client.post(
            "/api/v1/budgets/import-ynab",
            files={"file": ("export.zip", fixture_zip(tmp_path).read_bytes(), "application/zip")},
            data={"name": f"Parity {mode}", "history_mode": mode},
        )
        assert resp.status_code in (200, 201), resp.text
        budget_id = resp.json()["budget"]["id"]
        history = (await api_client.get(f"/api/v1/budgets/{budget_id}/history")).json()
        assert history["mode"] == mode
        assert history["import_month"] == AUG.isoformat(), "the anchor is written either way"
        assert history["keeps_history"] is True, "so are YNAB's figures for earlier months"
