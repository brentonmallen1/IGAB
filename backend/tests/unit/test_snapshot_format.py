"""The snapshot codec and the rules for reading an old file.

The round-trip is parametrized over **every column in the schema**, so a new
column type fails here in milliseconds rather than in an integration run — or,
worse, a year later when someone restores the file.

No database: this is the pure half of the feature (CLAUDE.md — split pure from
wired), and every compatibility branch is a one-line test because of it.
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Column, LargeBinary, MetaData, Table

from igab.db.budget_scope import budget_tables
from igab.db.models import Base
from igab.domain.snapshot_format import (
    FORMAT,
    MIN_SUPPORTED_REVISION,
    MIN_SUPPORTED_VERSION,
    REDACT_ON_NEW_BUDGET,
    SNAPSHOT_OMITTED,
    VERSION,
    AttachmentSummary,
    SnapshotManifest,
    UnsupportedColumnType,
    carried_tables,
    check_compatibility,
    column_kind,
    decode_row,
    decode_value,
    encode_row,
    encode_value,
    exported_columns,
)

METADATA = Base.metadata

SAMPLES = {
    "uuid": UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7"),
    "decimal": Decimal("100.0000"),
    "datetime": datetime(2026, 8, 29, 13, 45, 7, tzinfo=UTC),
    "date": date(2026, 8, 29),
    "bool": True,
    "int": 7,
    "float": 1.5,
    "str": "Harborstone",
    "json": {"note": "fictional", "rows": [1, 2, 3]},
}

ALL_COLUMNS = [
    (f"{table.name}.{column.name}", table, column)
    for table in METADATA.sorted_tables
    for column in table.columns
]


def _revision_history() -> list[str]:
    """Oldest first, with MIN_SUPPORTED_REVISION in the middle."""
    return ["aaaa0001", "bbbb0002", MIN_SUPPORTED_REVISION, "dddd0004", "eeee0005"]


def _manifest(**overrides) -> SnapshotManifest:
    base = dict(
        format=FORMAT,
        format_version=VERSION,
        alembic_revision="dddd0004",
        app_version="2026.08.29",
        exported_at="2026-08-29T13:45:07+00:00",
        source_budget_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
        budget_name="Household",
        columns={t.name: list(exported_columns(t)) for t in carried_tables(METADATA)},
        row_counts={t.name: 1 for t in carried_tables(METADATA)},
        omitted_tables=dict(SNAPSHOT_OMITTED),
    )
    base.update(overrides)
    return SnapshotManifest(**base)


class TestTheCodecCoversTheWholeSchema:
    @pytest.mark.parametrize("label,table,column", ALL_COLUMNS, ids=[c[0] for c in ALL_COLUMNS])
    def test_every_column_round_trips_through_json(self, label, table, column):
        """Encode → JSON → parse → decode gives back what went in.

        Through JSON deliberately: encoding to something json.dumps cannot
        serialize would pass a narrower test and fail on the first export.
        """
        value = SAMPLES[column_kind(column)]
        wire = json.loads(json.dumps({column.name: encode_value(column, value)}))
        assert decode_value(column, wire[column.name]) == value

    @pytest.mark.parametrize("label,table,column", ALL_COLUMNS, ids=[c[0] for c in ALL_COLUMNS])
    def test_none_survives_every_column(self, label, table, column):
        assert encode_value(column, None) is None
        assert decode_value(column, None) is None

    def test_an_unknown_column_type_raises_rather_than_stringifying(self):
        table = Table("made_up", MetaData(), Column("blob", LargeBinary))
        with pytest.raises(UnsupportedColumnType, match="made_up.blob"):
            encode_value(table.c.blob, b"x")


class TestMoneyIsNeverAFloat:
    def test_scale_survives_byte_identically(self):
        column = METADATA.tables["transactions"].c.amount
        assert encode_value(column, Decimal("100.0000")) == "100.0000"
        assert decode_value(column, "100.0000") == Decimal("100.0000")
        assert str(decode_value(column, "100.0000")) == "100.0000"

    def test_amounts_are_written_as_strings(self):
        column = METADATA.tables["transactions"].c.amount
        encoded = encode_value(column, Decimal("-1234.5600"))
        assert isinstance(encoded, str)
        assert not isinstance(encoded, float)

    def test_a_third_of_a_dollar_does_not_drift(self):
        """The case a float would lose. Three decimals of a cent is inside
        Numeric(19, 4), so it must survive exactly."""
        column = METADATA.tables["transactions"].c.amount
        assert decode_value(column, encode_value(column, Decimal("0.3333"))) == Decimal("0.3333")

    def test_latitude_stays_a_float_because_it_is_one(self):
        """Not everything numeric is money — geo columns are Float and must
        not be dragged into Decimal."""
        column = METADATA.tables["transactions"].c.latitude
        assert column_kind(column) == "float"
        assert encode_value(column, 47.6062) == 47.6062


class TestRows:
    def test_a_row_round_trips(self):
        table = METADATA.tables["accounts"]
        row = {
            "id": SAMPLES["uuid"],
            "budget_id": SAMPLES["uuid"],
            "name": "Cascade Point HYSA",
            "simplefin_balance": Decimal("1250.0000"),
            "created_at": SAMPLES["datetime"],
        }
        encoded = encode_row(table, row)
        assert encoded["name"] == "Cascade Point HYSA"
        assert encoded["simplefin_balance"] == "1250.0000"
        decoded = decode_row(table, json.loads(json.dumps(encoded)))
        assert decoded["simplefin_balance"] == Decimal("1250.0000")
        assert decoded["created_at"] == SAMPLES["datetime"]

    def test_encode_row_writes_every_column(self):
        table = METADATA.tables["accounts"]
        assert set(encode_row(table, {})) == set(exported_columns(table))

    def test_decode_row_leaves_out_columns_the_file_lacks(self):
        """A column added since the export must take its schema default, not
        a null that would fail the NOT NULL the compatibility check cleared."""
        table = METADATA.tables["accounts"]
        decoded = decode_row(table, {"id": str(SAMPLES["uuid"]), "name": "Sapphire Visa"})
        assert set(decoded) == {"id", "name"}


class TestWhatIsCarried:
    def test_omitted_tables_are_real_budget_tables_with_reasons(self):
        in_graph = {t.name for t in budget_tables(METADATA)}
        for name, reason in SNAPSHOT_OMITTED.items():
            assert name in in_graph, (
                f"SNAPSHOT_OMITTED names {name}, which is not a budget-owned "
                f"table — omitting it says nothing"
            )
            assert len(reason) > 20, f"SNAPSHOT_OMITTED[{name}] needs a reason"

    def test_carried_is_the_graph_minus_the_omitted(self):
        carried = {t.name for t in carried_tables(METADATA)}
        assert carried == {t.name for t in budget_tables(METADATA)} - set(SNAPSHOT_OMITTED)
        assert not carried & set(SNAPSHOT_OMITTED)

    def test_the_ledger_itself_is_carried(self):
        """A guard against an omission list that quietly grows past its
        purpose: the tables a budget *is* must always be in the file."""
        carried = {t.name for t in carried_tables(METADATA)}
        for name in ("budgets", "accounts", "categories", "transactions", "budget_assignments"):
            assert name in carried

    def test_import_batches_is_carried_so_its_id_can_be_remapped(self):
        """Carrying one row per import makes transactions.import_batch_id
        remappable instead of a dangling id needing a null-out special case."""
        assert "import_batches" in {t.name for t in carried_tables(METADATA)}


class TestSimplefinLinkageIsRedacted:
    def test_every_simplefin_column_on_accounts_is_declared(self):
        """Derived from metadata, so a new simplefin column fails this suite
        instead of leaking a bank link into a duplicated budget."""
        accounts = METADATA.tables["accounts"]
        declared = {column for (table, column) in REDACT_ON_NEW_BUDGET if table == "accounts"}
        missing = sorted(
            column.name
            for column in accounts.columns
            if "simplefin" in column.name and column.name not in declared
        )
        assert not missing, (
            f"{missing} are bank-link columns with no entry in "
            f"REDACT_ON_NEW_BUDGET. A duplicate that keeps them means one sync "
            f"writes the same rows into two budgets."
        )

    def test_the_first_sync_anchor_is_declared_too(self):
        """It does not carry the prefix, and a copy that claims its first sync
        is complete skips the anchoring pass."""
        assert ("accounts", "first_sync_complete") in REDACT_ON_NEW_BUDGET
        assert REDACT_ON_NEW_BUDGET[("accounts", "first_sync_complete")] is False

    def test_every_declared_column_exists(self):
        for table_name, column_name in REDACT_ON_NEW_BUDGET:
            assert column_name in METADATA.tables[table_name].columns

    def test_row_level_provenance_is_kept(self):
        """sync_id / sync_source are scoped by account_id, so they cannot
        collide across budgets — and keeping them means dedup still works if
        the copy is later linked to the same bank."""
        assert ("transactions", "sync_id") not in REDACT_ON_NEW_BUDGET
        assert ("transactions", "sync_source") not in REDACT_ON_NEW_BUDGET


class TestManifestSerialization:
    def test_round_trips_through_json(self):
        manifest = _manifest(attachments=AttachmentSummary(included=False, omitted_count=4))
        again = SnapshotManifest.from_dict(json.loads(json.dumps(manifest.to_dict())))
        assert again.format == FORMAT
        assert again.budget_name == "Household"
        assert again.attachments.omitted_count == 4
        assert again.columns["accounts"] == list(exported_columns(METADATA.tables["accounts"]))

    def test_a_manifest_missing_everything_does_not_explode(self):
        """An uploaded file is untrusted input; reading its manifest must
        produce a refusal, not a KeyError."""
        empty = SnapshotManifest.from_dict({})
        assert not check_compatibility(empty, METADATA).ok


class TestCompatibility:
    def test_a_matching_file_is_accepted_with_nothing_to_say(self):
        result = check_compatibility(
            _manifest(), METADATA, current_revision="dddd0004",
            revision_history=_revision_history(),
        )
        assert result.ok
        assert result.warnings == ()
        assert result.dropped_columns == {}

    def test_a_foreign_format_is_refused(self):
        result = check_compatibility(_manifest(format="ynab.export"), METADATA)
        assert not result.ok
        assert "not an IGAB budget snapshot" in result.refusals[0]

    def test_a_newer_format_version_is_refused(self):
        result = check_compatibility(_manifest(format_version=VERSION + 1), METADATA)
        assert not result.ok
        assert f"v{VERSION + 1}" in result.refusals[0]

    def test_a_prehistoric_format_version_is_refused(self):
        result = check_compatibility(_manifest(format_version=MIN_SUPPORTED_VERSION - 1), METADATA)
        assert not result.ok

    def test_a_column_gone_from_the_schema_is_dropped_with_a_warning(self):
        columns = {t.name: list(exported_columns(t)) for t in carried_tables(METADATA)}
        columns["accounts"] = [*columns["accounts"], "favourite_colour"]
        result = check_compatibility(_manifest(columns=columns), METADATA)
        assert result.ok
        assert result.dropped_columns["accounts"] == ("favourite_colour",)
        assert any("favourite_colour" in w for w in result.warnings)

    def test_a_nullable_column_missing_from_the_file_is_fine(self):
        columns = {t.name: list(exported_columns(t)) for t in carried_tables(METADATA)}
        columns["accounts"] = [c for c in columns["accounts"] if c != "note"]
        assert check_compatibility(_manifest(columns=columns), METADATA).ok

    def test_a_defaulted_column_missing_from_the_file_is_fine(self):
        columns = {t.name: list(exported_columns(t)) for t in carried_tables(METADATA)}
        columns["accounts"] = [c for c in columns["accounts"] if c != "is_closed"]
        assert check_compatibility(_manifest(columns=columns), METADATA).ok

    def test_a_required_column_missing_from_the_file_is_refused(self):
        columns = {t.name: list(exported_columns(t)) for t in carried_tables(METADATA)}
        columns["accounts"] = [c for c in columns["accounts"] if c != "name"]
        result = check_compatibility(_manifest(columns=columns), METADATA)
        assert not result.ok
        assert any("accounts.name" in r for r in result.refusals)

    def test_a_table_gone_from_the_schema_is_skipped_with_a_warning(self):
        columns = {t.name: list(exported_columns(t)) for t in carried_tables(METADATA)}
        columns["retired_table"] = ["id"]
        result = check_compatibility(_manifest(columns=columns), METADATA)
        assert result.ok
        assert any("retired_table" in w for w in result.warnings)

    def test_a_table_the_file_predates_is_a_warning_not_a_refusal(self):
        columns = {t.name: list(exported_columns(t)) for t in carried_tables(METADATA)}
        del columns["wishlist_items"]
        result = check_compatibility(_manifest(columns=columns), METADATA)
        assert result.ok
        assert any("wishlist_items" in w for w in result.warnings)


class TestRevisions:
    def test_a_revision_mismatch_warns_and_never_refuses(self):
        """Refusing here would make last month's backup unrestorable, which is
        the entire point of having one."""
        result = check_compatibility(
            _manifest(alembic_revision="dddd0004"), METADATA,
            current_revision="eeee0005", revision_history=_revision_history(),
        )
        assert result.ok
        assert any("dddd0004" in w for w in result.warnings)

    def test_a_file_older_than_the_meaning_change_is_refused(self):
        result = check_compatibility(
            _manifest(alembic_revision="aaaa0001"), METADATA,
            current_revision="dddd0004", revision_history=_revision_history(),
        )
        assert not result.ok
        assert MIN_SUPPORTED_REVISION in result.refusals[0]

    def test_the_meaning_change_itself_is_supported(self):
        result = check_compatibility(
            _manifest(alembic_revision=MIN_SUPPORTED_REVISION), METADATA,
            current_revision="dddd0004", revision_history=_revision_history(),
        )
        assert result.ok

    def test_an_unknown_revision_warns_rather_than_refusing(self):
        result = check_compatibility(
            _manifest(alembic_revision="zzzz9999"), METADATA,
            current_revision="dddd0004", revision_history=_revision_history(),
        )
        assert result.ok
        assert any("zzzz9999" in w for w in result.warnings)

    def test_without_a_history_age_cannot_be_judged_so_it_is_not(self):
        """The caller reads the migration scripts; with no history the honest
        answer is a warning, not a guess about ordering."""
        result = check_compatibility(
            _manifest(alembic_revision="aaaa0001"), METADATA, current_revision="dddd0004"
        )
        assert result.ok

    def test_a_file_that_names_no_revision_says_so(self):
        result = check_compatibility(_manifest(alembic_revision=""), METADATA)
        assert result.ok
        assert any("does not say which schema version" in w for w in result.warnings)
