"""Snapshot invalidation: session-level hooks that keep the category balance
snapshot cache honest.

Any write touching a model that feeds the budget summary (Transaction,
BudgetAssignment, Category, ImportAnchor, Account) deletes every
BudgetSnapshotMeta row — meta-row presence is the sole validity signal, so the
next summary read rebuilds from source data. The in-process card walk cache
(`igab.services.walk_cache`) keys on the same row, so these hooks are its
invalidation too: anything the walk reads has to be watched here.

Invalidation is deliberately coarse (all budgets, no old-state capture): a
changed row only reveals its *new* category/month, so per-scope tracking
cannot be made sound, and a self-hosted install has at most a handful of
budgets.

Two hooks are required because the app mutates through two channels:
- ``before_flush`` catches ORM object changes (``session.add``, attribute
  assignment, ``session.delete``).
- ``do_orm_execute`` catches core ``insert()``/``update()``/``delete()``
  statements issued through ``session.execute`` — the path used by
  BaseRepository.update/soft_delete, TransactionRepository.update_cleared,
  and bulk imports — which never appear in a flush.

Hard budget deletes cascade snapshot rows away at the DB level, so they need
no hook. Listeners are registered on the Session class at import time;
``igab.db`` imports this module so any code that touches the models has them
active.
"""

from sqlalchemy import delete, event, inspect
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql import ClauseElement

from igab.db.models import (
    Account,
    Budget,
    BudgetAssignment,
    BudgetSnapshotMeta,
    Category,
    ImportAnchor,
    Transaction,
)

# ImportAnchor is written once per import, but that write must invalidate:
# the category snapshot cache bakes the anchor's openings into its rows.
#
# Not CategoryGroup: the only group column a cache reads is `is_system`
# (`category_filters.SPENDABLE`), which is set when the group is created and
# never changed, and a category moving between groups is a Category write.
_WATCHED = (Transaction, BudgetAssignment, Category, ImportAnchor)

#: The account columns the caches read, through `txn_filters`:
#: `ON_BUDGET_ACCOUNT` (on_budget, is_deleted) decides which rows an
#: envelope's activity sums, `ON_CARD_ACCOUNT` (classification, of which
#: account_type is the source) which accounts are cards, `LATE_ARRIVAL`
#: (from_import) which month a row counts in, and `AFTER_BUDGET_START`
#: (budget_start_date) which card rows count at all. The card walk also takes
#: its list of cards from the accounts table — by those same columns.
#:
#: Only these, the way `Budget` is watched for `history_mode` alone: a rename,
#: a sort order or a sync timestamp moves no figure, and a sync touches its
#: account on every run. An account inserted or hard-deleted always
#: invalidates — it may be a card the walk has not seen.
#:
#: An account switched off budget used to leave its spending in every
#: envelope's cached activity until the next unrelated write.
_ACCOUNT_COLUMNS = frozenset(
    {
        "on_budget",
        "is_deleted",
        "classification",
        "account_type",
        "from_import",
        "budget_start_date",
    }
)


def _invalidate(session: Session) -> None:
    # An empty DELETE on a table with one row per budget is cheap enough to
    # run unguarded; a skip-flag would need re-arming after every rebuild and
    # is exactly the kind of statefulness that makes caches lie.
    session.execute(delete(BudgetSnapshotMeta))


@event.listens_for(Session, "before_flush")
def _invalidate_on_flush(session: Session, flush_context: object, instances: object) -> None:
    for obj in session.new:
        if isinstance(obj, (*_WATCHED, Account)):
            _invalidate(session)
            return
    for obj in session.deleted:
        if isinstance(obj, (*_WATCHED, Account)):
            _invalidate(session)
            return
    for obj in session.dirty:
        if isinstance(obj, _WATCHED) and session.is_modified(obj, include_collections=False):
            _invalidate(session)
            return
        if isinstance(obj, Account) and any(
            inspect(obj).attrs[column].history.has_changes() for column in _ACCOUNT_COLUMNS
        ):
            _invalidate(session)
            return
        if isinstance(obj, Budget) and inspect(obj).attrs.history_mode.history.has_changes():
            # The history-mode switch decides whether the anchor is read at
            # all (`import_anchor_repo.ANCHOR_IN_FORCE`) — the cache built
            # under one mode is wrong under the other. Only that column: a
            # rename moves no figure.
            _invalidate(session)
            return


@event.listens_for(Session, "do_orm_execute")
def _invalidate_on_execute(state: ORMExecuteState) -> None:
    if not (state.is_insert or state.is_update or state.is_delete):
        return
    mapper = state.bind_mapper
    # bind_mapper is None for plain Table statements (e.g. tag association
    # tables) — none of those feed the summary.
    if mapper is None:
        return
    # A core UPDATE of a budget row may carry `history_mode` (an undo's field
    # restore, say), and its columns are not cheap to read back out of the
    # statement — budget rows change rarely enough to invalidate on any.
    if issubclass(mapper.class_, _WATCHED) or (state.is_update and mapper.class_ is Budget):
        _invalidate(state.session)
    elif mapper.class_ is Account and (not state.is_update or _sets_any(state, _ACCOUNT_COLUMNS)):
        _invalidate(state.session)


def _sets_any(state: ORMExecuteState, columns: frozenset[str]) -> bool:
    """Whether a core UPDATE may write any of `columns`.

    Read from the statement's own bind parameters — `.values(on_budget=...)`
    compiles to a parameter named `on_budget`, where a WHERE clause's are
    suffixed (`on_budget_1`) — and from the parameter sets an ORM bulk update
    passes beside it. Blind to a watched column set to a SQL expression
    rather than a value; every account UPDATE in the app sets plain values
    there (`updated_at=func.now()` is the only expression, and is not
    watched). A statement with no parameters at all is not read: it
    invalidates.
    """
    statement = state.statement
    if not isinstance(statement, ClauseElement):
        return True
    names = set(statement.compile().params)
    params = state.parameters
    for row in params if isinstance(params, list | tuple) else [params or {}]:
        names.update(row)
    return not names or not names.isdisjoint(columns)
