"""Export a budget, import it as a new one, and prove the copy is the budget.

The acceptance test for the duplication flow. Three things have to hold, and
the third is the one people actually feel:

1. Every carried table arrives at the same row count; every omitted table is
   empty in the copy.
2. The golden invariants pass on both. ``assert_transfer_integrity`` and
   ``assert_split_integrity`` are whole-database rather than budget-scoped —
   they scan every live transfer leg for mutual linkage and a zero sum — so a
   transfer_id that was not remapped fails there immediately, without this
   file having to know how remapping works.
3. The budget summary agrees. Category balances are compared after mapping
   id -> (group name, category name): the ids legitimately differ, and the API
   must not grow a 100k-entry id map just to make a test easier.
"""

import io
import json
import zipfile
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select

from igab.db.models import Budget, BudgetSnapshotMeta, ChangeLog
from igab.domain.snapshot_format import SNAPSHOT_OMITTED, carried_tables

from .budget_rows import assert_fully_populated, row_counts
from .factories import make_services
from .full_budget import MONTH, build_full_budget, mark_snapshot_cache_valid
from .invariants import assert_financial_invariants, assert_no_cross_budget_references

# The month the fixture books into, plus its neighbours: carry-over means a
# copy can agree in one month and disagree in the next.
_PREVIOUS = (MONTH - timedelta(days=1)).replace(day=1)
_NEXT = (MONTH + timedelta(days=32)).replace(day=1)
MONTHS = [_PREVIOUS, MONTH, _NEXT]


async def _export(api_client, budget_id) -> bytes:
    resp = await api_client.get(f"/api/v1/budgets/{budget_id}/snapshot")
    assert resp.status_code == 200, resp.text
    return resp.content


async def _import(api_client, body: bytes, name: str | None = None):
    data = {"name": name} if name else None
    resp = await api_client.post(
        "/api/v1/budgets/import-snapshot",
        files={"file": ("snapshot.igab.zip", body, "application/zip")},
        data=data,
    )
    return resp


async def _duplicate(api_client, db_session, name: str | None = None):
    """A fully-populated budget and the copy made from its snapshot."""
    source = await build_full_budget(db_session, api_client.test_user)
    await mark_snapshot_cache_valid(db_session, source.id)
    resp = await _import(api_client, await _export(api_client, source.id), name)
    assert resp.status_code == 201, resp.text
    return source, resp.json()


class TestTheCopyIsTheBudget:
    async def test_every_carried_table_arrives_at_the_same_count(self, api_client, db_session):
        source, result = await _duplicate(api_client, db_session)
        before = await row_counts(db_session, source.id)
        assert_fully_populated(before)
        after = await row_counts(db_session, UUID(result["budget_id"]))

        carried = {t.name for t in carried_tables()}
        for name in carried:
            assert after[name] == before[name], name

    async def test_omitted_tables_are_empty_in_the_copy(self, api_client, db_session):
        """Not carried means not there — and each one has a reason on record."""
        source, result = await _duplicate(api_client, db_session)
        after = await row_counts(db_session, UUID(result["budget_id"]))
        for name in SNAPSHOT_OMITTED:
            if name == "budget_members":
                continue  # the importer grants ownership; see below
            assert after[name] == 0, name

    async def test_the_importer_owns_what_they_imported(self, api_client, db_session):
        """budget_members is omitted so the exporter's collaborators do not
        come along — but the copy still needs exactly one owner."""
        _, result = await _duplicate(api_client, db_session)
        after = await row_counts(db_session, UUID(result["budget_id"]))
        assert after["budget_members"] == 1

    async def test_both_budgets_pass_the_golden_invariants(self, api_client, db_session):
        source, result = await _duplicate(api_client, db_session)
        await assert_financial_invariants(db_session, source.id)
        await assert_financial_invariants(db_session, UUID(result["budget_id"]))

    async def test_nothing_in_the_copy_points_at_the_original(self, api_client, db_session):
        source, result = await _duplicate(api_client, db_session)
        await assert_no_cross_budget_references(db_session, UUID(result["budget_id"]))
        await assert_no_cross_budget_references(db_session, source.id)

    async def test_the_summary_agrees_month_by_month(self, api_client, db_session):
        source, result = await _duplicate(api_client, db_session)
        service = make_services(db_session).budgets

        copy_id = UUID(result["budget_id"])
        for month in MONTHS:
            original = await service.get_budget_summary(source.id, month)
            copy = await service.get_budget_summary(copy_id, month)
            assert await _by_name(db_session, original, source.id) == await _by_name(
                db_session, copy, copy_id
            ), month
            assert original.to_be_assigned == copy.to_be_assigned, month
            assert original.total_overspent == copy.total_overspent, month


