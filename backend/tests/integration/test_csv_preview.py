"""Saying what a CSV would do, before it does it.

The importer already worked; what it never did was speak. A bank export
overlaps the previous one almost every time, so "128 rows, 12 already
imported" is the thing a person needs in front of them — not afterwards, in a
number they cannot check.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Payee, Transaction, TransactionMatch

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
)

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
    assert [r["outcome"] for r in body["sample"]] == ["already_imported", "already_imported", "new"]


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


# ─── The match ladder: a bank file over a history from another app ──────────
#
# The history carries that app's cleaned payees; the bank file carries raw
# descriptors, posted the same day or a few days later. Import ids never
# collide across the two, so before the ladder nearly every line came in as a
# new row beside its own twin.


async def _history(db_session, budget, account, rows, *, cleared="uncleared"):
    """Rows as another app's import leaves them: a cleaned payee, its own
    import id, no bank link."""
    made = []
    for n, (day, amount, name) in enumerate(rows):
        payee = await create_payee(db_session, budget, name)
        made.append(
            await create_transaction(
                db_session,
                budget,
                account,
                amount,
                day,
                payee=payee,
                cleared=cleared,
                import_id=f"other-app:{n}",
            )
        )
    return made


async def _live(db_session, account) -> list[Transaction]:
    await db_session.flush()
    result = await db_session.execute(
        select(Transaction).where(
            Transaction.account_id == account.id, Transaction.is_deleted.is_(False)
        )
    )
    return list(result.scalars())


async def _pending_reviews(api_client, budget) -> list[dict]:
    r = await api_client.get(f"/api/v1/simplefin/matches?budget_id={budget.id}")
    assert r.status_code == 200, r.text
    return r.json()


CLEANED = [
    (date(2026, 1, 3), "-84.12", "Trader Joe's"),
    (date(2026, 1, 5), "2150.00", "Northwind Payserv"),
    (date(2026, 1, 8), "-45.00", "Shell"),
    (date(2026, 1, 9), "-15.49", "Netflix"),
    (date(2026, 1, 12), "-12.40", "Corner Market"),
    (date(2026, 1, 14), "-120.00", "Lawn Service"),
]

#: The same six as the bank exports them: raw descriptors, upper and lower
#: case, posted 0–3 days after the history's dates. The last is a check whose
#: descriptor shares nothing with the payee, a day later — the structural
#: rung of the ladder.
RAW = HEADER + (
    "2026-01-03,TRADER JOE'S #552 SEATTLE WA,84.12,\n"
    "2026-01-07,NORTHWIND PAYSERV DIR DEP,,2150.00\n"
    "2026-01-11,SHELL OIL 57442,45.00,\n"
    "2026-01-10,netflix.com,15.49,\n"
    "2026-01-15,corner market #12,12.40,\n"
    "2026-01-15,CHECK 1043,120.00,\n"
)


async def test_a_bank_file_over_cleaned_history_adds_nothing_and_clears_every_row(
    db_session, api_client
):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Harborstone Checking")
    history = await _history(db_session, budget, account, CLEANED)
    await db_session.commit()

    preview = await _preview(api_client, budget, account, RAW)
    assert preview["new_rows"] == 0
    assert preview["matched_rows"] == 6
    assert preview["confirmed_rows"] == 6
    assert preview["review_rows"] == 0
    assert {r["outcome"] for r in preview["sample"]} == {"matched"}
    assert all(r["confirms"] for r in preview["sample"])

    result = await _import(api_client, budget, account, RAW)
    assert result["imported"] == 0
    assert result["matched"] == 6
    assert result["confirmed"] == 6
    assert result["review"] == 0
    # Clearing six rows is something to undo, so there is a batch.
    assert result["batch_id"] is not None

    live = await _live(db_session, account)
    assert {t.id for t in live} == {t.id for t in history}
    for txn in live:
        await db_session.refresh(txn)
        assert txn.cleared == "cleared"
        # The file's word sits beside the row as provenance, but a file is
        # not a feed: no link is claimed.
        assert txn.bank_amount == txn.amount
        assert txn.bank_posted_date is not None
        assert txn.sync_source is None
        assert txn.has_sync_source is False
    assert await _pending_reviews(api_client, budget) == []
    # Matched lines create no payees: only rows that are written need one.
    raw_payees = (
        await db_session.execute(select(Payee).where(Payee.name == "SHELL OIL 57442"))
    ).all()
    assert raw_payees == []


async def test_genuinely_new_lines_still_import_as_new(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Harborstone Checking")
    await _history(db_session, budget, account, CLEANED[:1])
    await db_session.commit()
    csv = HEADER + (
        "2026-01-03,TRADER JOE'S #552 SEATTLE WA,84.12,\n"
        "2026-01-20,COSTCO WHSE #0001,212.37,\n"
        "2026-01-21,CORNER MARKET #12,7.80,\n"
    )

    preview = await _preview(api_client, budget, account, csv)
    assert [r["outcome"] for r in preview["sample"]] == ["matched", "new", "new"]

    result = await _import(api_client, budget, account, csv)
    assert result["imported"] == 2
    assert result["matched"] == 1

    costco = next(t for t in await _live(db_session, account) if t.amount == Decimal("-212.37"))
    # The bank's own words are kept: what the next file is matched against.
    assert costco.import_description == "COSTCO WHSE #0001"
    assert costco.import_id is not None


async def test_two_identical_charges_against_one_existing_row(db_session, api_client):
    """One row already here, two same-day lines in the file: one is that
    row, the other is a second purchase. Never two matches on one row."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Harborstone Checking")
    await _history(db_session, budget, account, [(date(2026, 1, 12), "-12.40", "Corner Market")])
    await db_session.commit()
    csv = HEADER + ("2026-01-12,CORNER MARKET #12,12.40,\n2026-01-12,CORNER MARKET #12,12.40,\n")

    preview = await _preview(api_client, budget, account, csv)
    assert [r["outcome"] for r in preview["sample"]] == ["matched", "new"]

    result = await _import(api_client, budget, account, csv)
    assert (result["imported"], result["matched"]) == (1, 1)
    assert len(await _live(db_session, account)) == 2


