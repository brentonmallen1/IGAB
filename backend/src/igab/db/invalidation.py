"""Snapshot invalidation: session-level hooks that keep the category balance
snapshot cache honest.

Any write touching a model that feeds the budget summary (Transaction,
BudgetAssignment, Category) deletes every BudgetSnapshotMeta row — meta-row
presence is the sole validity signal, so the next summary read rebuilds from
source data. Invalidation is deliberately coarse (all budgets, no old-state
capture): a changed row only reveals its *new* category/month, so per-scope
tracking cannot be made sound, and a self-hosted install has at most a
handful of budgets.

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

from sqlalchemy import delete, event
from sqlalchemy.orm import ORMExecuteState, Session

from igab.db.models import BudgetAssignment, BudgetSnapshotMeta, Category, Transaction

_WATCHED = (Transaction, BudgetAssignment, Category)


def _invalidate(session: Session) -> None:
    # An empty DELETE on a table with one row per budget is cheap enough to
    # run unguarded; a skip-flag would need re-arming after every rebuild and
    # is exactly the kind of statefulness that makes caches lie.
    session.execute(delete(BudgetSnapshotMeta))


@event.listens_for(Session, "before_flush")
def _invalidate_on_flush(session: Session, flush_context: object, instances: object) -> None:
    for obj in session.new:
        if isinstance(obj, _WATCHED):
            _invalidate(session)
            return
    for obj in session.deleted:
        if isinstance(obj, _WATCHED):
            _invalidate(session)
            return
    for obj in session.dirty:
        if isinstance(obj, _WATCHED) and session.is_modified(obj, include_collections=False):
            _invalidate(session)
            return


@event.listens_for(Session, "do_orm_execute")
def _invalidate_on_execute(state: ORMExecuteState) -> None:
    if not (state.is_insert or state.is_update or state.is_delete):
        return
    mapper = state.bind_mapper
    # bind_mapper is None for plain Table statements (e.g. tag association
    # tables) — none of those feed the summary.
    if mapper is None or not issubclass(mapper.class_, _WATCHED):
        return
    _invalidate(state.session)
