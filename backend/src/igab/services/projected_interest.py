"""Keeping a loan's projected interest rows in step with its ledger.

The rule — whether a month should carry a projection, and what it is — is
`domain.projected_interest.plan_projection`. This is the wiring: gather each
month's facts (`ProjectedInterestRepository`), plan, write, record.

**Writes are the app's, inside the caller's batch.** Every row written here
is recorded with `source="system"` on the recorder the caller hands in, so
the payment that caused a projection and the projection itself are one undo
unit — ⌘Z of a payment takes its interest row with it, and a sync run's undo
takes back the replacements it caused. Nothing here goes through
`TransactionService`, which is what triggers a settle: writing through the
repository directly is what keeps a settle from re-triggering itself.

**Which months.** A change to a month moves every later month's opening
balance, and a later projection is sized on that opening — so a settle
re-plans each touched month and every later month that holds a live
projection, oldest first, flushing between months so each one reads the
month before it as written.

**Retiring** sets the month to NULL and deletes the row, recorded as one
`delete` carrying `_retired` bookkeeping. Clearing the month is what keeps a
retire from reading as a tombstone (the person declining the month), and the
bookkeeping is how redo replays it as a retire rather than a decline.
"""

import uuid
from collections.abc import Iterable
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Transaction
from igab.domain.dates import add_months, month_start
from igab.domain.interest import chargeable_rate
from igab.domain.projected_interest import (
    PROJECTION_MEMO,
    PROJECTION_ORIGIN,
    RETIRED_KEY,
    Create,
    Plan,
    Retire,
    Update,
    may_create_for,
    plan_projection,
)
from igab.repositories.projected_interest_repo import ProjectedInterestRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import ChangeRecorder, snapshot, source_for
from igab.utils.clock import today_utc

_SOURCE = source_for(PROJECTION_ORIGIN)


class ProjectedInterest:
    def __init__(self, session: AsyncSession, recorder: ChangeRecorder) -> None:
        self.session = session
        self.recorder = recorder
        self.repo = ProjectedInterestRepository(session)
        self.transactions = TransactionRepository(session)

    async def settle(
        self,
        positions: Iterable[tuple[uuid.UUID | str, date | str]],
        today: date | None = None,
    ) -> None:
        """Bring every account and month in `positions` — and every later
        month holding a projection — into line with the ledger. A position
        may be spelled as a change-log snapshot spells it (strings)."""
        today = today or today_utc()
        by_account: dict[uuid.UUID, set[date]] = {}
        for account_id, day in positions:
            on = day if isinstance(day, date) else date.fromisoformat(day)
            by_account.setdefault(uuid.UUID(str(account_id)), set()).add(month_start(on))
        for account_id, months in by_account.items():
            await self._settle(account_id, months, today)

    async def settle_account(self, account_id: uuid.UUID, today: date | None = None) -> None:
        """Re-plan an account whose TERMS changed: a rate set or cleared, a
        promo moved, the liability linked or unlinked. Covers the months a new
        projection may be written for (this one and last) and every month
        already holding one."""
        today = today or today_utc()
        this_month = month_start(today)
        await self._settle(account_id, {add_months(this_month, -1), this_month}, today)

    async def _settle(self, account_id: uuid.UUID, months: set[date], today: date) -> None:
        liability = await self.repo.terms_on_file(account_id)
        if liability is None:
            # No terms: nothing may stand. Whatever the app projected under
            # terms since cleared, or on an account since moved on budget,
            # goes — the person's tombstones stay, they are not projections.
            for row in await self.repo.live_projections(account_id):
                await self._retire(row)
            return
        later = await self.repo.live_projections(account_id, from_month=min(months))
        months = months | {m for row in later if (m := row.projected_interest_month) is not None}
        for month in sorted(months):
            facts = await self.repo.month_facts(account_id, month)
            rate = chargeable_rate(liability.interest_rate, liability.promo_end_date, month)
            await self._apply(
                account_id,
                liability.budget_id,
                plan_projection(facts, rate, may_create_for(month, today)),
            )

    async def _apply(self, account_id: uuid.UUID, budget_id: uuid.UUID, plan: Plan) -> None:
        if isinstance(plan, Create):
            row = await self.transactions.create(
                budget_id=budget_id,
                account_id=account_id,
                date=plan.date,
                amount=plan.amount,
                payee_id=None,
                category_id=None,
                memo=PROJECTION_MEMO,
                cleared="uncleared",
                approved=True,
                created_via=PROJECTION_ORIGIN,
                projected_interest_month=plan.month,
            )
            await self.recorder.record(
                budget_id=budget_id,
                entity_type="transaction",
                entity_id=row.id,
                action="create",
                after=snapshot("transaction", row),
                source=_SOURCE,
            )
        elif isinstance(plan, Update):
            row = await self.transactions.get_or_raise(plan.id)
            before = snapshot("transaction", row)
            row = await self.transactions.update(plan.id, date=plan.date, amount=plan.amount)
            await self.recorder.record(
                budget_id=budget_id,
                entity_type="transaction",
                entity_id=row.id,
                action="update",
                before=before,
                after=snapshot("transaction", row),
                source=_SOURCE,
            )
        elif isinstance(plan, Retire):
            await self._retire(await self.transactions.get_or_raise(plan.id))

    async def _retire(self, row: Transaction) -> None:
        before = {**snapshot("transaction", row), RETIRED_KEY: True}
        await self.transactions.update(row.id, projected_interest_month=None)
        await self.transactions.soft_delete(row.id)
        await self.recorder.record(
            budget_id=row.budget_id,
            entity_type="transaction",
            entity_id=row.id,
            action="delete",
            before=before,
            source=_SOURCE,
        )