async def test_a_low_confidence_pair_imports_and_queues_a_review(db_session, api_client):
    """Same amount two days apart, descriptors that share nothing: maybe the
    same payment, maybe not. Written, and asked about — exactly as the sync
    asks — never silently merged and never silently doubled."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Harborstone Checking")
    (payment,) = await _history(
        db_session, budget, account, [(date(2026, 1, 10), "-250.00", "Sapphire Visa")]
    )
    await db_session.commit()
    csv = HEADER + "2026-01-12,ACH WEB PMT,250.00,\n"

    preview = await _preview(api_client, budget, account, csv)
    assert preview["review_rows"] == 1
    assert preview["sample"][0]["outcome"] == "review"

    result = await _import(api_client, budget, account, csv)
    assert (result["imported"], result["review"], result["matched"]) == (1, 1, 0)

    reviews = await _pending_reviews(api_client, budget)
    assert len(reviews) == 1
    assert reviews[0]["manual_transaction_id"] == str(payment.id)
    await db_session.refresh(payment)
    assert payment.cleared == "uncleared"


async def test_the_preview_and_the_import_agree_line_by_line(db_session, api_client):
    """Every outcome, including twins inside the file. The preview used to
    skip the in-file suffixing the import does, so one twin already imported
    made the preview call BOTH lines duplicates while the import wrote the
    second."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Harborstone Checking")
    await _history(
        db_session,
        budget,
        account,
        [
            (date(2026, 1, 3), "-84.12", "Trader Joe's"),
            (date(2026, 1, 10), "-250.00", "Sapphire Visa"),
        ],
    )
    await db_session.commit()
    await _import(api_client, budget, account, HEADER + "2026-01-09,COFFEE CART,4.50,\n")

    csv = HEADER + (
        "2026-01-03,TRADER JOE'S #552 SEATTLE WA,84.12,\n"  # matched
        "2026-01-09,COFFEE CART,4.50,\n"  # already imported
        "2026-01-09,COFFEE CART,4.50,\n"  # its twin: new
        "2026-01-12,ACH WEB PMT,250.00,\n"  # review
        "2026-01-20,COSTCO WHSE #0001,212.37,\n"  # new
    )
    expected = ["matched", "already_imported", "new", "review", "new"]

    preview = await _preview(api_client, budget, account, csv)
    assert [r["outcome"] for r in preview["sample"]] == expected
    result = await _import(api_client, budget, account, csv)
    assert result["imported"] == preview["new_rows"] + preview["review_rows"] == 3
    assert result["matched"] == preview["matched_rows"] == 1
    assert result["confirmed"] == preview["confirmed_rows"] == 1
    assert result["review"] == preview["review_rows"] == 1
    assert result["skipped"] == preview["duplicate_rows"] == 1

    # And what landed is what a second look sees: every written line is now
    # already imported, the matched one still matched — with nothing to clear.
    again = await _preview(api_client, budget, account, csv)
    assert [r["outcome"] for r in again["sample"]] == [
        "matched",
        "already_imported",
        "already_imported",
        "already_imported",
        "already_imported",
    ]
    assert again["confirmed_rows"] == 0


