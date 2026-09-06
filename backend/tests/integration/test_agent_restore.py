"""The restore path, run for real against a scratch database.

The incident this pins: a restore of a dump taken before the `import_anchors`
migration reported "restore complete", and the app never came back. The agent
ran ``pg_restore --clean``, which drops only what the DUMP knows about — so
every table added since the dump stayed in the database while
``alembic_version`` was rolled back behind it. On restart Alembic re-ran the
migration that creates ``import_anchors``, hit DuplicateTable, and the API's
run script took the AIO container down with it.

``restore_into_db`` in scripts/db-backup.sh now drops the schema first. These
tests build that exact situation with two invented tables and check that the
newer one is gone afterwards. They exercise the shell script itself — the
in-app restore and ``just restore`` both end in that one function, and a test
of a Python re-statement of it would test nothing that ships.

Needs ``psql``/``pg_dump``/``pg_restore`` on PATH (the CI runner has them;
a laptop without them skips).
"""

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .conftest import _BASE_URL

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "db-backup.sh"

pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("psql", "pg_dump", "pg_restore")),
    reason="postgres client tools not on PATH",
)


@pytest.fixture
def scratch_db():
    """A throwaway database plus the PG* environment that reaches it."""
    url = make_url(_BASE_URL)
    name = f"igab_restore_{uuid.uuid4().hex[:8]}"
    admin_url = url.set(database="postgres", drivername="postgresql+psycopg2")
    admin = create_engine(
        admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    env = {
        **os.environ,
        "PGHOST": url.host or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
        "PGDATABASE": name,
    }
    try:
        yield name, env
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def psql(env: dict, sql: str) -> str:
    out = subprocess.run(
        ["psql", "-X", "-tA", "-v", "ON_ERROR_STOP=1", "-c", sql],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def tables(env: dict) -> set[str]:
    rows = psql(env, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return set(filter(None, rows.splitlines()))


def old_schema_dump(env: dict, path: Path) -> None:
    """A budget as it stood BEFORE a table-adding migration."""
    psql(env, "CREATE TABLE envelopes (id int PRIMARY KEY, name text)")
    psql(env, "INSERT INTO envelopes VALUES (1, 'Groceries'), (2, 'Rent')")
    psql(env, "CREATE TABLE alembic_version (version_num text PRIMARY KEY)")
    psql(env, "INSERT INTO alembic_version VALUES ('before_anchors')")
    subprocess.run(["pg_dump", "-Fc", "-f", str(path)], env=env, check=True)


def migrate_forward(env: dict) -> None:
    """What the app did after that dump: one new table, version bumped."""
    psql(env, "CREATE TABLE import_anchors (id int PRIMARY KEY)")
    psql(env, "UPDATE alembic_version SET version_num = 'after_anchors'")
    psql(env, "INSERT INTO envelopes VALUES (3, 'Entered after the backup')")


def restore_file(env: dict, *args: str, stdin=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(SCRIPT), "restore-file", *args],
        env={**env, "BACKUP_DIR": env.get("BACKUP_DIR", "/nonexistent")},
        capture_output=True,
        text=True,
        stdin=stdin,
    )


class TestRestoreIntoDb:
    def test_a_table_the_dump_does_not_know_about_is_gone(self, scratch_db, tmp_path):
        """The bug, by name. --clean would have left import_anchors standing."""
        _, env = scratch_db
        dump = tmp_path / "igab-20260904-150356.dump"
        old_schema_dump(env, dump)
        migrate_forward(env)
        assert "import_anchors" in tables(env)

        result = restore_file(env, str(dump))

        assert result.returncode == 0, result.stderr
        assert tables(env) == {"envelopes", "alembic_version"}

    def test_alembic_version_agrees_with_the_tables_left_behind(self, scratch_db, tmp_path):
        """The half that made the crash a loop: a version behind the schema.
        Now the version and the tables come from the same dump."""
        _, env = scratch_db
        dump = tmp_path / "igab-20260904-150356.dump"
        old_schema_dump(env, dump)
        migrate_forward(env)

        restore_file(env, str(dump))

        assert psql(env, "SELECT version_num FROM alembic_version") == "before_anchors"

    def test_rows_entered_after_the_backup_are_gone_and_the_backup_rows_are_back(
        self, scratch_db, tmp_path
    ):
        _, env = scratch_db
        dump = tmp_path / "igab-20260904-150356.dump"
        old_schema_dump(env, dump)
        migrate_forward(env)

        restore_file(env, str(dump))

        assert psql(env, "SELECT count(*) FROM envelopes") == "2"

    def test_the_dump_can_arrive_on_stdin(self, scratch_db, tmp_path):
        """`just restore` pipes the file (or an age-decrypted stream) into the
        db container; the script must accept it the same way."""
        _, env = scratch_db
        dump = tmp_path / "igab-20260904-150356.dump"
        old_schema_dump(env, dump)
        migrate_forward(env)

        with dump.open("rb") as fh:
            result = restore_file(env, "-", stdin=fh)

        assert result.returncode == 0, result.stderr
        assert tables(env) == {"envelopes", "alembic_version"}

    def test_a_restore_of_the_same_schema_still_round_trips(self, scratch_db, tmp_path):
        """Dropping the schema must not break the ordinary case."""
        _, env = scratch_db
        dump = tmp_path / "igab-20260904-150356.dump"
        old_schema_dump(env, dump)
        psql(env, "DELETE FROM envelopes")

        result = restore_file(env, str(dump))

        assert result.returncode == 0, result.stderr
        assert psql(env, "SELECT count(*) FROM envelopes") == "2"


class TestRestoreFileSubcommand:
    def test_a_missing_path_is_a_usage_error_not_a_hang(self, scratch_db):
        """Without the argument check the script would fall through into the
        agent loop and wait forever for commands."""
        _, env = scratch_db
        result = restore_file(env)
        assert result.returncode == 2
        assert "usage" in result.stderr

    def test_an_unknown_argument_is_refused(self, scratch_db):
        _, env = scratch_db
        result = subprocess.run(
            ["sh", str(SCRIPT), "frobnicate"], env=env, capture_output=True, text=True
        )
        assert result.returncode == 2
        assert "unknown argument" in result.stderr

    def test_a_failed_restore_reports_failure(self, scratch_db, tmp_path):
        """The agent reads the exit status to decide between "restore
        complete" and an error the overlay can show."""
        _, env = scratch_db
        bogus = tmp_path / "igab-20260904-150356.dump"
        bogus.write_bytes(b"not a pg_dump archive")
        result = restore_file(env, str(bogus))
        assert result.returncode != 0
