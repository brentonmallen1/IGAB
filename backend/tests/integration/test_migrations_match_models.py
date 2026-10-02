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


def _run_migrations(database: str, target: str = "head", *, command: str = "upgrade") -> None:
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
        ["uv", "run", "alembic", command, target],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic {command} {target} failed:\n{result.stderr}"


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
    # The migration side creates btree_gist itself; the model side has to be
    # given it, or `import_anchors`' EXCLUDE ... USING gist cannot be built and
    # the two schemas differ for a reason that is not a drift.
    with modelled.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        conn.commit()
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


def test_migrations_adopt_emergency_bindings(scratch_dbs):
    """Migration e52d44b73edb over every case in `emergency_fund_adoption_cases`
    — the same rows and outcomes the snapshot restore's adopter is held to.

    Upgraded through the real chain to the revision before, the old binding
    rows inserted, then upgraded to head."""
    from .emergency_fund_adoption_cases import (
        PRE_ADOPTION_REVISION,
        assert_chosen_adopted,
        assert_dismissed_adopted,
        assert_guess_only_adopted,
        build_chosen,
        build_dismissed,
        build_guess_only,
        insert_budget,
    )

    database, _ = scratch_dbs
    _run_migrations(database, PRE_ADOPTION_REVISION)
    engine = create_engine(_url(database))
    try:
        with engine.begin() as conn:
            chosen = build_chosen(conn, insert_budget(conn, "Chosen"))
            guess_only = insert_budget(conn, "Guess only")
            build_guess_only(conn, guess_only)
            dismissed = insert_budget(conn, "Dismissed")
            build_dismissed(conn, dismissed)

        _run_migrations(database)

        with engine.connect() as conn:
            assert_chosen_adopted(conn, chosen)
            assert_guess_only_adopted(conn, guess_only)
            assert_dismissed_adopted(conn, dismissed)
    finally:
        engine.dispose()


def test_migration_backfills_the_interest_envelope(scratch_dbs):
    """Migration 2cb769068102 over the three shapes a budget with cards can be
    in, and one with none — then down and up again, which must find what the
    first run made rather than make a second."""
    from sqlalchemy import insert, select

    from .emergency_fund_adoption_cases import _account, _t, insert_budget

    before = "b3f70c5e12d9"
    database, _ = scratch_dbs
    _run_migrations(database, before)
    engine = create_engine(_url(database))

    def group(conn, budget_id, name, sort_order=0):
        return conn.execute(
            insert(_t("category_groups"))
            .values(budget_id=budget_id, name=name, sort_order=sort_order)
            .returning(_t("category_groups").c.id)
        ).scalar_one()

    def category(conn, budget_id, group_id, name, sort_order=0, linked=None):
        return conn.execute(
            insert(_t("categories"))
            .values(
                budget_id=budget_id,
                category_group_id=group_id,
                name=name,
                sort_order=sort_order,
                linked_account_id=linked,
            )
            .returning(_t("categories").c.id)
        ).scalar_one()

    def card(conn, budget_id, name):
        return _account(
            conn,
            budget_id,
            name,
            key="credit_card",
            classification="liability",
            on_budget=True,
            counts_as_savings=False,
        )

    try:
        with engine.begin() as conn:
            # A card whose envelope sits in the card group.
            plain = insert_budget(conn, "Plain")
            plain_group = group(conn, plain, "Credit Card Payments", sort_order=3)
            category(
                conn, plain, plain_group, "Sapphire Visa", 0, card(conn, plain, "Sapphire Visa")
            )
            # The user already made their own, in the card group.
            own = insert_budget(conn, "Own")
            own_group = group(conn, own, "Credit Card Payments")
            category(
                conn, own, own_group, "Harborstone Card", 0, card(conn, own, "Harborstone Card")
            )
            theirs = category(conn, own, own_group, "Interest and Fees", 1)
            # Card envelopes kept elsewhere: no card group at all.
            elsewhere = insert_budget(conn, "Elsewhere")
            debt = group(conn, elsewhere, "Debt", sort_order=4)
            category(
                conn, elsewhere, debt, "Kestrel Card", 0, card(conn, elsewhere, "Kestrel Card")
            )
            # No card, nothing to do.
            cashonly = insert_budget(conn, "Cash only")
            _account(
                conn,
                cashonly,
                "Checking",
                key="checking",
                on_budget=True,
                counts_as_savings=False,
            )

        def keyed(conn, budget_id):
            rows = conn.execute(
                text(
                    "SELECT c.id, c.name, c.sort_order, g.name AS group_name, g.sort_order AS gs"
                    " FROM categories c JOIN category_groups g ON g.id = c.category_group_id"
                    " WHERE c.budget_id = :b AND c.system_key = 'card_interest'"
                    " AND NOT c.is_deleted"
                ),
                {"b": budget_id},
            ).all()
            return rows

        def assert_backfilled():
            with engine.connect() as conn:
                [p] = keyed(conn, plain)
                assert (p.name, p.group_name, p.sort_order) == (
                    "Interest & fees",
                    "Credit Card Payments",
                    1,
                ), "last in the card group"
                [o] = keyed(conn, own)
                assert o.id == theirs and o.name == "Interest and Fees", "adopted, not duplicated"
                [e] = keyed(conn, elsewhere)
                assert (e.group_name, e.gs) == ("Credit Card Payments", 5), "group made, last"
                assert keyed(conn, cashonly) == []
                named = conn.execute(
                    select(_t("categories").c.budget_id).where(
                        _t("categories").c.name.in_(["Interest & fees", "Interest and Fees"])
                    )
                ).scalars()
                assert sorted(map(str, named)) == sorted(map(str, [plain, own, elsewhere]))

        _run_migrations(database)
        assert_backfilled()
        # Down drops the key and keeps the envelopes (they may hold money);
        # up again adopts them by name rather than adding a second.
        _run_migrations(database, before, command="downgrade")
        _run_migrations(database)
        assert_backfilled()
    finally:
        engine.dispose()