async def test_a_reconciled_match_is_left_alone(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Harborstone Checking")
    (row,) = await _history(db_session, budget, account, CLEANED[:1], cleared="reconciled")
    await db_session.commit()
    csv = HEADER + "2026-01-03,TRADER JOE'S #552 SEATTLE WA,84.12,\n"

    preview = await _preview(api_client, budget, account, csv)
    assert preview["sample"][0]["outcome"] == "matched"
    assert preview["sample"][0]["confirms"] is False

    result = await _import(api_client, budget, account, csv)
    assert (result["imported"], result["matched"], result["confirmed"]) == (0, 1, 0)
    assert result["batch_id"] is None
    await db_session.refresh(row)
    assert row.cleared == "reconciled"
    assert row.bank_payee is None
    assert row.import_description is None


async def test_a_synced_match_is_not_rewritten(db_session, api_client):
    """A row the feed linked belongs to the feed. The file is a second
    witness: the line counts as already here, and the feed's own words and
    state stay exactly as the feed left them."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Harborstone Checking")
    payee = await create_payee(db_session, budget, "Trader Joe's")
    synced = await create_transaction(
        db_session,
        budget,
        account,
        "-84.12",
        date(2026, 1, 3),
        payee=payee,
        cleared="uncleared",
        sync_id="feed-1",
        sync_source="simplefin",
        bank_payee="TRADER JOE'S 552",
    )
    await db_session.commit()
    csv = HEADER + "2026-01-04,TRADER JOE'S #552 SEATTLE WA,84.12,\n"

    result = await _import(api_client, budget, account, csv)
    assert (result["imported"], result["matched"], result["confirmed"]) == (0, 1, 0)
    await db_session.refresh(synced)
    assert synced.cleared == "uncleared"
    assert synced.bank_payee == "TRADER JOE'S 552"
    assert synced.bank_posted_date is None
    assert synced.sync_id == "feed-1"


async def test_reimporting_after_accepting_a_review_adds_nothing(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Harborstone Checking")
    await _history(db_session, budget, account, [(date(2026, 1, 10), "-250.00", "Sapphire Visa")])
    await db_session.commit()
    csv = HEADER + "2026-01-12,ACH WEB PMT,250.00,\n"
    await _import(api_client, budget, account, csv)
    (review,) = await _pending_reviews(api_client, budget)

    r = await api_client.post(f"/api/v1/simplefin/matches/{review['id']}/accept")
    assert r.status_code == 204, r.text
    assert len(await _live(db_session, account)) == 1

    again = await _import(api_client, budget, account, csv)
    assert again["imported"] == 0
    assert again["review"] == 0
    assert len(await _live(db_session, account)) == 1
    assert await _pending_reviews(api_client, budget) == []


async def test_a_review_whose_row_was_deleted_is_not_offered(db_session, api_client):
    """Undoing a sync run deletes the rows it wrote and leaves its review
    pairs behind. A question about a row that is gone cannot be answered."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Harborstone Checking")
    kept = await create_transaction(db_session, budget, account, "-9.00", date(2026, 1, 5))
    gone = await create_transaction(
        db_session, budget, account, "-9.00", date(2026, 1, 6), is_deleted=True
    )
    for synced, manual in ((gone, kept), (kept, gone)):
        db_session.add(
            TransactionMatch(
                synced_transaction_id=synced.id,
                manual_transaction_id=manual.id,
                confidence_score=Decimal("0.6"),
            )
        )
    await db_session.commit()

    assert await _pending_reviews(api_client, budget) == []
