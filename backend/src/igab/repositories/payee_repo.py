import uuid

from sqlalchemy import func, select, update

from igab.db.models import Payee, Transaction
from igab.repositories.base import BaseRepository


class PayeeRepository(BaseRepository[Payee]):
    model = Payee

    async def get_all(self, budget_id: uuid.UUID) -> list[Payee]:
        result = await self.session.execute(
            select(Payee)
            .where(Payee.budget_id == budget_id, Payee.is_deleted == False)  # noqa: E712
            .order_by(Payee.name)
        )
        return list(result.scalars().all())

    async def get_all_with_counts(self, budget_id: uuid.UUID) -> list[tuple[Payee, int]]:
        payees = await self.get_all(budget_id)
        results = []
        for payee in payees:
            count_result = await self.session.execute(
                select(func.count(Transaction.id)).where(
                    Transaction.payee_id == payee.id,
                    Transaction.is_deleted == False,  # noqa: E712
                )
            )
            count = count_result.scalar_one()
            results.append((payee, count))
        return results

    async def find_by_name(self, budget_id: uuid.UUID, name: str) -> Payee | None:
        result = await self.session.execute(
            select(Payee).where(
                Payee.budget_id == budget_id,
                func.lower(Payee.name) == name.lower(),
                Payee.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def find_or_create(self, budget_id: uuid.UUID, name: str) -> Payee:
        payee = await self.find_by_name(budget_id, name)
        if payee is None:
            payee = await self.create(budget_id=budget_id, name=name)
        return payee

    async def find_or_create_batch(
        self, budget_id: uuid.UUID, names: list[str]
    ) -> dict[str, uuid.UUID]:
        """Resolve a list of payee names to IDs, creating missing ones. Returns name→id map."""
        if not names:
            return {}

        unique_names = list({n for n in names if n})
        result = await self.session.execute(
            select(Payee).where(
                Payee.budget_id == budget_id,
                func.lower(Payee.name).in_([n.lower() for n in unique_names]),
                Payee.is_deleted == False,  # noqa: E712
            )
        )
        existing = {p.name.lower(): p for p in result.scalars().all()}

        payee_map: dict[str, uuid.UUID] = {}
        for name in unique_names:
            if name.lower() in existing:
                payee_map[name] = existing[name.lower()].id
            else:
                payee = await self.create(budget_id=budget_id, name=name)
                payee_map[name] = payee.id
        return payee_map

    async def merge(self, source_id: uuid.UUID, target_id: uuid.UUID) -> None:
        """Reassign all transactions from source to target, then soft-delete source."""
        await self.session.execute(
            update(Transaction)
            .where(Transaction.payee_id == source_id)
            .values(payee_id=target_id)
        )
        await self.soft_delete(source_id)
        await self.session.flush()

    async def delete(self, payee_id: uuid.UUID) -> None:
        await self.soft_delete(payee_id)
