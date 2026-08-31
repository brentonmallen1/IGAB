"""The migration chain must build the schema the ORM expects.

The rest of the suite gets its schema from `Base.metadata.create_all`
(tests/integration/conftest.py), so migrations are never executed. That leaves
a hole: a model change without a matching migration passes every test and then
fails in production, where alembic is what actually runs (`alembic upgrade head`
is the API image's CMD).

This closes it by building the schema both ways in throwaway databases and
diffing them — columns, nullability, unique constraints, foreign keys and their
ondelete. It is slower than the rest of the suite, and worth it: the failure it
catches is one nothing else can see.
"""

import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from igab.db.models import Base

_BASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://igab:changeme@localhost:5432/igab")

#: Alembic owns this one; it is not in the models.
_ALEMBIC_TABLE = "alembic_version"


def _url(database: str) -> str:
    return (
        make_url(_BASE_URL)
        .set(database=database, drivername="postgresql+psycopg2")
        .render_as_string(hide_password=False)
    )


@pytest.fixture
def scratch_dbs():
    """Two empty databases, dropped afterwards whatever happens."""
    names = [f"igab_schema_{uuid.uuid4().hex[:8]}" for _ in range(2)]
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for n in names:
            conn.execute(text(f'CREATE DATABASE "{n}"'))
    try:
        yield names
    finally:
        with admin.connect() as conn:
            for n in names:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{n}" WITH (FORCE)'))
        admin.dispose()


def _run_migrations(database: str) -> None:
    """Run the chain in a subprocess with DATABASE_URL pointed at the scratch db.

    In-process will not do. alembic/env.py overwrites `sqlalchemy.url` from
    `settings.DATABASE_URL`, so `cfg.set_main_option` is ignored and the chain
    runs against whatever the settings default is — the developer's real
    database. A subprocess is also what production does.
    """
    assert database.startswith("igab_schema_"), (
        f"refusing to migrate {database!r}: this test only ever touches its own throwaway databases"
    )
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env = {
        **os.environ,
        "DATABASE_URL": make_url(_BASE_URL)
        .set(database=database)
        .render_as_string(hide_password=False),
        "PYTHONPATH": os.path.join(root, "src"),
    }
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"


def _shape(engine, table: str) -> dict:
    insp = inspect(engine)
    return {
        "columns": {c["name"]: (str(c["type"]), c["nullable"]) for c in insp.get_columns(table)},
        "unique": {u["name"] for u in insp.get_unique_constraints(table)},
        "foreign_keys": {
            (
                f["referred_table"],
                tuple(f["constrained_columns"]),
                f["options"].get("ondelete"),
            )
            for f in insp.get_foreign_keys(table)
        },
    }


def test_migrations_produce_the_model_schema(scratch_dbs):
    migrated_db, model_db = scratch_dbs

    migrated = create_engine(_url(migrated_db))
    _run_migrations(migrated_db)

    modelled = create_engine(_url(model_db))
    Base.metadata.create_all(modelled)

    try:
        migrated_tables = set(inspect(migrated).get_table_names()) - {_ALEMBIC_TABLE}
        model_tables = set(inspect(modelled).get_table_names())

        assert migrated_tables == model_tables, (
            "migrations and models disagree about which tables exist — "
            f"only migrated: {sorted(migrated_tables - model_tables)}; "
            f"only modelled: {sorted(model_tables - migrated_tables)}"
        )

        drift = {}
        for table in sorted(model_tables):
            a, b = _shape(migrated, table), _shape(modelled, table)
            if a != b:
                drift[table] = {
                    key: {"migrated": a[key], "models": b[key]} for key in a if a[key] != b[key]
                }
        assert not drift, f"migrated schema differs from the models: {drift}"
    finally:
        migrated.dispose()
        modelled.dispose()
