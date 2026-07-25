import uuid

from rapidfuzz import fuzz
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from igab.db.models import Payee, Transaction
from igab.repositories.base import BaseRepository

PAYEE_FUZZY_THRESHOLD = 80


class PayeeRepository(BaseRepository[Payee]):
    model = Payee

    async def get_all(self, budget_id: uuid.UUID) -> list[Payee]:
        result = await self.session.execute(
            select(Payee)
            .options(selectinload(Payee.tags))
            .where(Payee.budget_id == budget_id, Payee.is_deleted == False)  # noqa: E712
            .order_by(Payee.name)
        )
        return list(result.scalars().all())

    async def get_located_visits(
        self,
        budget_id: uuid.UUID,
        min_lat: float,
        max_lat: float,
        min_lng: float,
        max_lng: float,
    ) -> list[tuple]:
        """Located, non-deleted transactions joined to their payees within a
        bounding box: (payee_id, name, default_category_id, lat, lng, date).
        Exact radius filtering happens in the caller via haversine."""
        result = await self.session.execute(
            select(
                Payee.id,
                Payee.name,
                Payee.default_category_id,
                Transaction.latitude,
                Transaction.longitude,
                Transaction.date,
            )
            .join(Payee, Payee.id == Transaction.payee_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.latitude.is_not(None),
                Transaction.latitude.between(min_lat, max_lat),
                Transaction.longitude.between(min_lng, max_lng),
                Payee.is_deleted == False,  # noqa: E712
            )
        )
        return [tuple(row) for row in result.all()]

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

    async def find_best_match(self, budget_id: uuid.UUID, raw_name: str) -> Payee | None:
        """Fuzzy-match raw_name against payee names and mapping_samples.

        Scores each payee against its canonical name and any comma-separated
        mapping_samples. Returns the best match above PAYEE_FUZZY_THRESHOLD.
        """
        payees = await self.get_all(budget_id)
        raw_lower = raw_name.lower()
        best_match: Payee | None = None
        best_score = 0

        for payee in payees:
            candidates = [payee.name]
            if payee.mapping_samples:
                candidates.extend(s.strip() for s in payee.mapping_samples.split(",") if s.strip())

            for candidate in candidates:
                score = fuzz.token_set_ratio(raw_lower, candidate.lower())
                if score > best_score and score >= PAYEE_FUZZY_THRESHOLD:
                    best_score = score
                    best_match = payee

        return best_match

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
            update(Transaction).where(Transaction.payee_id == source_id).values(payee_id=target_id)
        )
        await self.soft_delete(source_id)
        await self.session.flush()

    async def delete(self, payee_id: uuid.UUID) -> None:
        await self.soft_delete(payee_id)
