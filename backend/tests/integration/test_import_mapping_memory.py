"""The import mapping step remembers what you told it last time.

A YNAB register export carries no account ids and no types — only names — so
the mapping step asks the same question once per account, and a real export
asks it 47 times. Re-importing the same file asked all 47 again from scratch,
which is what testing an import looks like.

Every account name here is invented (see CLAUDE.md): the point of the test is
the round trip, never a real budget.
"""

import io
import json
import zipfile

from sqlalchemy import select

from igab.db.models import ImportAccountMapping

REGISTER = """Account,Date,Payee,Category Group,Category,Memo,Outflow,Inflow,Cleared
Harborstone Checking,07/01/2026,Northwind Payserv,Inflow,Ready to Assign,,,"2,000.00",Cleared
Harborstone Checking,07/02/2026,Corner Market,Everyday,Groceries,,60.00,,Cleared
Birchwood Property Ferry,07/03/2026,Opening Balance,,,,,"310,000.00",Cleared
Vehicle A Loan,07/04/2026,Opening Balance,,,,"18,400.00",,Cleared
Old Cascade Point HYSA,07/05/2026,Opening Balance,,,,,"1,200.00",Cleared
"""

ALL_ACCOUNTS = {
    "Harborstone Checking",
    "Birchwood Property Ferry",
    "Vehicle A Loan",
    "Old Cascade Point HYSA",
}


def _zip(register: str = REGISTER) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("My Budget - Register.csv", register)
    return buf.getvalue()


def _mapping(**overrides) -> str:
    """The form the mapping screen submits, with sensible answers by default."""
    choices = {
        "Harborstone Checking": {"account_type": "checking", "on_budget": True},
        "Birchwood Property Ferry": {"account_type": "other_asset", "on_budget": False},
        "Vehicle A Loan": {"account_type": "auto_loan", "on_budget": False},
        "Old Cascade Point HYSA": {"account_type": "savings", "on_budget": True},
    }
    for name, patch in overrides.items():
        choices[name.replace("_", " ")] = {**choices[name.replace("_", " ")], **patch}
    return json.dumps(choices)


async def _import(api_client, name: str, mapping: str | None = None, register: str = REGISTER):
    return await api_client.post(
        "/api/v1/budgets/import-ynab",
        data={"name": name, "account_types": mapping if mapping is not None else _mapping()},
        files={"file": ("export.zip", _zip(register), "application/zip")},
    )


