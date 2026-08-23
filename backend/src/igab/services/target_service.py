import uuid
from datetime import date
from decimal import Decimal

from igab.db.models import CategoryTarget
from igab.domain.dates import months_between
from igab.repositories.target_repo import TargetRepository


class TargetService:
    def __init__(self, repo: TargetRepository) -> None:
        self.repo = repo

    async def get(self, category_id: uuid.UUID) -> CategoryTarget | None:
        return await self.repo.get_by_category(category_id)

    async def upsert(
        self,
        category_id: uuid.UUID,
        target_type: str,
        target_amount: Decimal,
        target_date: date | None = None,
        repeat_frequency: str | None = None,
    ) -> CategoryTarget:
        existing = await self.repo.get_by_category(category_id)
        if existing is None:
            return await self.repo.create(
                category_id=category_id,
                target_type=target_type,
                target_amount=target_amount,
                target_date=target_date,
                repeat_frequency=repeat_frequency,
            )
        return await self.repo.update(
            existing.id,
            target_type=target_type,
            target_amount=target_amount,
            target_date=target_date,
            repeat_frequency=repeat_frequency,
        )

    async def delete(self, category_id: uuid.UUID) -> None:
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
        """
        today = today or date.today()
        amount = target.target_amount

        if target.target_type == "savings_balance":
            return max(Decimal("0"), amount - available)
        if target.target_type == "needed_for_spending" and target.target_date:
            months_left = months_between(today, target.target_date)
            return max(Decimal("0"), amount - available) / months_left
        return amount

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
    ) -> str:
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
