"""Assets: a stated, dated value joining net worth through a step function.

The mirror of the unmanaged-liability bucket, with the sign flipped — and the
sign is why the rules here are strict: a self-reported figure that moves net
worth UP contributes nothing before its first dated point, never rewrites the
months before that point, and always carries its date. The denormalised
(`manual_value`, `value_as_of`) pair has exactly one writer (AssetRepository's
newest-wins path), pinned here by deleting the newest point and watching the
pair fall back rather than strand.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.repositories.asset_repo import AssetRepository
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_liability,
    create_transaction,
    create_user,
)

TODAY = date.today()
D = Decimal


async def _budget(db_session, owner=None):
    user = owner or await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    await create_transaction(db_session, budget, checking, "1000.00", TODAY - timedelta(days=45))
    return budget


async def _asset(db_session, budget, name="Maple St House", **kwargs):
    return await AssetRepository(db_session).create(budget_id=budget.id, name=name, **kwargs)


async def test_a_valued_asset_raises_net_worth_and_is_broken_out(api_client, db_session):
    budget = await _budget(db_session, api_client.test_user)
    asset = await _asset(db_session, budget)
    repo = AssetRepository(db_session)
    await repo.upsert_value(asset, TODAY - timedelta(days=10), D("300000.00"))

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/net-worth", params={"months": 3})
    body = resp.json()
    latest = body["points"][-1]
    assert D(latest["total_assets"]) == D("301000.00")
    assert D(latest["net_worth"]) == D("301000.00")
    # Broken out, because the value is in the net line without appearing in
    # any account series — the same footnote bucket as unmanaged debts.
    assert D(latest["asset_value_total"]) == D("300000.00")
    assert D(body["asset_value_total"]) == D("300000.00")


async def test_an_asset_with_no_value_point_contributes_nothing(api_client, db_session):
    """Before tracking began there is no honest number to show — the same
    rule the unmanaged-liability step function states."""
    budget = await _budget(db_session, api_client.test_user)
    await _asset(db_session, budget)

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/net-worth", params={"months": 1})
    latest = resp.json()["points"][-1]
    assert D(latest["total_assets"]) == D("1000.00")
    assert D(latest["asset_value_total"]) == D("0")


async def test_a_value_steps_in_at_its_date_and_does_not_rewrite_history(api_client, db_session):
    """A June appraisal must not change January: months before the first
    point read zero, months after each point read that point."""
    budget = await _budget(db_session, api_client.test_user)
    asset = await _asset(db_session, budget)
    repo = AssetRepository(db_session)
    last_month = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
    await repo.upsert_value(asset, last_month, D("250000.00"))
    await repo.upsert_value(asset, TODAY, D("260000.00"))

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/net-worth", params={"months": 3})
    points = resp.json()["points"]
    assert D(points[0]["asset_value_total"]) == D("0")  # before any point
    assert D(points[-2]["asset_value_total"]) == D("250000.00")
    assert D(points[-1]["asset_value_total"]) == D("260000.00")


async def test_dashboard_and_history_agree_with_an_asset_present(api_client, db_session):
    budget = await _budget(db_session, api_client.test_user)
    asset = await _asset(db_session, budget)
    await AssetRepository(db_session).upsert_value(asset, TODAY - timedelta(days=5), D("42000.00"))

    history = (
        await api_client.get(f"/api/v1/{budget.id}/reports/net-worth", params={"months": 3})
    ).json()
    dashboard = (await api_client.get(f"/api/v1/{budget.id}/reports/dashboard")).json()
    assert D(dashboard["net_worth"]) == D(history["points"][-1]["net_worth"])


async def test_the_denormalised_pair_has_one_writer_and_falls_back(db_session):
    """Deleting the newest point must re-derive the pair from the one before
    it — never strand `manual_value` pointing at a row that no longer exists,
    and never leave the value without its date."""
    budget = await _budget(db_session)
    asset = await _asset(db_session, budget)
    repo = AssetRepository(db_session)
    old_point = await repo.upsert_value(asset, TODAY - timedelta(days=400), D("240000.00"))
    new_point = await repo.upsert_value(asset, TODAY, D("260000.00"))
    assert (asset.manual_value, asset.value_as_of) == (D("260000.0000"), TODAY)

    # Editing a point re-derives too.
    await repo.update_value(asset, new_point.id, D("261000.00"))
    assert asset.manual_value == D("261000.0000")

    assert await repo.delete_value(asset, new_point.id)
    assert (asset.manual_value, asset.value_as_of) == (
        D("240000.0000"),
        TODAY - timedelta(days=400),
    )

    assert await repo.delete_value(asset, old_point.id)
    assert (asset.manual_value, asset.value_as_of) == (None, None)


async def test_one_asset_can_secure_two_liabilities(api_client, db_session):
    """linked_asset_id is NOT unique on purpose: a house secures a mortgage
    and a HELOC, and equity is value − Σ owed across everything linked."""
    budget = await _budget(db_session, api_client.test_user)
    asset = await _asset(db_session, budget)
    mortgage = await create_liability(
        db_session, budget, "Maple St Mortgage", manual_balance=D("200000.00")
    )
    heloc = await create_liability(db_session, budget, "Maple St HELOC", manual_balance=D("30000"))

    for liability in (mortgage, heloc):
        resp = await api_client.put(
            f"/api/v1/{budget.id}/liabilities/{liability.id}/link-asset",
            json={"asset_id": str(asset.id)},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["linked_asset_id"] == str(asset.id)

    # Unlink is an explicit null, not a delete.
    resp = await api_client.put(
        f"/api/v1/{budget.id}/liabilities/{heloc.id}/link-asset", json={"asset_id": None}
    )
    assert resp.json()["linked_asset_id"] is None


async def test_deleting_the_asset_unlinks_its_liabilities(api_client, db_session):
    """ondelete=SET NULL never fires on a soft delete, so the repository
    nulls the links itself — a page must never follow `linked_asset_id` to a
    deleted asset."""
    budget = await _budget(db_session, api_client.test_user)
    asset = await _asset(db_session, budget)
    mortgage = await create_liability(
        db_session, budget, "Maple St Mortgage", manual_balance=D("200000.00")
    )
    await api_client.put(
        f"/api/v1/{budget.id}/liabilities/{mortgage.id}/link-asset",
        json={"asset_id": str(asset.id)},
    )

    resp = await api_client.delete(f"/api/v1/{budget.id}/assets/{asset.id}")
    assert resp.status_code == 204
    await db_session.refresh(mortgage)
    assert mortgage.linked_asset_id is None
    # And its value leaves net worth with it.
    nw = await api_client.get(f"/api/v1/{budget.id}/reports/net-worth", params={"months": 1})
    assert D(nw.json()["points"][-1]["asset_value_total"]) == D("0")


async def test_an_asset_outlives_its_loan(db_session):
    """Deleting the liability leaves the asset — a paid-off car stays in net
    worth instead of vanishing the month the loan clears."""
    budget = await _budget(db_session)
    asset = await _asset(db_session, budget, name="Cedar Wagon")
    repo = AssetRepository(db_session)
    await repo.upsert_value(asset, TODAY, D("9000.00"))
    loan = await create_liability(db_session, budget, "Cedar Wagon Loan", manual_balance=D("500"))
    loan.linked_asset_id = asset.id
    await db_session.flush()

    await db_session.delete(loan)
    await db_session.flush()
    asset_now, _ = await ReportService(db_session)._asset_values(budget.id)
    assert asset_now == D("9000.0000")


async def test_the_value_register_lists_edits_and_refuses_strangers(api_client, db_session):
    budget = await _budget(db_session, api_client.test_user)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/assets",
        json={"name": "Maple St House", "asset_type": "property", "value": "250000.00"},
    )
    assert resp.status_code == 201, resp.text
    asset_id = resp.json()["id"]
    assert D(resp.json()["current_value"] or "0") == D("250000.00")

    resp = await api_client.post(
        f"/api/v1/{budget.id}/assets/{asset_id}/values",
        json={"value": "260000.00", "date": str(TODAY - timedelta(days=1))},
    )
    assert resp.status_code == 201

    values = (await api_client.get(f"/api/v1/{budget.id}/assets/{asset_id}/values")).json()
    assert len(values) == 2
    assert values[0]["date"] == str(TODAY)  # newest first

    other_user = await create_user(db_session)
    other_budget = await create_budget(db_session, other_user)
    resp = await api_client.get(f"/api/v1/{other_budget.id}/assets/{asset_id}/values")
    assert resp.status_code in (403, 404)


async def test_stale_value_finding_fires_at_the_boundary(api_client, db_session):
    from igab.services.account_hygiene import STALE_ASSET_VALUE_MONTHS

    budget = await _budget(db_session, api_client.test_user)
    asset = await _asset(db_session, budget)
    repo = AssetRepository(db_session)
    stale_date = TODAY - timedelta(days=STALE_ASSET_VALUE_MONTHS * 30 + 1)
    await repo.upsert_value(asset, stale_date, D("250000.00"))

    body = (await api_client.get(f"/api/v1/{budget.id}/accounts/hygiene")).json()
    finding = next(f for f in body["findings"] if f["kind"] == "stale_asset_value")
    assert finding["asset_ids"] == [str(asset.id)]

    # A fresh value clears it.
    await repo.upsert_value(asset, TODAY, D("260000.00"))
    body = (await api_client.get(f"/api/v1/{budget.id}/accounts/hygiene")).json()
    assert all(f["kind"] != "stale_asset_value" for f in body["findings"])


async def test_double_count_suspect_names_both_sides(api_client, db_session):
    budget = await _budget(db_session, api_client.test_user)
    asset = await _asset(db_session, budget, name="Maple Street House")
    await AssetRepository(db_session).upsert_value(asset, TODAY, D("300000.00"))
    house_account = await create_account(
        db_session, budget, "Maple Street House", account_type="other_asset", on_budget=False
    )
    await create_transaction(
        db_session, budget, house_account, "300000.00", TODAY - timedelta(days=30)
    )

    body = (await api_client.get(f"/api/v1/{budget.id}/accounts/hygiene")).json()
    finding = next(f for f in body["findings"] if f["kind"] == "asset_beside_asset_account")
    assert finding["asset_ids"] == [str(asset.id)]
    assert finding["account_ids"] == [str(house_account.id)]
