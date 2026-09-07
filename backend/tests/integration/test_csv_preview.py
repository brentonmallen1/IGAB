"""Saying what a CSV would do, before it does it.

The importer already worked; what it never did was speak. A bank export
overlaps the previous one almost every time, so "128 rows, 12 already
imported" is the thing a person needs in front of them — not afterwards, in a
number they cannot check.
"""

from decimal import Decimal

from .factories import create_account, create_budget, create_category, create_category_group

HEADER = "Posted Date,Description,Debit,Credit\n"


async def _preview(api_client, budget, account, csv: str, mapping: str | None = None):
    params = {"account_id": str(account.id)}
    if mapping:
        params["mapping"] = mapping
    r = await api_client.post(
        f"/api/v1/{budget.id}/import/csv/preview",
        params=params,
        files={"file": ("export.csv", csv.encode(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _import(api_client, budget, account, csv: str, mapping: str | None = None):
    params = {"account_id": str(account.id)}
    if mapping:
        params["mapping"] = mapping
    r = await api_client.post(
        f"/api/v1/{budget.id}/import/csv",
        params=params,
        files={"file": ("export.csv", csv.encode(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_preview_names_the_columns_it_guessed(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()

    body = await _preview(api_client, budget, account, HEADER + "2026-01-05,Harborstone,42.10,\n")

    assert body["headers"] == ["Posted Date", "Description", "Debit", "Credit"]
    # Echoed back, because a guess the user did not make is one they must see.
    assert body["mapping"]["date"] == "Posted Date"
    assert body["mapping"]["payee"] == "Description"
    assert body["mapping"]["debit"] == "Debit"
    assert body["date_format"] == "%Y-%m-%d"


async def test_a_debit_column_becomes_money_leaving(db_session, api_client):
    """The shape the single-amount parser could not express at all."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()
    csv = HEADER + "2026-01-05,Shop,42.10,\n2026-01-06,Payroll,,1200.00\n"

    body = await _preview(api_client, budget, account, csv)

    amounts = [Decimal(r["amount"]) for r in body["sample"]]
    assert amounts == [Decimal("-42.10"), Decimal("1200.00")]


async def test_the_second_export_is_almost_all_duplicates(db_session, api_client):
    """The case that made the preview worth building: next month's export from
    the same bank overlaps last month's."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()

    january = HEADER + "2026-01-05,Shop,42.10,\n2026-01-06,Cafe,8.00,\n"
    assert (await _import(api_client, budget, account, january))["imported"] == 2

    overlapping = january + "2026-02-01,Shop,15.00,\n"
    body = await _preview(api_client, budget, account, overlapping)

    assert body["total_rows"] == 3
    assert body["duplicate_rows"] == 2
    assert body["new_rows"] == 1
    # Row by row, so the sample shows WHICH ones.
    assert [r["duplicate"] for r in body["sample"]] == [True, True, False]


async def test_importing_the_same_file_twice_writes_nothing_the_second_time(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()
    csv = HEADER + "2026-01-05,Shop,42.10,\n"

    first = await _import(api_client, budget, account, csv)
    second = await _import(api_client, budget, account, csv)

    assert first["imported"] == 1
    assert second["imported"] == 0
    assert second["skipped"] == 1
    # No batch means nothing to undo, which is the honest answer.
    assert second["batch_id"] is None


async def test_the_preview_and_the_import_agree(db_session, api_client):
    """One parser, two callers: what the preview promised is what lands."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()
    csv = HEADER + "2026-01-05,Shop,42.10,\n2026-01-06,,,\n2026-01-07,Cafe,8.00,\n"

    preview = await _preview(api_client, budget, account, csv)
    result = await _import(api_client, budget, account, csv)

    assert preview["new_rows"] == result["imported"]
    assert len(preview["skipped"]) == result["skipped"]


async def test_a_chosen_mapping_overrides_the_guess(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()
    # Headers the hints do not know; the user says which is which.
    csv = "Fecha,Concepto,Importe\n2026-01-05,Tienda,-42.10\n"
    mapping = '{"date": "Fecha", "payee": "Concepto", "amount": "Importe"}'

    body = await _preview(api_client, budget, account, csv, mapping)

    assert body["new_rows"] == 1
    assert body["sample"][0]["payee"] == "Tienda"


async def test_an_unmappable_file_is_refused_with_a_reason(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()

    r = await api_client.post(
        f"/api/v1/{budget.id}/import/csv/preview",
        params={"account_id": str(account.id)},
        files={"file": ("x.csv", b"Fecha,Importe\n2026-01-05,-1\n", "text/csv")},
    )

    assert r.status_code == 400
    assert "date column" in r.json()["detail"]


async def test_a_category_column_files_into_an_existing_envelope(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    group = await create_category_group(db_session, budget, "Everyday")
    await create_category(db_session, budget, group, "Groceries")
    await db_session.commit()

    csv = "Date,Description,Amount,Category\n2026-01-05,Shop,-42.10,Groceries\n"
    result = await _import(api_client, budget, account, csv)
    assert result["imported"] == 1

    txns = (await api_client.get(f"/api/v1/accounts/{account.id}/transactions")).json()
    assert txns[0]["category_id"] is not None


async def test_an_unknown_category_lands_uncategorized_rather_than_inventing_one(
    db_session, api_client
):
    """A bank's idea of "Travel" is not this budget's envelope, and inventing
    envelopes from a file is how a category list becomes unusable."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()

    csv = "Date,Description,Amount,Category\n2026-01-05,Shop,-42.10,Sundries\n"
    assert (await _import(api_client, budget, account, csv))["imported"] == 1

    groups = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
    assert not any(c["name"] == "Sundries" for c in groups)