class TestTheIdsThatHaveNoForeignKey:
    async def test_the_soft_references_are_remapped(self, api_client, db_session):
        """import_batch_id and scheduled_transaction_id have no FK to declare
        them, so nothing in the database would have complained."""
        source, result = await _duplicate(api_client, db_session)
        copy_id = UUID(result["budget_id"])

        transactions = _table("transactions")
        schedules = _table("scheduled_transactions")
        batches = _table("import_batches")

        rows = (
            await db_session.execute(
                select(
                    transactions.c.scheduled_transaction_id,
                    transactions.c.import_batch_id,
                ).where(transactions.c.budget_id == copy_id)
            )
        ).all()
        pointed_schedules = {r[0] for r in rows if r[0] is not None}
        pointed_batches = {r[1] for r in rows if r[1] is not None}
        assert pointed_schedules and pointed_batches

        assert source.scheduled_id not in pointed_schedules
        assert source.import_batch_id not in pointed_batches

        copy_schedules = set(
            (
                await db_session.execute(
                    select(schedules.c.id).where(schedules.c.budget_id == copy_id)
                )
            )
            .scalars()
            .all()
        )
        copy_batches = set(
            (await db_session.execute(select(batches.c.id).where(batches.c.budget_id == copy_id)))
            .scalars()
            .all()
        )
        assert pointed_schedules <= copy_schedules
        assert pointed_batches <= copy_batches

    async def test_the_polymorphic_guide_binding_is_remapped(self, api_client, db_session):
        """entity_id points at three different tables depending on a sibling
        column; only the declared vocabulary can resolve it."""
        source, result = await _duplicate(api_client, db_session)
        copy_id = UUID(result["budget_id"])

        bindings = _table("guide_bindings")
        categories = _table("categories")
        bound = (
            (
                await db_session.execute(
                    select(bindings.c.entity_id).where(
                        bindings.c.budget_id == copy_id,
                        bindings.c.entity_type == "category",
                        bindings.c.entity_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert bound
        assert source.category_id not in bound

        copy_categories = set(
            (
                await db_session.execute(
                    select(categories.c.id).where(categories.c.budget_id == copy_id)
                )
            )
            .scalars()
            .all()
        )
        assert set(bound) <= copy_categories

    async def test_the_self_references_survive_the_second_pass(self, api_client, db_session):
        """transfer_id, parent_transaction_id and linked_transaction_id are
        written NULL on insert and filled afterwards; a copy that skipped the
        pass would have a transfer with one leg."""
        _, result = await _duplicate(api_client, db_session)
        copy_id = UUID(result["budget_id"])
        transactions = _table("transactions")

        for column in ("transfer_id", "parent_transaction_id", "linked_transaction_id"):
            count = (
                await db_session.execute(
                    select(func.count())
                    .select_from(transactions)
                    .where(
                        transactions.c.budget_id == copy_id,
                        transactions.c[column].is_not(None),
                    )
                )
            ).scalar_one()
            assert count > 0, column


class TestWhatACopyMustNotInherit:
    async def test_the_bank_link_is_dropped(self, api_client, db_session):
        """Two accounts sharing a simplefin_account_id means one sync writes
        the same rows into both budgets."""
        _, result = await _duplicate(api_client, db_session)
        accounts = _table("accounts")
        rows = (
            await db_session.execute(
                select(
                    accounts.c.simplefin_account_id,
                    accounts.c.first_sync_complete,
                ).where(accounts.c.budget_id == UUID(result["budget_id"]))
            )
        ).all()
        assert rows
        assert all(r[0] is None for r in rows)
        assert all(r[1] is False for r in rows)

    async def test_row_level_sync_provenance_is_kept(self, api_client, db_session):
        """sync_id is scoped by account_id, so it cannot collide across
        budgets — and keeping it means dedup still works if the copy is later
        linked to the same bank."""
        _, result = await _duplicate(api_client, db_session)
        transactions = _table("transactions")
        synced = (
            await db_session.execute(
                select(func.count())
                .select_from(transactions)
                .where(
                    transactions.c.budget_id == UUID(result["budget_id"]),
                    transactions.c.sync_id.is_not(None),
                )
            )
        ).scalar_one()
        assert synced > 0

    async def test_no_undo_history_is_invented(self, api_client, db_session):
        """A change_log row here would offer to undo something that never
        happened on this installation."""
        _, result = await _duplicate(api_client, db_session)
        count = (
            await db_session.execute(
                select(func.count())
                .select_from(ChangeLog)
                .where(ChangeLog.budget_id == UUID(result["budget_id"]))
            )
        ).scalar_one()
        assert count == 0

    async def test_the_derived_cache_is_absent_so_it_rebuilds(self, api_client, db_session):
        """Absence *is* the invalidation — SnapshotRepository.is_valid returns
        False with no meta row, so the first summary read rebuilds. The
        importer must not rely on db/invalidation's hooks: they short-circuit
        on Core insert(Table), which is exactly what it uses."""
        _, result = await _duplicate(api_client, db_session)
        copy_id = UUID(result["budget_id"])

        meta = (
            await db_session.execute(
                select(func.count())
                .select_from(BudgetSnapshotMeta)
                .where(BudgetSnapshotMeta.budget_id == copy_id)
            )
        ).scalar_one()
        assert meta == 0

        summary = await make_services(db_session).budgets.get_budget_summary(copy_id, MONTHS[-1])
        assert summary is not None


class TestNaming:
    async def test_a_copy_beside_its_original_gets_a_free_name(self, api_client, db_session):
        source, result = await _duplicate(api_client, db_session)
        assert result["budget_name"] == f"{source.budget.name} 2"

    async def test_a_requested_name_is_used(self, api_client, db_session):
        _, result = await _duplicate(api_client, db_session, name="Experiment")
        assert result["budget_name"] == "Experiment"


class TestNothingIsWrittenWhenTheFileIsRefused:
    async def test_a_newer_format_version_leaves_the_database_alone(self, api_client, db_session):
        source = await build_full_budget(db_session, api_client.test_user)
        body = _rewrite_manifest(await _export(api_client, source.id), format_version=99)
        before = (await db_session.execute(select(func.count()).select_from(Budget))).scalar_one()

        resp = await _import(api_client, body)
        assert resp.status_code == 400
        after = (await db_session.execute(select(func.count()).select_from(Budget))).scalar_one()
        assert after == before

    async def test_a_member_the_manifest_does_not_declare_is_refused(self, api_client, db_session):
        """A file assembled by something other than this app: the extra rows
        would be silently ignored by a loader that reads only the manifest."""
        source = await build_full_budget(db_session, api_client.test_user)
        body = _with_extra_member(await _export(api_client, source.id))
        before = (await db_session.execute(select(func.count()).select_from(Budget))).scalar_one()

        resp = await _import(api_client, body)
        assert resp.status_code == 400
        assert "does not declare" in resp.json()["detail"]
        after = (await db_session.execute(select(func.count()).select_from(Budget))).scalar_one()
        assert after == before

    async def test_a_dangling_reference_fails_loudly(self, api_client, db_session):
        """Never a silent NULL: a budget that looks imported and is quietly
        missing its links is the failure this feature exists to rule out."""
        source = await build_full_budget(db_session, api_client.test_user)
        body = _drop_rows(await _export(api_client, source.id), "payees")
        before = (await db_session.execute(select(func.count()).select_from(Budget))).scalar_one()

        resp = await _import(api_client, body)
        assert resp.status_code == 400
        assert "not in the file" in resp.json()["detail"]
        after = (await db_session.execute(select(func.count()).select_from(Budget))).scalar_one()
        assert after == before


class TestSeeding:
    async def test_the_custom_account_type_travels(self, api_client, db_session):
        _, result = await _duplicate(api_client, db_session)
        types = _table("account_types")
        keys = (
            (
                await db_session.execute(
                    select(types.c.key).where(types.c.budget_id == UUID(result["budget_id"]))
                )
            )
            .scalars()
            .all()
        )
        assert "crypto_wallet" in keys

    async def test_seeding_after_the_rows_does_not_duplicate_the_builtins(
        self, api_client, db_session
    ):
        """The YNAB importer seeds before creating rows; copying that here
        collides with the snapshot's own builtin rows on
        uq_account_type_budget_key."""
        source, result = await _duplicate(api_client, db_session)
        types = _table("account_types")

        def keys_for(budget_id):
            return select(types.c.key).where(types.c.budget_id == budget_id)

        original = sorted((await db_session.execute(keys_for(source.id))).scalars().all())
        copy_keys = keys_for(UUID(result["budget_id"]))
        copy = sorted((await db_session.execute(copy_keys)).scalars().all())
        assert copy == original
        assert len(copy) == len(set(copy))


def _table(name):
    from igab.db.models import Base

    return Base.metadata.tables[name]


async def _by_name(session, summary, budget_id) -> dict[tuple[str, str], tuple]:
    """Category balances keyed by (group name, category name).

    The ids legitimately differ between an original and its copy, and the API
    must not return a 100k-entry id map just to make a test easier.
    """
    categories = _table("categories")
    groups = _table("category_groups")
    rows = (
        await session.execute(
            select(categories.c.id, categories.c.name, groups.c.name)
            .select_from(categories.join(groups, categories.c.category_group_id == groups.c.id))
            .where(categories.c.budget_id == budget_id)
        )
    ).all()
    names = {row[0]: (row[2], row[1]) for row in rows}
    return {
        names[balance.category_id]: (balance.assigned, balance.activity, balance.available)
        for balance in summary.category_balances
    }


def _rewrite_manifest(body: bytes, **overrides) -> bytes:
    return _rebuild(body, lambda item, data: _patch_manifest(item, data, overrides))


def _patch_manifest(item: str, data: bytes, overrides: dict) -> bytes:
    if item != "manifest.json":
        return data
    manifest = json.loads(data)
    manifest.update(overrides)
    return json.dumps(manifest).encode()


def _with_extra_member(body: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(body)) as source, zipfile.ZipFile(out, "w") as target:
        for item in source.namelist():
            target.writestr(item, source.read(item))
        target.writestr("tables/smuggled.ndjson", '{"id": "x"}\n')
    return out.getvalue()


def _drop_rows(body: bytes, table_name: str) -> bytes:
    """Empty one member without touching the manifest — a file that says it
    carries payees and does not."""

    def edit(item: str, data: bytes) -> bytes:
        return b"" if item == f"tables/{table_name}.ndjson" else data

    return _rebuild(body, edit)


def _rebuild(body: bytes, edit) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(body)) as source, zipfile.ZipFile(out, "w") as target:
        for item in source.namelist():
            target.writestr(item, edit(item, source.read(item)))
    return out.getvalue()
