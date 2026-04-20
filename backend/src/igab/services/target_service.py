import uuid
from datetime import date
from decimal import Decimal

from igab.db.models import CategoryTarget
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

    def calculate_status(
        self,
        target: CategoryTarget,
        assigned: Decimal,
        available: Decimal,
    ) -> str:
        """Returns 'funded', 'underfunded', or 'overfunded'."""
        today = date.today()
        needed: Decimal

        if target.target_type == "monthly_funding":
            needed = target.target_amount
        elif target.target_type == "savings_balance":
            shortfall = target.target_amount - available
            needed = max(Decimal("0"), shortfall)
        elif target.target_type == "needed_for_spending":
            if target.target_date:
                months_left = _months_between(today, target.target_date)
                remaining = target.target_amount - available
                needed = remaining / max(1, months_left)
            else:
                needed = target.target_amount
        elif target.target_type == "weekly_funding":
            needed = target.target_amount
        else:
            needed = target.target_amount

        if assigned >= needed:
            return "overfunded" if assigned > needed * Decimal("1.05") else "funded"
        return "underfunded"


def _months_between(start: date, end: date) -> int:
    return max(1, (end.year - start.year) * 12 + end.month - start.month)
