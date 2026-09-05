import uuid
from datetime import date
from decimal import Decimal

from igab.db.models import Category, CategoryTarget
from igab.domain.dates import months_between
from igab.domain.enums import TargetStatus
from igab.domain.exceptions import NotFoundError
from igab.repositories.target_repo import TargetRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match


class TargetService:
    def __init__(self, repo: TargetRepository) -> None:
        self.repo = repo
        # Targets are money rules, so every mutation records (change_log.py).
        # Recording lives here rather than in the router because the
        # wishlist's envelope goals and the planner's apply-targets both
        # write through this service — a router-side record would cover one
        # path of three. `batch_id` lets those callers group the target row
        # with their own, so the compound operation undoes as one unit.
        self.changes = ChangeRecorder(repo.session)

    async def _budget_of(self, category_id: uuid.UUID) -> uuid.UUID:
        category = await self.repo.session.get(Category, category_id)
        if category is None:
            raise NotFoundError("Category", str(category_id))
        return category.budget_id

    async def get(self, category_id: uuid.UUID) -> CategoryTarget | None:
        return await self.repo.get_by_category(category_id)

    async def upsert(
        self,
        category_id: uuid.UUID,
        target_type: str,
        target_amount: Decimal,
        target_date: date | None = None,
        repeat_frequency: str | None = None,
        *,
        batch_id: uuid.UUID | None = None,
    ) -> CategoryTarget:
        budget_id = await self._budget_of(category_id)
        existing = await self.repo.get_by_category(category_id)
        if existing is None:
            created = await self.repo.create(
                category_id=category_id,
                target_type=target_type,
                target_amount=target_amount,
                target_date=target_date,
                repeat_frequency=repeat_frequency,
            )
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
        updated = await self.repo.update(
            existing.id,
            target_type=target_type,
            target_amount=target_amount,
            target_date=target_date,
            repeat_frequency=repeat_frequency,
        )
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

    def needed_gross(
        self,
        target: CategoryTarget,
        available: Decimal,
        today: date | None = None,
    ) -> Decimal:
        """This month's full duty, before crediting anything assigned this month.

        One definition, used by both `calculate_needed` and `calculate_status`,
        because a pill that says "funded" has to mean "Fill Underfunded will
        leave this alone". They were separate, and disagreed: `calculate_status`
        clamped the savings-balance shortfall at zero but left the dated
        needed-for-spending shortfall signed, so the two balance-measured target
        types behaved differently for no stated reason.

        Two shapes of target, and the difference is which number they measure:

        - **Balance-measured** (savings balance; needed-for-spending with a
          date) measure AVAILABLE — the balance being built. `available`
          already contains this month's assignment, so the shortfall is net of
          it and must not have `assigned` subtracted again.
        - **Funding** (monthly, weekly, undated needed-for-spending) measure
          ASSIGNED — a duty owed every period regardless of the balance.

        **A card's paydown target reads a signed `available`, and that is
        deliberate.** For a card, `available` is its set-aside, which goes
        NEGATIVE when a payment ran past what any envelope reserved — so
        paying the card down directly makes a balance-measured target ask for
        MORE, not less. It reads backwards and it is right: the payment has
        left your account and nothing has been assigned to cover it, so the
        target is naming a real duty. Do not floor `available` here to make
        the number look friendlier; that would report a funded card while its
        envelope is in the red. The card row explains the negative in words
        (`cardRow.ts`), which is the place for the reassurance.
        """
        today = today or date.today()
        amount = target.target_amount

        if target.target_type == "savings_balance":
            return max(Decimal("0"), amount - available)
        if target.target_type == "needed_for_spending" and target.target_date:
            months_left = months_between(today, target.target_date)
            return max(Decimal("0"), amount - available) / months_left
        return amount

    def monthly_pace(
        self,
        target: CategoryTarget,
        available: Decimal,
        today: date | None = None,
    ) -> Decimal | None:
        """What this target asks for per month — the pace a wish can count on.

        Funding targets (monthly, weekly, undated needed-for-spending) are
        their amount, and a dated needed-for-spending target is its shortfall
        spread over the months left: both exactly `needed_gross`. A dated
        savings goal is ALSO paced by its date here, which is a deliberate
        divergence from Fill Underfunded: that fills a savings goal whole,
        because it is asking what to assign now; this asks how fast the
        balance is being built, which is what "about N months" means. An
        undated savings goal has no pace, so it answers None rather than
        pretending the whole shortfall arrives every month.
        """
        today = today or date.today()
        if target.target_type == "savings_balance":
            if not target.target_date:
                return None
            months_left = months_between(today, target.target_date)
            return max(Decimal("0"), target.target_amount - available) / months_left
        return self.needed_gross(target, available, today)

    def measures_balance(self, target: CategoryTarget) -> bool:
        """Does this target's progress read AVAILABLE rather than ASSIGNED?"""
        return target.target_type == "savings_balance" or (
            target.target_type == "needed_for_spending" and bool(target.target_date)
        )

    def calculate_needed(
        self,
        target: CategoryTarget,
        assigned: Decimal,
        available: Decimal,
        today: date | None = None,
    ) -> Decimal:
        """The amount still to assign this month for the target to be met.

        This is what Fill Underfunded moves, so it is the number the budget
        row's pill has to predict.

        A savings-balance target does not subtract `assigned`: its shortfall is
        measured against `available`, which already counts it. Subtracting
        again would ask for the money twice.
        """
        gross = self.needed_gross(target, available, today)
        if target.target_type == "savings_balance":
            return gross
        return max(Decimal("0"), gross - assigned)

    def calculate_status(
        self,
        target: CategoryTarget,
        assigned: Decimal,
        available: Decimal,
        today: date | None = None,
    ) -> TargetStatus:
        """Returns 'funded', 'underfunded', or 'overfunded'.

        The pill exists to say what Fill Underfunded will do, so "underfunded"
        means exactly that: `calculate_needed` would move money here. Derived
        from it rather than restated, which is what makes the two unable to
        contradict each other.

        A savings-balance goal is judged on the BALANCE, not on what was
        assigned this month. It used to compare `assigned` against a shortfall
        expressed in `available`, so a category holding $600 against a $1,000
        goal read "funded" the moment $400 was assigned — even though $400 of
        that had been spent again and Fill Underfunded would top it up. The
        other target types are funding duties and are still judged on
        `assigned`; a dated needed-for-spending goal asks for a monthly pace,
        not the whole balance, so it is not judged on the balance either.
        """
        if self.calculate_needed(target, assigned, available, today) > 0:
            return "underfunded"

        # Met. Overfunded is "more than it asked for", measured the same way.
        if target.target_type == "savings_balance":
            goal, measure = target.target_amount, available
        else:
            goal, measure = self.needed_gross(target, available, today), assigned

        return "overfunded" if measure > goal * Decimal("1.05") else "funded"
