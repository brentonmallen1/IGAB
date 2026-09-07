import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from igab.db.models import Account, Category, Payee, ScheduledTransaction
from igab.domain.exceptions import NotFoundError
from igab.domain.schedule import next_occurrence, validate_schedule
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
from igab.services.ownership import require_in_budget
from igab.services.transaction_service import TransactionCreate, TransactionService


@dataclass
class ScheduledTransactionCreate:
    account_id: uuid.UUID
    amount: Decimal
    frequency: str
    start_date: date
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    end_date: date | None = None
    auto_create: bool = False
    days_before_reminder: int = 3
    second_day_of_month: int | None = None
    transfer_account_id: uuid.UUID | None = None
    #: Set by an importer so re-importing the same file creates nothing twice
    #: (the identity rule is domain/import_identity.py's, shared with rows).
    import_id: str | None = None


#: The columns `validate_schedule` reads, so update can merge them from the
#: stored row without listing them twice.
_SHAPE_FIELDS = (
    "frequency",
    "start_date",
    "second_day_of_month",
    "end_date",
    "days_before_reminder",
)


class ScheduledTransactionService:
    def __init__(
        self,
        repo: ScheduledTransactionRepository,
        txn_service: TransactionService,
    ) -> None:
        self.repo = repo
        self.txn_service = txn_service
        # Every mutation records (change_log.py). The nightly scheduler
        # shares these paths; its writes record with source="system", so
        # they show in Activity without entering the manual ⌘Z stack.
        self.changes = ChangeRecorder(repo.session)

    async def list(self, budget_id: uuid.UUID) -> list[ScheduledTransaction]:
        return await self.repo.get_all(budget_id)

    async def create(
        self,
        budget_id: uuid.UUID,
        data: ScheduledTransactionCreate,
        *,
        source: str = "manual",
    ) -> ScheduledTransaction:
        validate_schedule(
            frequency=data.frequency,
            start_date=data.start_date,
            second_day_of_month=data.second_day_of_month,
            end_date=data.end_date,
            days_before_reminder=data.days_before_reminder,
        )
        await self._validate_budget_refs(
            budget_id,
            data.account_id,
            data.category_id,
            data.payee_id,
            data.transfer_account_id,
        )
        sched = await self.repo.create(
            budget_id=budget_id,
            account_id=data.account_id,
            amount=data.amount,
            payee_id=data.payee_id,
            category_id=data.category_id,
            memo=data.memo,
            frequency=data.frequency,
            start_date=data.start_date,
            end_date=data.end_date,
            second_day_of_month=data.second_day_of_month,
            auto_create=data.auto_create,
            days_before_reminder=data.days_before_reminder,
            transfer_account_id=data.transfer_account_id,
            import_id=data.import_id,
            next_occurrence_date=data.start_date,
        )
        await self.changes.record(
            budget_id=budget_id,
            entity_type="scheduled_transaction",
            entity_id=sched.id,
            action="create",
            after=snapshot("scheduled_transaction", sched),
            source=source,
        )
        return sched

    async def update(self, id: uuid.UUID, **kwargs) -> ScheduledTransaction:
        existing = await self.repo.get(id)
        if existing is None:
            raise NotFoundError("Scheduled transaction", str(id))
        # The shape rules run on the merged row: a PATCH that switches to
        # twice-monthly without a second day is refused here, not by the
        # arithmetic on the night it first comes due.
        merged = {f: kwargs.get(f, getattr(existing, f)) for f in _SHAPE_FIELDS}
        validate_schedule(**merged)
        if any(
            k in kwargs for k in ("account_id", "category_id", "payee_id", "transfer_account_id")
        ):
            await self._validate_budget_refs(
                existing.budget_id,
                kwargs.get("account_id"),
                kwargs.get("category_id"),
                kwargs.get("payee_id"),
                kwargs.get("transfer_account_id"),
            )
        before = snapshot("scheduled_transaction", existing)
        updated = await self.repo.update(id, **kwargs)
        after = snapshot("scheduled_transaction", updated)
        if snapshots_match(after, before):
            await self.changes.record(
                budget_id=updated.budget_id,
                entity_type="scheduled_transaction",
                entity_id=updated.id,
                action="update",
                before=before,
                after=after,
            )
        return updated

    async def _validate_budget_refs(
        self,
        budget_id: uuid.UUID,
        account_id: uuid.UUID | None,
        category_id: uuid.UUID | None,
        payee_id: uuid.UUID | None,
        transfer_account_id: uuid.UUID | None = None,
    ) -> None:
        """Reject account/category/payee ids that belong to another budget.

        These arrive from the request body, so the route's ownership guard does
        not cover them.
        """
        session = self.txn_service.session
        await require_in_budget(session, Account, account_id, budget_id, "Account")
        await require_in_budget(session, Category, category_id, budget_id, "Category")
        await require_in_budget(session, Payee, payee_id, budget_id, "Payee")
        await require_in_budget(session, Account, transfer_account_id, budget_id, "Account")

    async def delete(
        self,
        id: uuid.UUID,
        *,
        source: str = "manual",
        batch_id: uuid.UUID | None = None,
    ) -> None:
        sched = await self.repo.get(id)
        if sched is not None:
            await self.changes.record(
                budget_id=sched.budget_id,
                entity_type="scheduled_transaction",
                entity_id=sched.id,
                action="delete",
                before=snapshot("scheduled_transaction", sched),
                source=source,
                batch_id=batch_id,
            )
        await self.repo.soft_delete(id)

    async def _advance(
        self,
        sched: ScheduledTransaction,
        *,
        source: str,
        batch_id: uuid.UUID | None = None,
        posted_on: date | None = None,
    ) -> ScheduledTransaction | None:
        """Roll the schedule to its next occurrence and record the move —
        the one spelling shared by skip, enter, and the nightly run.

        Returns None when the schedule has completed: a `once` after its
        date, or the last occurrence before `end_date`. Completion is a soft
        delete in the same batch, so ⌘Z after entering the final occurrence
        restores the schedule along with taking back the row. One rule for
        both cases; `process_due` used to have its own end-date branch.
        """
        before = snapshot("scheduled_transaction", sched)
        nxt = calculate_next(sched)
        values: dict = {}
        if posted_on is not None:
            values["last_created_date"] = posted_on
        if nxt is not None:
            values["next_occurrence_date"] = nxt
        updated = sched
        if values:
            updated = await self.repo.update(sched.id, **values)
            after = snapshot("scheduled_transaction", updated)
            if snapshots_match(after, before):  # non-empty diff — the dates moved
                await self.changes.record(
                    budget_id=updated.budget_id,
                    entity_type="scheduled_transaction",
                    entity_id=updated.id,
                    action="update",
                    before=before,
                    after=after,
                    source=source,
                    batch_id=batch_id,
                )
        if nxt is None:
            await self.delete(sched.id, source=source, batch_id=batch_id)
            return None
        return updated

    async def skip(self, id: uuid.UUID) -> ScheduledTransaction | None:
        """Advance without posting. None means the skip completed the schedule."""
        sched = await self.repo.get(id)
        if sched is None:
            raise NotFoundError("Scheduled transaction", str(id))
        return await self._advance(sched, source="manual")

    async def enter_now(
        self, sched_id: uuid.UUID, budget_id: uuid.UUID, *, source: str = "manual"
    ) -> None:
        sched = await self.repo.get(sched_id)
        if sched is None:
            return
        # The row is dated the occurrence it stands for, not the day the
        # button was pressed or the night the job ran: a missed nightly run
        # backdates correctly, and "enter early" files on the bill's date.
        posted_on = sched.next_occurrence_date
        # One batch across both recorders (batch_id is just a column): ⌘Z
        # after "enter now" takes back the created transaction AND the
        # schedule's advanced dates, not one without the other.
        with self.txn_service.changes.batch() as batch_id:
            await self.txn_service.create(
                budget_id,
                TransactionCreate(
                    account_id=sched.account_id,
                    date=posted_on,
                    amount=sched.amount,
                    payee_id=sched.payee_id,
                    category_id=sched.category_id,
                    memo=sched.memo,
                    cleared="uncleared",
                    approved=True,
                    # A scheduled transfer must materialize BOTH legs
                    transfer_account_id=sched.transfer_account_id,
                    # The row says where it came from (created_via='scheduled')
                    # and which schedule; nothing set this before.
                    scheduled_transaction_id=sched.id,
                ),
            )
            await self._advance(sched, source=source, batch_id=batch_id, posted_on=posted_on)

    async def process_due(self, budget_id: uuid.UUID, today: date) -> int:
        """The nightly run: post every due occurrence of every auto-create
        schedule, each on its own date.

        Only auto-create schedules are touched. A schedule the person enters
        by hand stays due — the register shows it overdue — until they enter
        or skip it. It used to be advanced silently here, so a missed bill
        moved to next month with no trace that it had been missed.
        """
        due = await self.repo.get_due(today, budget_id=budget_id)
        created = 0
        for sched in due:
            if not sched.auto_create:
                continue
            current: ScheduledTransaction | None = sched
            # Loop, not one step: a job that slept two nights owes two rows.
            while current is not None and current.next_occurrence_date <= today:
                if current.end_date is not None and current.next_occurrence_date > current.end_date:
                    # The end date was moved back behind the next occurrence;
                    # the schedule is over without another row.
                    await self.delete(current.id, source="system")
                    break
                await self.enter_now(current.id, budget_id, source="system")
                created += 1
                current = await self.repo.get(current.id)
        return created


def calculate_next(sched: ScheduledTransaction) -> date | None:
    """The stored row's next occurrence — a thin wrapper so the arithmetic
    has one home (domain/schedule.py) and one set of tests."""
    return next_occurrence(
        sched.frequency,
        sched.next_occurrence_date,
        start_day=sched.start_date.day,
        second_day_of_month=sched.second_day_of_month,
        end_date=sched.end_date,
    )
