"""The guards that keep the budget graph derived rather than remembered.

These run against ``Base.metadata`` with no database, so a schema change that
would silently drop a table from a snapshot — or silently orphan it on delete
— fails here in milliseconds instead of in an integration run, or in someone's
budget.

The most valuable one is the last: every UUID column is an FK or a declared
reference. That is the test that would have caught
``transactions.scheduled_transaction_id``, which points at a row, has no
foreign key to say so, and is rendered in the register.
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from igab.db.budget_scope import (
    EXCLUDED_TABLES,
    GLOBAL_TABLES,
    POLYMORPHIC_REFERENCES,
    ROOT_TABLE,
    SOFT_REFERENCES,
    UNTRACKED_UUIDS,
    Scope,
    anchor_column,
    budget_predicate,
    budget_tables,
    classify,
    deferred_columns,
    delete_order,
)
from igab.db.models import Base

METADATA = Base.metadata
IN_GRAPH = {Scope.ROOT, Scope.OWNED, Scope.CHILD}


class TestEveryTableIsClassified:
    def test_nothing_is_left_undecided(self):
        scopes = classify(METADATA)
        undecided = sorted(name for name, scope in scopes.items() if scope is None)
        assert not undecided, (
            f"These tables fit none of the rules: {undecided}. Decide which "
            f"they are — leaving one out means a snapshot silently drops it "
            f"and a budget delete silently orphans it. Give it a budget_id "
            f"(OWNED), point it only at tables already in the graph (CHILD), "
            f"or add it to GLOBAL_TABLES / EXCLUDED_TABLES with a reason."
        )

    def test_every_table_in_the_schema_is_covered(self):
        assert set(classify(METADATA)) == set(METADATA.tables)

    def test_the_shape_of_the_graph_today(self):
        """Pinned so a table joining or leaving the graph is a decision
        someone made, not a diff nobody read."""
        scopes = classify(METADATA)
        counted = {scope: sum(1 for s in scopes.values() if s is scope) for scope in Scope}
        assert counted[Scope.ROOT] == 1
        assert counted[Scope.OWNED] == 23
        assert counted[Scope.CHILD] == 10
        assert counted[Scope.GLOBAL] == 3
        assert counted[Scope.EXCLUDED] == 0

    def test_the_fixpoint_reaches_grandchildren(self):
        """budget_view_placements is only CHILD once budget_view_groups is —
        a single pass over the tables would classify it by luck of ordering."""
        scopes = classify(METADATA)
        assert scopes["budget_view_groups"] is Scope.CHILD
        assert scopes["budget_view_placements"] is Scope.CHILD


class TestTheAllowlists:
    def test_global_tables_are_real_and_reasoned(self):
        for name, reason in GLOBAL_TABLES.items():
            assert name in METADATA.tables, f"GLOBAL_TABLES names {name}, which does not exist"
            assert len(reason) > 20, f"GLOBAL_TABLES[{name}] needs a reason, not a placeholder"

    def test_excluded_tables_are_real_and_reasoned(self):
        for name, reason in EXCLUDED_TABLES.items():
            assert name in METADATA.tables, f"EXCLUDED_TABLES names {name}, which does not exist"
            assert len(reason) > 20, f"EXCLUDED_TABLES[{name}] needs a reason, not a placeholder"

    def test_an_allowlisted_table_is_not_also_in_the_graph(self):
        scopes = classify(METADATA)
        for name in list(GLOBAL_TABLES) + list(EXCLUDED_TABLES):
            assert scopes[name] not in IN_GRAPH


class TestOrdering:
    def test_budget_tables_are_in_dependency_order(self):
        """One list, two directions: INSERT in this order, DELETE reversed.
        That only holds if every table's targets sort before it."""
        order = [t.name for t in budget_tables(METADATA)]
        position = {name: i for i, name in enumerate(order)}
        for table in budget_tables(METADATA):
            for column in table.columns:
                for fk in column.foreign_keys:
                    target = fk.column.table.name
                    if target == table.name or target not in position:
                        continue
                    assert position[target] < position[table.name], (
                        f"{table.name}.{column.name} points at {target}, which "
                        f"sorts after it — inserting a snapshot in this order "
                        f"would violate the foreign key."
                    )

    def test_the_graph_is_every_in_scope_table(self):
        scopes = classify(METADATA)
        assert {t.name for t in budget_tables(METADATA)} == {
            name for name, scope in scopes.items() if scope in IN_GRAPH
        }

    def test_delete_order_is_children_first_and_drops_the_root(self):
        names = [t.name for t in delete_order(METADATA)]
        assert ROOT_TABLE not in names
        assert names == [t.name for t in reversed(budget_tables(METADATA)) if t.name != ROOT_TABLE]

    def test_accounts_are_deleted_before_their_account_types(self):
        """account_type_id is a plain NO ACTION reference checked at statement
        end; the reverse order is what keeps it satisfiable."""
        names = [t.name for t in delete_order(METADATA)]
        assert names.index("accounts") < names.index("account_types")


