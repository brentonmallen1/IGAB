import datetime
import uuid

from rapidfuzz import fuzz
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from igab.db.models import Payee, Transaction
from igab.domain.exceptions import InvariantViolation
from igab.repositories.base import BaseRepository

PAYEE_FUZZY_THRESHOLD = 80
DUPLICATE_SUGGESTION_THRESHOLD = 75


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

    async def get_all_with_counts(
        self, budget_id: uuid.UUID
    ) -> list[tuple[Payee, int, datetime.date | None]]:
        """All payees with their transaction count and most recent transaction
        date, in a single grouped query (the count used to be an N+1 loop)."""
        stats = (
            select(
                Transaction.payee_id.label("payee_id"),
                func.count(Transaction.id).label("txn_count"),
                func.max(Transaction.date).label("last_used"),
            )
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
            )
            .group_by(Transaction.payee_id)
            .subquery()
        )
        result = await self.session.execute(
            select(Payee, func.coalesce(stats.c.txn_count, 0), stats.c.last_used)
            .options(selectinload(Payee.tags))
            .outerjoin(stats, stats.c.payee_id == Payee.id)
            .where(Payee.budget_id == budget_id, Payee.is_deleted == False)  # noqa: E712
            .order_by(Payee.name)
        )
        return [(payee, count, last_used) for payee, count, last_used in result.all()]

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
        """Reassign all transactions from source to target, then soft-delete source.

        The route guards `source_id` (PayeeAccess) but `target_id` comes from the
        request body; require both live in the same budget so a merge cannot
        re-point the caller's transactions onto another budget's payee.
        """
        source = await self.session.get(Payee, source_id)
        target = await self.session.get(Payee, target_id)
        if (
            source is None
            or target is None
            or source.is_deleted
            or target.is_deleted
            or source.budget_id != target.budget_id
        ):
            raise InvariantViolation("Cannot merge payees from different budgets")
        await self.session.execute(
            update(Transaction).where(Transaction.payee_id == source_id).values(payee_id=target_id)
        )
        await self.soft_delete(source_id)
        await self.session.flush()

    async def delete(self, payee_id: uuid.UUID) -> None:
        await self.soft_delete(payee_id)

    async def find_duplicate_groups(
        self, budget_id: uuid.UUID, threshold: int = DUPLICATE_SUGGESTION_THRESHOLD
    ) -> list[dict]:
        """Find groups of similar payees using fuzzy matching.

        Returns groups of payees with similarity >= threshold.
        Each group contains payees that are similar to each other.
        Groups are sorted by total transaction count descending.
        """
        # Exclude transfer payees
        payees_with_counts = [
            (p, c)
            for p, c, _last_used in await self.get_all_with_counts(budget_id)
            if p.transfer_account_id is None
        ]

        if len(payees_with_counts) < 2:
            return []

        # Build adjacency using Union-Find for grouping
        parent: dict[str, str] = {}
        rank: dict[str, int] = {}

        def find(x: str) -> str:
            if parent.get(x, x) != x:
                parent[x] = find(parent[x])
            return parent.get(x, x)

        def union(x: str, y: str) -> None:
            px, py = find(x), find(y)
            if px == py:
                return
            if rank.get(px, 0) < rank.get(py, 0):
                px, py = py, px
            parent[py] = px
            if rank.get(px, 0) == rank.get(py, 0):
                rank[px] = rank.get(px, 0) + 1

        # Compare all pairs
        for i, (p1, _) in enumerate(payees_with_counts):
            for p2, _ in payees_with_counts[i + 1 :]:
                score = fuzz.token_set_ratio(p1.name.lower(), p2.name.lower())
                if score >= threshold:
                    union(str(p1.id), str(p2.id))

        # Build groups from Union-Find
        groups_map: dict[str, list[tuple[Payee, int]]] = {}
        for payee, count in payees_with_counts:
            root = find(str(payee.id))
            if root not in groups_map:
                groups_map[root] = []
            groups_map[root].append((payee, count))

        # Filter to groups with 2+ payees, compute total count, sort
        result = []
        for members in groups_map.values():
            if len(members) < 2:
                continue
            total_count = sum(c for _, c in members)
            # Compute average similarity within group
            if len(members) == 2:
                similarity = int(
                    fuzz.token_set_ratio(members[0][0].name.lower(), members[1][0].name.lower())
                )
            else:
                # Average of all pairwise similarities
                sims = []
                for i, (p1, _) in enumerate(members):
                    for p2, _ in members[i + 1 :]:
                        sims.append(fuzz.token_set_ratio(p1.name.lower(), p2.name.lower()))
                similarity = int(sum(sims) / len(sims)) if sims else 0

            result.append(
                {
                    "payees": [
                        {
                            "id": str(p.id),
                            "name": p.name,
                            "transaction_count": c,
                        }
                        for p, c in sorted(members, key=lambda x: -x[1])
                    ],
                    "similarity": similarity,
                    "total_count": total_count,
                }
            )

        # Sort by total transaction count descending
        result.sort(key=lambda g: -g["total_count"])
        return result