def test_migration_rolls_overdue_schedules_forward_without_posting(scratch_dbs):
    """Migration e53562b192c5: every schedule posts on its date from now on,
    so before `auto_create` goes, each live overdue schedule moves to its first
    occurrence on or after today and nothing is posted. A schedule whose end
    passes on the way ends as Skip ends one; due-today, future and deleted rows
    are not touched. Down re-adds the column as false and leaves the dates."""
    from datetime import timedelta

    from igab.utils.clock import today_server_local

    from .emergency_fund_adoption_cases import _account, insert_budget

    before = "2cb769068102"
    database, _ = scratch_dbs
    _run_migrations(database, before)
    engine = create_engine(_url(database))
    # The subprocess asks the same clock, in the same TZ.
    today = today_server_local()
    day = timedelta(days=1)

    def schedule(conn, account, budget, frequency, start, nxt, end=None, deleted=False):
        sid = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO scheduled_transactions (id, budget_id, account_id, amount,"
                " frequency, start_date, end_date, next_occurrence_date, auto_create,"
                " days_before_reminder, is_deleted)"
                " VALUES (:id, :b, :a, -120, :f, :s, :e, :n, false, 3, :d)"
            ),
            {"id": sid, "b": budget, "a": account, "f": frequency, "s": start}
            | {"e": end, "n": nxt, "d": deleted},
        )
        return sid

    def read(conn, sid):
        return tuple(
            conn.execute(
                text(
                    "SELECT next_occurrence_date, is_deleted"
                    " FROM scheduled_transactions WHERE id = :i"
                ),
                {"i": sid},
            ).one()
        )

    ago15, ago40 = today - 15 * day, today - 40 * day
    try:
        with engine.begin() as conn:
            budget = insert_budget(conn, "Schedules")
            acct = _account(
                conn,
                budget,
                "Harborstone Checking",
                key="checking",
                on_budget=True,
                counts_as_savings=False,
            )
            weekly = schedule(conn, acct, budget, "weekly", ago15, ago15)
            ended = schedule(
                conn, acct, budget, "monthly", today - 100 * day, ago40, end=today - 20 * day
            )
            once = schedule(conn, acct, budget, "once", today - 3 * day, today - 3 * day)
            due_today = schedule(conn, acct, budget, "monthly", today, today)
            future = schedule(conn, acct, budget, "monthly", today + 5 * day, today + 5 * day)
            deleted = schedule(conn, acct, budget, "weekly", ago15, ago15, deleted=True)

        def assert_rolled():
            with engine.connect() as conn:
                # Three weeks on from fifteen days ago: six days ahead.
                assert read(conn, weekly) == (today + 6 * day, False)
                # A month on from 40 days ago is past the end: ended as Skip
                # ends one, its dates left where they were.
                assert read(conn, ended) == (ago40, True)
                assert read(conn, once) == (today - 3 * day, True)
                assert read(conn, due_today) == (today, False)
                assert read(conn, future) == (today + 5 * day, False)
                assert read(conn, deleted) == (ago15, True)
                posted = conn.execute(text("SELECT count(*) FROM transactions")).scalar_one()
                assert posted == 0, "the roll-forward posts nothing"

        _run_migrations(database)
        assert_rolled()
        columns = {c["name"] for c in inspect(engine).get_columns("scheduled_transactions")}
        assert "auto_create" not in columns

        _run_migrations(database, before, command="downgrade")
        with engine.connect() as conn:
            flags = conn.execute(text("SELECT DISTINCT auto_create FROM scheduled_transactions"))
            assert list(flags.scalars()) == [False]
        assert_rolled()  # the dates stay where the upgrade put them

        _run_migrations(database)
        assert_rolled()  # nothing is overdue the second time round
    finally:
        engine.dispose()