async def _preview(api_client, register: str = REGISTER) -> dict:
    resp = await api_client.post(
        "/api/v1/budgets/import/preview",
        files={"file": ("export.zip", _zip(register), "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    return {a["name"]: a for a in resp.json()["ynab"]["accounts"]}


class TestTheSecondImport:
    async def test_arrives_pre_filled(self, api_client):
        """The headline. Before this, every account came back as a guess read
        from its name — and "Birchwood Property Ferry" reads as nothing."""
        assert (await _import(api_client, "First")).status_code == 201

        by_name = await _preview(api_client)
        assert by_name["Vehicle A Loan"]["suggested_type"] == "auto_loan"
        assert by_name["Birchwood Property Ferry"]["suggested_type"] == "other_asset"
        assert by_name["Birchwood Property Ferry"]["suggested_on_budget"] is False
        for name in ALL_ACCOUNTS:
            assert by_name[name]["suggestion_source"] == "remembered", name

    async def test_a_first_import_has_nothing_to_remember(self, api_client):
        by_name = await _preview(api_client)
        for name in ALL_ACCOUNTS:
            assert by_name[name]["suggestion_source"] == "heuristic", name

    async def test_the_check_badge_is_not_silenced(self, api_client):
        """A name we could not read last time is still a name we cannot read.
        What was remembered is a keystroke, and the keystroke may have been the
        pre-filled guess nobody looked at."""
        assert (await _import(api_client, "First")).status_code == 201
        by_name = await _preview(api_client)
        assert by_name["Birchwood Property Ferry"]["needs_review"] is True
        assert by_name["Harborstone Checking"]["needs_review"] is False


class TestDisposition:
    async def test_a_skipped_account_is_remembered_as_skipped(self, api_client):
        """The choice deriving from the imported accounts could never store: a
        skipped account is never created, so there is no row to read back."""
        mapping = _mapping(Old_Cascade_Point_HYSA={"skip": True})
        assert (await _import(api_client, "First", mapping)).status_code == 201

        by_name = await _preview(api_client)
        assert by_name["Old Cascade Point HYSA"]["suggested_skip"] is True
        assert by_name["Harborstone Checking"]["suggested_skip"] is False

    async def test_the_type_of_a_skipped_account_survives(self, api_client):
        """`type_map` drops every skipped account, so remembering from there
        would forget that this was typed `savings` — and pre-fill
        checking/on-budget the moment someone un-skipped it."""
        mapping = _mapping(Old_Cascade_Point_HYSA={"skip": True})
        assert (await _import(api_client, "First", mapping)).status_code == 201

        remembered = (await _preview(api_client))["Old Cascade Point HYSA"]
        assert remembered["suggested_type"] == "savings"
        assert remembered["suggested_skip"] is True

    async def test_a_closed_account_is_remembered_as_closed(self, api_client):
        mapping = _mapping(Old_Cascade_Point_HYSA={"close": True})
        assert (await _import(api_client, "First", mapping)).status_code == 201

        remembered = (await _preview(api_client))["Old Cascade Point HYSA"]
        assert (remembered["suggested_close"], remembered["suggested_skip"]) == (True, False)


class TestWhatItOutlives:
    async def test_memory_outlives_the_budget_it_came_from(self, api_client):
        """The whole reason this is a table and not a read of the accounts a
        previous import created. Deleting the budget is exactly what testing an
        import looks like, and accounts cascade with it."""
        created = await _import(api_client, "First")
        assert created.status_code == 201
        budget_id = created.json()["budget"]["id"]

        deleted = await api_client.delete(f"/api/v1/budgets/{budget_id}")
        assert deleted.status_code in (200, 204), deleted.text

        by_name = await _preview(api_client)
        assert by_name["Vehicle A Loan"]["suggested_type"] == "auto_loan"
        assert by_name["Vehicle A Loan"]["suggestion_source"] == "remembered"

    async def test_a_failed_import_remembers_nothing(self, api_client, db_session):
        """The choices were never acted on. The write shares the import's
        transaction, so the rollback takes it too."""
        assert (await _import(api_client, "Taken")).status_code == 201
        await db_session.execute(select(ImportAccountMapping))
        before = len((await db_session.execute(select(ImportAccountMapping))).scalars().all())

        clash = await _import(api_client, "Taken", _mapping(Vehicle_A_Loan={"skip": True}))
        assert clash.status_code == 409

        rows = (await db_session.execute(select(ImportAccountMapping))).scalars().all()
        assert len(rows) == before
        assert all(row.skip is False for row in rows)


class TestKeying:
    async def test_names_match_case_insensitively(self, api_client):
        """The register and the memory are written at different times. The
        importer has always matched account names case-insensitively; the
        memory must agree or it silently never hits."""
        assert (await _import(api_client, "First")).status_code == 201

        shouted = REGISTER.replace("Vehicle A Loan", "VEHICLE A LOAN")
        by_name = await _preview(api_client, shouted)
        assert by_name["VEHICLE A LOAN"]["suggested_type"] == "auto_loan"
        assert by_name["VEHICLE A LOAN"]["suggestion_source"] == "remembered"

    async def test_two_spellings_in_one_file_collapse_to_one_row(self, api_client, db_session):
        """Not realistic, but Postgres raises "ON CONFLICT DO UPDATE command
        cannot affect row a second time" if two VALUES rows share a conflict
        key — and it would raise at the very end, after the import had already
        succeeded."""
        mapping = json.dumps(
            {
                "Harborstone Checking": {"account_type": "checking", "on_budget": True},
                "harborstone checking": {"account_type": "savings", "on_budget": True},
            }
        )
        assert (await _import(api_client, "First", mapping)).status_code == 201

        rows = (
            (
                await db_session.execute(
                    select(ImportAccountMapping).where(
                        ImportAccountMapping.account_key == "harborstone checking"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1

    async def test_re_importing_updates_rather_than_duplicates(self, api_client, db_session):
        assert (await _import(api_client, "First")).status_code == 201
        changed = _mapping(Old_Cascade_Point_HYSA={"account_type": "cash"})
        assert (await _import(api_client, "Second", changed)).status_code == 201

        rows = (
            (
                await db_session.execute(
                    select(ImportAccountMapping).where(
                        ImportAccountMapping.account_key == "old cascade point hysa"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].account_type == "cash"

    async def test_the_casing_last_seen_is_kept(self, api_client, db_session):
        assert (await _import(api_client, "First")).status_code == 201
        row = (
            await db_session.execute(
                select(ImportAccountMapping).where(
                    ImportAccountMapping.account_key == "vehicle a loan"
                )
            )
        ).scalar_one()
        assert row.account_name == "Vehicle A Loan"


class TestForgetting:
    async def test_it_reports_how_many_and_leaves_the_next_preview_guessing(self, api_client):
        """The off switch, and the only one — per person, in the screen where
        the memory is visible."""
        assert (await _import(api_client, "First")).status_code == 201

        forgotten = await api_client.delete("/api/v1/budgets/import/remembered-accounts")
        assert forgotten.status_code == 200
        assert forgotten.json()["forgotten"] == len(ALL_ACCOUNTS)

        by_name = await _preview(api_client)
        for name in ALL_ACCOUNTS:
            assert by_name[name]["suggestion_source"] == "heuristic", name

    async def test_forgetting_nothing_is_not_an_error(self, api_client):
        resp = await api_client.delete("/api/v1/budgets/import/remembered-accounts")
        assert resp.status_code == 200
        assert resp.json()["forgotten"] == 0


class TestTenancy:
    async def test_memory_is_per_user(self, api_client, db_session):
        """One household, two people, two sets of accounts. Asserted at the
        repository rather than through a second client: the API fixture pins
        one signed-in user, and what needs pinning here is the query."""
        from igab.repositories.import_mapping_repo import ImportMappingRepository

        from .factories import create_user

        assert (await _import(api_client, "First")).status_code == 201
        other = await create_user(db_session)

        repo = ImportMappingRepository(db_session)
        assert await repo.get_for_user(api_client.test_user.id)
        assert await repo.get_for_user(other.id) == {}

    async def test_forgetting_is_per_user_too(self, api_client, db_session):
        from igab.repositories.import_mapping_repo import ImportMappingRepository

        from .factories import create_user

        assert (await _import(api_client, "First")).status_code == 201
        other = await create_user(db_session)

        repo = ImportMappingRepository(db_session)
        assert await repo.forget_all(other.id) == 0
        assert await repo.get_for_user(api_client.test_user.id)
