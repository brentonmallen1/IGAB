"""What a budget owns, derived from the schema instead of listed by hand.

Every feature that walks a budget's whole entity graph needs the same answer:
which tables carry this budget's rows, in what order, and how do you select
them. Deleting a budget needs it. Exporting one as a portable snapshot needs
it, and importing that snapshot needs it in reverse. The invariant that no row
in a budget points at another budget's row needs it too.

Written by hand, that list is wrong the day someone adds a table — and it
already was: ``test_budget_delete.py`` asserted cascade against a
hand-maintained list of **14** of the 23 budget-owned tables, so nine could
have stopped cascading with the test still green.

So it is derived from ``Base.metadata`` and nothing else — no session, no I/O,
unit-testable in milliseconds. Everything the metadata *cannot* answer is
declared here as data with a reason, and ``tests/unit/test_budget_scope.py``
fails when a new one appears rather than letting it be missed silently.

The classification, in order:

``ROOT``      ``budgets`` itself.
``OWNED``     has a foreign key to ``budgets.id``.
``CHILD``     has at least one foreign key, and every non-self foreign key
              target is already ROOT, OWNED or CHILD. Computed as a fixpoint,
              which is load-bearing: ``budget_view_placements`` only becomes
              CHILD after ``budget_view_groups`` does.
``GLOBAL``    allowlisted as shared across budgets.
``EXCLUDED``  allowlisted as deliberately outside the graph.

Anything left over classifies as ``None`` and fails the guard test. That is
the correct outcome, not a gap: a table with foreign keys to both
``categories`` and ``users`` needs a human to decide which it is.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import UUID

from sqlalchemy import Column, MetaData, Table, select
from sqlalchemy.sql.elements import ColumnElement

from igab.db.models import Base
from igab.guide.bindings import GUIDE_ENTITY_TABLES

ROOT_TABLE = "budgets"


class Scope(StrEnum):
    ROOT = "root"
    OWNED = "owned"
    CHILD = "child"
    GLOBAL = "global"
    EXCLUDED = "excluded"


#: Shared across every budget, so a per-budget walk must never carry, copy or
#: delete them. One reason per entry — an allowlist without reasons is a list
#: nobody can audit later.
GLOBAL_TABLES: Mapping[str, str] = MappingProxyType(
    {
        "users": "Accounts on the installation, not in a budget. A budget's "
        "rows reference them; they outlive any budget.",
        "app_settings": "Installation-wide configuration (AI, backups, "
        "update checks). Not addressable by budget.",
        "simplefin_connections": "One bank connection serves every budget it "
        "has accounts in, and holds an encrypted credential no snapshot may "
        "carry.",
    }
)

#: Budget-scoped by the schema but deliberately outside the graph. Empty
#: today; an entry is a claim that needs a reason, not a convenience.
EXCLUDED_TABLES: Mapping[str, str] = MappingProxyType({})

#: UUID columns that address another table's row with no foreign key to say
#: so. A purely metadata-driven walk cannot see these, and the failure is
#: silent — nothing raises, the copy simply keeps pointing at the original
#: budget's rows.
SOFT_REFERENCES: Mapping[tuple[str, str], str] = MappingProxyType(
    {
        # Served and rendered: the register looks a schedule up by this id, so
        # an unremapped copy shows the *source* budget's schedule.
        ("transactions", "scheduled_transaction_id"): "scheduled_transactions",
        # Import undo groups by batch; unremapped, it targets another budget's
        # batch.
        ("transactions", "import_batch_id"): "import_batches",
    }
)

#: Soft references whose target table depends on a sibling column's value.
#: ``(type_column, {type_value: table_name})``.
POLYMORPHIC_REFERENCES: Mapping[tuple[str, str], tuple[str, Mapping[str, str]]] = MappingProxyType(
    {
        ("guide_bindings", "entity_id"): ("entity_type", GUIDE_ENTITY_TABLES),
    }
)

#: UUID columns that are *not* a live pointer into the graph. Each needs a
#: reason, because the alternative reading — someone forgot to declare a soft
#: reference — is the bug this module exists to prevent.
UNTRACKED_UUIDS: Mapping[tuple[str, str], str] = MappingProxyType(
    {
        ("change_log", "entity_id"): "Audit history. Polymorphic over "
        "services.change_log.ENTITY_MODELS, and routinely points at a row "
        "that has since been deleted — undo resolves it and tolerates its "
        "absence. Never remapped, never validated. If change_log is ever "
        "carried into a snapshot this becomes a live reference and moves to "
        "POLYMORPHIC_REFERENCES.",
        ("change_log", "batch_id"): "Correlates change_log rows belonging to "
        "one compound operation. Not a row id in any table.",
    }
)


def _foreign_targets(table: Table) -> set[str]:
    """Table names this table points at, excluding itself."""
    return {
        fk.column.table.name
        for column in table.columns
        for fk in column.foreign_keys
        if fk.column.table.name != table.name
    }


def _has_foreign_key(table: Table, target: str, column_name: str = "id") -> bool:
    return any(
        fk.column.table.name == target and fk.column.name == column_name
        for column in table.columns
        for fk in column.foreign_keys
    )


def classify(metadata: MetaData = Base.metadata) -> dict[str, Scope | None]:
    """Every table in the schema, mapped to its scope — ``None`` when the
    rules cannot decide and a person must."""
    scopes: dict[str, Scope | None] = {}

    for name in metadata.tables:
        if name == ROOT_TABLE:
            scopes[name] = Scope.ROOT
        elif name in GLOBAL_TABLES:
            scopes[name] = Scope.GLOBAL
        elif name in EXCLUDED_TABLES:
            scopes[name] = Scope.EXCLUDED
        elif _has_foreign_key(metadata.tables[name], ROOT_TABLE):
            scopes[name] = Scope.OWNED
        else:
            scopes[name] = None

    # Fixpoint: a table joins the graph once every table it points at is in it.
    inside = {Scope.ROOT, Scope.OWNED, Scope.CHILD}
    changed = True
    while changed:
        changed = False
        for name, scope in scopes.items():
            if scope is not None:
                continue
            targets = _foreign_targets(metadata.tables[name])
            if targets and all(scopes.get(t) in inside for t in targets):
                scopes[name] = Scope.CHILD
                changed = True

    return scopes


def budget_tables(metadata: MetaData = Base.metadata) -> tuple[Table, ...]:
    """Every table holding a budget's rows, in an order safe to INSERT in.

    ``sorted_tables`` is a topological sort with no cycles between distinct
    tables in this schema, so one list serves both directions: insert in this
    order, delete in ``reversed()``. That reverse is also what makes
    ``accounts.account_type_id`` safe — a plain NO ACTION reference, checked at
    statement end, so accounts must go before account types.
    """
    scopes = classify(metadata)
    inside = {Scope.ROOT, Scope.OWNED, Scope.CHILD}
    return tuple(t for t in metadata.sorted_tables if scopes.get(t.name) in inside)


def delete_order(metadata: MetaData = Base.metadata) -> tuple[Table, ...]:
    """Budget tables in an order safe to DELETE in — children first, and
    without ``budgets`` itself, which the caller removes last (or keeps)."""
    return tuple(t for t in reversed(budget_tables(metadata)) if t.name != ROOT_TABLE)


def deferred_columns(table: Table) -> tuple[Column[Any], ...]:
    """Columns that point back at this same table, and so cannot be filled on
    INSERT before the rows they reference exist.

    Derived rather than named, so nothing downstream hard-codes
    ``transfer_id``. Today this is exactly three columns of ``transactions``;
    every other back-reference is handled by the topological sort.
    """
    return tuple(
        column
        for column in table.columns
        if any(fk.column.table.name == table.name for fk in column.foreign_keys)
    )


def anchor_column(table: Table, metadata: MetaData = Base.metadata) -> Column[Any]:
    """The foreign key a CHILD table reaches its budget through.

    The first NOT NULL foreign key, in column order, whose target is itself in
    the graph. NOT NULL matters: ``reconciliation_snapshots`` also points at a
    transaction, but nullably, so it cannot be the anchor.
    """
    scopes = classify(metadata)
    inside = {Scope.ROOT, Scope.OWNED, Scope.CHILD}
    for column in table.columns:
        if column.nullable:
            continue
        for fk in column.foreign_keys:
            if fk.column.table.name != table.name and scopes.get(fk.column.table.name) in inside:
                return column
    raise ValueError(
        f"{table.name} has no NOT NULL foreign key into the budget graph, so "
        f"its rows cannot be attributed to a budget. Give it a budget_id, or "
        f"declare it in GLOBAL_TABLES or EXCLUDED_TABLES with a reason."
    )


def budget_predicate(
    table: Table, budget_id: UUID, metadata: MetaData = Base.metadata
) -> ColumnElement[bool]:
    """A WHERE clause selecting exactly this budget's rows of ``table``.

    ``budget_id == x`` for a table that carries one; otherwise a subquery
    through the anchor foreign key, recursively. Max depth in this schema is 2
    (``transaction_matches → transactions → budgets``) and every anchor column
    is indexed.
    """
    scope = classify(metadata).get(table.name)
    if scope is Scope.ROOT:
        return table.c.id == budget_id
    if scope is Scope.OWNED:
        return table.c.budget_id == budget_id
    if scope is Scope.CHILD:
        column = anchor_column(table, metadata)
        parent = next(fk.column.table for fk in column.foreign_keys)
        return column.in_(select(parent.c.id).where(budget_predicate(parent, budget_id, metadata)))
    raise ValueError(
        f"{table.name} is {scope.value if scope else 'unclassified'}, not part "
        f"of a budget's graph, so it has no per-budget predicate."
    )