class TestDeferredColumns:
    def test_only_self_references_are_deferred(self):
        for table in budget_tables(METADATA):
            for column in deferred_columns(table):
                assert any(
                    fk.column.table.name == table.name for fk in column.foreign_keys
                ), f"{table.name}.{column.name} is not self-referential"

    def test_the_deferred_set_today(self):
        """Named here and nowhere else — an importer that hard-codes
        'transfer_id' is a second copy of this list."""
        deferred = {
            f"{table.name}.{column.name}"
            for table in budget_tables(METADATA)
            for column in deferred_columns(table)
        }
        assert deferred == {
            "transactions.transfer_id",
            "transactions.parent_transaction_id",
            "transactions.linked_transaction_id",
        }


class TestEveryUuidIsAccountedFor:
    """The single most valuable guard here.

    A UUID column with no foreign key is either a soft reference nobody
    declared — in which case a duplicated budget keeps pointing at the
    original's rows, with nothing raising — or it is not a reference at all,
    which is a claim worth writing down.
    """

    def test_no_undeclared_uuid_columns(self):
        undeclared = []
        for table in METADATA.sorted_tables:
            for column in table.columns:
                if not isinstance(column.type, PG_UUID) or column.primary_key:
                    continue
                if column.foreign_keys:
                    continue
                key = (table.name, column.name)
                if key in SOFT_REFERENCES or key in POLYMORPHIC_REFERENCES:
                    continue
                if key in UNTRACKED_UUIDS:
                    continue
                undeclared.append(f"{table.name}.{column.name}")
        assert not undeclared, (
            f"These UUID columns have no foreign key and no declaration: "
            f"{undeclared}. If one addresses another row, declare it in "
            f"SOFT_REFERENCES (or POLYMORPHIC_REFERENCES) so copying a budget "
            f"remaps it — otherwise the copy keeps pointing at the original's "
            f"rows and nothing raises. If it addresses nothing, say so in "
            f"UNTRACKED_UUIDS with a reason."
        )

    def test_soft_references_name_real_columns_and_targets(self):
        for (table_name, column_name), target in SOFT_REFERENCES.items():
            assert table_name in METADATA.tables
            assert column_name in METADATA.tables[table_name].columns
            assert target in METADATA.tables, f"{table_name}.{column_name} points at no such table"

    def test_polymorphic_references_name_real_columns_targets_and_discriminators(self):
        for (table_name, column_name), (type_column, targets) in POLYMORPHIC_REFERENCES.items():
            table = METADATA.tables[table_name]
            assert column_name in table.columns
            assert type_column in table.columns, (
                f"{table_name}.{column_name} is discriminated by {type_column}, "
                f"which does not exist"
            )
            assert targets, f"{table_name}.{column_name} declares no targets"
            for value, target in targets.items():
                assert target in METADATA.tables, f"{value!r} names no such table: {target}"

    def test_untracked_uuids_are_real_and_reasoned(self):
        for (table_name, column_name), reason in UNTRACKED_UUIDS.items():
            assert column_name in METADATA.tables[table_name].columns
            assert len(reason) > 20, f"{table_name}.{column_name} needs a reason"


class TestPredicates:
    def test_every_table_in_the_graph_can_select_one_budget(self):
        budget_id = uuid.uuid4()
        for table in budget_tables(METADATA):
            assert budget_predicate(table, budget_id, METADATA) is not None

    def test_owned_tables_filter_directly(self):
        budget_id = uuid.uuid4()
        clause = str(budget_predicate(METADATA.tables["transactions"], budget_id, METADATA))
        assert "transactions.budget_id" in clause
        assert "SELECT" not in clause

    def test_child_tables_filter_through_their_anchor(self):
        budget_id = uuid.uuid4()
        clause = str(
            budget_predicate(METADATA.tables["transaction_matches"], budget_id, METADATA)
        )
        assert "synced_transaction_id IN" in clause
        assert "transactions.budget_id" in clause

    def test_the_anchor_is_never_a_nullable_column(self):
        scopes = classify(METADATA)
        for table in budget_tables(METADATA):
            if scopes[table.name] is not Scope.CHILD:
                continue
            assert not anchor_column(table, METADATA).nullable

    def test_reconciliation_snapshots_anchor_on_the_account(self):
        """Its other foreign key — the adjustment transaction — is nullable,
        so anchoring there would lose every snapshot with no adjustment."""
        assert (
            anchor_column(METADATA.tables["reconciliation_snapshots"], METADATA).name
            == "account_id"
        )
