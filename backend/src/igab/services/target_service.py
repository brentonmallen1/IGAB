import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, CategoryTarget
from igab.domain.carryover import carried_in
from igab.domain.dates import month_start, months_between, weekday_occurrences
from igab.domain.enums import TargetStatus, TargetType
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.domain.money import quantize_cents
from igab.domain.targets import MAX_FUNDING_DAY, is_pending
from igab.repositories.target_repo import TargetRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match

ZERO = Decimal("0")

#: The shapes that may carry a `target_limit` ("Stop at $L"): the ones paced
#: by a rate. A savings balance is already a balance to stop at.
CAPPABLE = frozenset({TargetType.MONTHLY_FUNDING, TargetType.WEEKLY_FUNDING})

#: How far past its measure a met target may sit before it reads overfunded.
OVERFUNDED_BAND = Decimal("1.05")


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
        target_limit: Decimal | None = None,
    ) -> None:
        """The shape rules: a weekly target needs its weekday (its duty is
        undefined without one), only a savings balance may carry a date, only
        a monthly or weekly target may stop at a balance, and the day fields
        stay inside the ranges the arithmetic reads."""
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
        if target_limit is not None:
            # A savings balance already is a balance to stop at; a cap on it
            # would be a second goal with no rule for which one wins.
            if kind not in CAPPABLE:
                raise InvariantViolation("Only a monthly or weekly target can stop at a balance")
            if target_limit <= 0:
                raise InvariantViolation("The balance a target stops at has to be more than zero")

    async def upsert(
        self,
        category_id: uuid.UUID,
        target_type: str,
        target_amount: Decimal,
        target_date: date | None = None,
        *,
        target_limit: Decimal | None,
        check_after_day: int | None = None,
        weekday: int | None = None,
        batch_id: uuid.UUID | None = None,
    ) -> CategoryTarget:
        """Create or replace a category's target.

        `target_limit` has no default on purpose: every write states it, so a
        caller that re-saves an existing target (the wishlist's goal sync, the
        planner's apply) cannot drop a cap by not knowing one was there.
        """
        self.validate(
            target_type,
            target_date,
            check_after_day=check_after_day,
            weekday=weekday,
            target_limit=target_limit,
        )
        budget_id = await self._budget_of(category_id)
        existing = await self.repo.get_by_category(category_id)
        fields = dict(
            target_type=target_type,
            target_amount=target_amount,
            target_date=target_date,
            check_after_day=check_after_day,
            weekday=weekday,
            target_limit=target_limit,
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

    #
    # Every method takes the month's three served figures — assigned,
    # activity, available — because a capped target measures from the balance
    # CARRIED IN (`domain.carryover.carried_in`), and that is the one figure
    # the other two cannot give without the third. Required, not defaulted:
    # a caller that forgot activity would read a capped envelope's spending
    # as money it never had.

    def duty(
        self,
        target: CategoryTarget,
        *,
        assigned: Decimal,
        activity: Decimal,
        available: Decimal,
        month: date,
    ) -> Decimal:
        """This month's full duty, before crediting what was assigned.

        - **Monthly**: the amount.
        - **Weekly**: the amount times the number of that weekday in
          `month` — 4 or 5 — so "$50 every Friday" asks for five in a
          five-Friday month. It used to be a flat monthly figure.
        - **Monthly or weekly with a stop** (`target_limit`, L): the rate,
          but never more than the month needs to bring what it carried in up
          to L — `min(rate, max(0, L − carried in))`. Measured from the
          balance carried in, not from Available, so spending this month
          does not raise the ask: "$100 a month until it holds $1,000" asks
          for $100 while the envelope arrives short, $40 the month it
          arrives holding $960, and nothing once it arrives holding $1,000 —
          whatever the month then spends. An overspent opening (negative,
          on an imported or card-corrected envelope) asks for the full rate.
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
        if kind in CAPPABLE:
            if kind is TargetType.MONTHLY_FUNDING:
                rate = amount
            else:
                if target.weekday is None:
                    raise InvariantViolation("A weekly target needs the day of the week it funds")
                rate = amount * weekday_occurrences(month, target.weekday)
            if target.target_limit is None:
                return rate
            opening = carried_in(assigned=assigned, activity=activity, available=available)
            return min(rate, max(ZERO, target.target_limit - opening))
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

    def ceiling(self, target: CategoryTarget) -> Decimal | None:
        """The balance past which money in this envelope is more than the
        target wants: an undated savings balance's goal, or a monthly or
        weekly target's stop (`target_limit`). None for a target paced by
        the month alone.

        A target with a ceiling is judged overfunded on AVAILABLE against it,
        and Reduce Overfunded returns only what sits above it — never what
        the envelope needs to stay there."""
        if self.measures_balance(target):
            return target.target_amount
        return target.target_limit

    def target_assigned(
        self,
        target: CategoryTarget,
        *,
        assigned: Decimal,
        activity: Decimal,
        available: Decimal,
        month: date,
    ) -> Decimal:
        """What this month's ASSIGNED should read for the target to be met —
        the figure Auto-assign's "target amounts" sets, in cents.

        Short of the target, it is assigned plus what is still needed — the
        same top-up Fill Underfunded makes. Past it, every target paced by
        month (monthly, weekly, dated savings) comes back down by what
        Reduce Overfunded would return (`returnable`): to the duty, as far
        as the envelope still holds the excess, or — for a target with a
        stop — to the stop, and no further. An undated savings balance has
        no monthly figure; it is topped up and never lowered here — holding
        more than a balance target is no shortfall.

        One rule for the Assign dropdown, the inspector's per-category button
        and the figure the budget month serves beside it.
        """
        needed = self.calculate_needed(target, assigned, available, activity=activity, month=month)
        if needed > 0 or self.measures_balance(target):
            return quantize_cents(assigned + needed)
        return assigned - self.returnable(
            target, assigned=assigned, activity=activity, available=available, month=month
        )

    def returnable(
        self,
        target: CategoryTarget,
        *,
        assigned: Decimal,
        activity: Decimal,
        available: Decimal,
        month: date,
    ) -> Decimal:
        """What Reduce Overfunded hands back to Ready to Assign: never
        negative, and zero for a target still short.

        - **No ceiling** (monthly, weekly, dated savings): what was assigned
          above the duty, as far as the envelope still holds it. Money spent
          above a target cannot return to Ready to Assign, and taking it
          anyway turned the envelope red — Reduce Overfunded's old bug.
        - **A ceiling** (a stop, or an undated savings goal): what Available
          holds above it, as far as this month assigned it. The envelope
          comes back down to the ceiling and stops there; money carried in
          from earlier months is not this month's to return. An undated
          savings goal used to give back everything assigned this month,
          leaving a $1,000 goal holding $900 after "reducing overfunding"
          from $1,200.
        """
        if self.calculate_needed(target, assigned, available, activity=activity, month=month) > 0:
            return ZERO
        ceiling = self.ceiling(target)
        if ceiling is None:
            duty = self.duty(
                target, assigned=assigned, activity=activity, available=available, month=month
            )
            over = assigned - quantize_cents(duty)
            room = max(available, ZERO)
        else:
            over = available - ceiling
            room = max(assigned, ZERO)
        return max(ZERO, min(over, room))

    def calculate_needed(
        self,
        target: CategoryTarget,
        assigned: Decimal,
        available: Decimal,
        *,
        activity: Decimal,
        month: date,
    ) -> Decimal:
        """The amount still to assign this month for the target to be met.

        This is what Fill Underfunded moves, so it is the number the budget
        row's pill has to predict. An undated savings balance does not
        subtract `assigned`: its shortfall is measured against `available`,
        which already counts it. Subtracting again would ask for the money
        twice. A pending target still has a `needed` — Fill Underfunded
        fills it; only the nag is held back.

        A target with a stop never asks past it: the shortfall against the
        duty, but no more than Available is short of L. Money that arrived
        in the envelope this month (a refund, a transfer in) counts toward
        the stop, so "fully funded while it holds L" is true whatever put
        the money there.
        """
        gross = self.duty(
            target, assigned=assigned, activity=activity, available=available, month=month
        )
        if self.measures_balance(target):
            return gross
        short = gross - assigned
        if target.target_limit is not None:
            short = min(short, target.target_limit - available)
        return max(ZERO, short)

    def calculate_status(
        self,
        target: CategoryTarget,
        assigned: Decimal,
        available: Decimal,
        *,
        activity: Decimal,
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

        A target with a ceiling (`ceiling`) is judged on the BALANCE, not on
        what was assigned this month. It used to compare `assigned` against
        a shortfall expressed in `available`, so a category holding $600
        against a $1,000 goal read "funded" the moment $400 was assigned —
        even though $400 of that had been spent again and Fill Underfunded
        would top it up. A target with a stop reads overfunded only once
        Available is past the stop by more than the band: assigning ahead of
        the rate toward the stop is not overfunding, and holding the stop
        exactly is funded however little this month assigned.
        """
        if self.calculate_needed(target, assigned, available, activity=activity, month=month) > 0:
            effective_day = target.check_after_day or funding_day
            return "pending" if is_pending(month, today, effective_day) else "underfunded"

        # Met. Overfunded is "more than it asked for", measured the same way.
        ceiling = self.ceiling(target)
        if ceiling is not None:
            goal, measure = ceiling, available
        else:
            goal = self.duty(
                target, assigned=assigned, activity=activity, available=available, month=month
            )
            measure = assigned

        return "overfunded" if measure > goal * OVERFUNDED_BAND else "funded"

    def monthly_pace(
        self,
        target: CategoryTarget,
        *,
        assigned: Decimal,
        activity: Decimal,
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
        return self.duty(
            target, assigned=assigned, activity=activity, available=available, month=month
        )
