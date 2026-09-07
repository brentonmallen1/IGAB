import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, CategoryTarget
from igab.domain.dates import month_start, months_between, weekday_occurrences
from igab.domain.enums import TargetStatus, TargetType
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.domain.targets import MAX_FUNDING_DAY, is_pending
from igab.repositories.target_repo import TargetRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match

ZERO = Decimal("0")


class TargetService:
    def __init__(self, repo: TargetRepository) -> None:
        self.repo = repo
        # Targets are money rules, so every mutation records (change_log.py).
        # Recording lives here rather than in the router because the
        # wishlist's envelope goals and the planner's apply-targets both
        # write through this service — a router-side record would cover one
        # path of three. `batch_id` lets those callers group the target row
        # with their own, so the compound operation undoes as one unit.
        # getattr: the pure-math paths are constructible with repo=None
        # (unit tests do), and those never record.
        self.changes = ChangeRecorder(cast(AsyncSession, getattr(repo, "session", None)))

    async def _budget_of(self, category_id: uuid.UUID) -> uuid.UUID:
        category = await self.repo.session.get(Category, category_id)
        if category is None:
            raise NotFoundError("Category", str(category_id))
        return category.budget_id

    async def get(self, category_id: uuid.UUID) -> CategoryTarget | None:
        return await self.repo.get_by_category(category_id)

    @staticmethod
    def validate(
        target_type: str,
        target_date: date | None,
        *,
        check_after_day: int | None,
        weekday: int | None,
    ) -> None:
        """The shape rules: a weekly target needs its weekday (its duty is
        undefined without one), only a savings balance may carry a date, and
        the day fields stay inside the ranges the arithmetic reads."""
        try:
            kind = TargetType(target_type)
        except ValueError:
            allowed = ", ".join(t.value for t in TargetType)
            raise InvariantViolation(f"Target type must be one of: {allowed}") from None
        if kind is TargetType.WEEKLY_FUNDING and weekday is None:
            raise InvariantViolation("A weekly target needs the day of the week it funds")
        if weekday is not None and not 0 <= weekday <= 6:
            raise InvariantViolation("Weekday must be 0 (Monday) to 6 (Sunday)")
        if target_date is not None and kind is not TargetType.SAVINGS_BALANCE:
            raise InvariantViolation("Only a savings balance target takes a target date")
        if check_after_day is not None and not 1 <= check_after_day <= MAX_FUNDING_DAY:
            raise InvariantViolation(f"Check-after day must be between 1 and {MAX_FUNDING_DAY}")

    async def upsert(
        self,
        category_id: uuid.UUID,
        target_type: str,
        target_amount: Decimal,
        target_date: date | None = None,
        *,
        check_after_day: int | None = None,
        weekday: int | None = None,
        batch_id: uuid.UUID | None = None,
    ) -> CategoryTarget:
        self.validate(target_type, target_date, check_after_day=check_after_day, weekday=weekday)
        budget_id = await self._budget_of(category_id)
        existing = await self.repo.get_by_category(category_id)
        fields = dict(
            target_type=target_type,
            target_amount=target_amount,
            target_date=target_date,
            check_after_day=check_after_day,
            weekday=weekday,
        )
        if existing is None:
            created = await self.repo.create(category_id=category_id, **fields)
            await self.changes.record(
                budget_id=budget_id,
                entity_type="category_target",
                entity_id=created.id,
                action="create",
                after=snapshot("category_target", created),
                batch_id=batch_id,
            )
            return created
        before = snapshot("category_target", existing)
        updated = await self.repo.update(existing.id, **fields)
        after = snapshot("category_target", updated)
        if snapshots_match(after, before):  # non-empty diff — something changed
            await self.changes.record(
                budget_id=budget_id,
                entity_type="category_target",
                entity_id=updated.id,
                action="update",
                before=before,
                after=after,
                batch_id=batch_id,
            )
        return updated

    async def delete(self, category_id: uuid.UUID, *, batch_id: uuid.UUID | None = None) -> None:
        existing = await self.repo.get_by_category(category_id)
        if existing is None:
            return
        await self.changes.record(
            budget_id=await self._budget_of(category_id),
            entity_type="category_target",
            entity_id=existing.id,
            action="delete",
            before=snapshot("category_target", existing),
            batch_id=batch_id,
        )
        await self.repo.delete(category_id)

    # ── the arithmetic ────────────────────────────────────────────────────
    #
    # One definition of the month's duty, and everything else derived from
    # it, because a pill that says "funded" has to mean "Fill Underfunded
    # will leave this alone". `today` is never defaulted: the callers pass
    # `today_utc()`, and a `date.today()` default here was a second clock.

    def duty(
        self,
        target: CategoryTarget,
        *,
        assigned: Decimal,
        available: Decimal,
        month: date,
    ) -> Decimal:
        """This month's full duty, before crediting what was assigned.

        - **Monthly**: the amount.
        - **Weekly**: the amount times the number of that weekday in
          `month` — 4 or 5 — so "$50 every Friday" asks for five in a
          five-Friday month. It used to be a flat monthly figure.
        - **Savings balance, undated**: the shortfall against AVAILABLE, the
          balance being built. `available` already contains this month's
          assignment, so `calculate_needed` must not subtract it again.
        - **Savings balance, dated**: the shortfall measured from the
          month's OPENING balance (available minus this month's assignment),
          spread over the months left to the date. Measuring from the
          opening balance is what makes "assign half the pace, half is still
          needed" hold; dividing the post-assignment shortfall drifted by
          `assigned / months_left` with every dollar assigned.

        **A card's paydown target reads a signed `available`, and that is
        deliberate.** For a card, `available` is its set-aside, which goes
        NEGATIVE when a payment ran past what any envelope reserved — so
        paying the card down directly makes a balance-measured target ask for
        MORE, not less. It reads backwards and it is right: the payment has
        left your account and nothing has been assigned to cover it. Do not
        floor `available` here; the card row explains the negative in words.
        """
        amount = target.target_amount
        kind = TargetType(target.target_type)
        if kind is TargetType.MONTHLY_FUNDING:
            return amount
        if kind is TargetType.WEEKLY_FUNDING:
            if target.weekday is None:
                raise InvariantViolation("A weekly target needs the day of the week it funds")
            return amount * weekday_occurrences(month, target.weekday)
        if target.target_date is None:
            return max(ZERO, amount - available)
        opening = available - assigned
        months_left = months_between(month_start(month), target.target_date)
        return max(ZERO, amount - opening) / months_left

    def measures_balance(self, target: CategoryTarget) -> bool:
        """Does this target's progress read AVAILABLE rather than ASSIGNED?
        Only an undated savings balance does; a dated one is paced, and its
        month's ask is judged on what was assigned toward that pace."""
        return target.target_type == TargetType.SAVINGS_BALANCE and target.target_date is None

    def calculate_needed(
        self,
        target: CategoryTarget,
        assigned: Decimal,
        available: Decimal,
        *,
        month: date,
    ) -> Decimal:
        """The amount still to assign this month for the target to be met.

        This is what Fill Underfunded moves, so it is the number the budget
        row's pill has to predict. An undated savings balance does not
        subtract `assigned`: its shortfall is measured against `available`,
        which already counts it. Subtracting again would ask for the money
        twice. A pending target still has a `needed` — Fill Underfunded
        fills it; only the nag is held back.
        """
        gross = self.duty(target, assigned=assigned, available=available, month=month)
        if self.measures_balance(target):
            return gross
        return max(ZERO, gross - assigned)

    def calculate_status(
        self,
        target: CategoryTarget,
        assigned: Decimal,
        available: Decimal,
        *,
        month: date,
        today: date,
        funding_day: int,
    ) -> TargetStatus:
        """'funded', 'underfunded', 'overfunded' or 'pending'.

        The pill exists to say what Fill Underfunded will do, so "underfunded"
        means exactly that: `calculate_needed` would move money here. Derived
        from it rather than restated, which is what makes the two unable to
        contradict each other. "pending" is the same fact before the funding
        day (`is_pending`): still needed, not yet nagged about.

        An undated savings goal is judged on the BALANCE, not on what was
        assigned this month. It used to compare `assigned` against a shortfall
        expressed in `available`, so a category holding $600 against a $1,000
        goal read "funded" the moment $400 was assigned — even though $400 of
        that had been spent again and Fill Underfunded would top it up.
        """
        if self.calculate_needed(target, assigned, available, month=month) > 0:
            effective_day = target.check_after_day or funding_day
            return "pending" if is_pending(month, today, effective_day) else "underfunded"

        # Met. Overfunded is "more than it asked for", measured the same way.
        if self.measures_balance(target):
            goal, measure = target.target_amount, available
        else:
            goal = self.duty(target, assigned=assigned, available=available, month=month)
            measure = assigned

        return "overfunded" if measure > goal * Decimal("1.05") else "funded"

    def monthly_pace(
        self,
        target: CategoryTarget,
        *,
        assigned: Decimal,
        available: Decimal,
        month: date,
    ) -> Decimal | None:
        """What this target asks for per month — the pace a wish can count on.

        Exactly the duty, for every shape that has one. An undated savings
        goal has no pace, so it answers None rather than pretending the
        whole shortfall arrives every month. This used to pace a dated
        savings goal by its date while Fill Underfunded filled it whole — a
        documented divergence that is gone now that the duty itself paces.
        """
        if self.measures_balance(target):
            return None
        return self.duty(target, assigned=assigned, available=available, month=month)
