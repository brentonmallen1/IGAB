import datetime
import re
import uuid
from typing import TypedDict

from rapidfuzz import fuzz
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from igab.db.models import Payee, Transaction
from igab.domain.exceptions import InvariantViolation
from igab.repositories.base import BaseRepository

PAYEE_FUZZY_THRESHOLD = 80
DUPLICATE_SUGGESTION_THRESHOLD = 75


class DuplicatePayee(TypedDict):
    id: str
    name: str
    transaction_count: int


class DuplicateGroup(TypedDict):
    """A cluster of payees judged to be the same one.

    Typed so `-g["total_count"]` narrows to int. As a bare dict the row is
    dict[str, str | int | list[...]], and unary minus is not defined across
    that union.
    """

    payees: list[DuplicatePayee]
    similarity: float
    total_count: int


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

    async def get_with_tags(self, payee_id: uuid.UUID) -> Payee | None:
        """Fetch one payee with tags eagerly loaded, for response serialization
        (a lazy tags load would raise MissingGreenlet under the async driver)."""
        result = await self.session.execute(
            select(Payee)
            .options(selectinload(Payee.tags))
            .where(Payee.id == payee_id, Payee.is_deleted == False)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def find_by_name(self, budget_id: uuid.UUID, name: str) -> Payee | None:
        result = await self.session.execute(
            select(Payee).where(
                Payee.budget_id == budget_id,
                func.lower(Payee.name) == name.lower(),
                Payee.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _match_by_pattern(payees: list[Payee], raw_name: str) -> Payee | None:
        """Match raw_name against payee match_pattern regexes (case-insensitive).

        Patterns are user-authored and validated at write time, but a stored
        pattern that no longer compiles is skipped rather than failing the
        whole resolution. When several payees match, the longest pattern wins
        (most specific), with name order as the tiebreaker via get_all's sort.
        """
        best: Payee | None = None
        for payee in payees:
            if not payee.match_pattern:
                continue
            try:
                if re.search(payee.match_pattern, raw_name, re.IGNORECASE):
                    if best is None or len(payee.match_pattern) > len(best.match_pattern or ""):
                        best = payee
            except re.error:
                continue
        return best

    async def find_by_pattern(self, budget_id: uuid.UUID, raw_name: str) -> Payee | None:
        return self._match_by_pattern(await self.get_all(budget_id), raw_name)

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

    #: The name every transfer payee carries, in both the app's own transfer
    #: flow and YNAB's register export. Kept here so the importer and the
    #: transaction service agree on one spelling.
    TRANSFER_PREFIX = "Transfer : "

    @classmethod
    def transfer_payee_name(cls, account_name: str) -> str:
        return f"{cls.TRANSFER_PREFIX}{account_name}"

    async def find_or_create_transfer(
        self, budget_id: uuid.UUID, account_id: uuid.UUID, account_name: str
    ) -> Payee:
        """Resolve the "Transfer : <account>" payee, guaranteeing that
        `transfer_account_id` points at the account it names.

        A payee is what marks a row as transfer-shaped once its partner link is
        gone, so the field has to be set for every transfer payee — not only the
        ones the sample-budget generator makes. An existing row created before
        this (or by an import) is adopted and backfilled rather than duplicated,
        since `uq_payee_budget_name` allows only one payee per name.
        """
        name = self.transfer_payee_name(account_name)
        # Exact match, not find_by_name's case-insensitive one. The unique
        # constraint is case-sensitive, so "Savings" and "savings" are two
        # accounts with two distinct payees — a case-insensitive lookup found
        # the first one's payee for the second account, saw it already bound,
        # and returned it. Every unlinked leg into "savings" then resolved its
        # counterpart to the wrong account, which can classify a debt payment
        # as savings.
        payee = (
            await self.session.execute(
                select(Payee).where(
                    Payee.budget_id == budget_id,
                    Payee.name == name,
                    Payee.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()

        if payee is None:
            return await self.create(budget_id=budget_id, name=name, transfer_account_id=account_id)
        if payee.transfer_account_id is None:
            payee.transfer_account_id = account_id
            await self.session.flush()
        elif payee.transfer_account_id != account_id:
            # Reachable by renaming an account and reusing its old name. Both
            # answers are wrong: re-pointing rewrites what existing transfers
            # mean, and returning it as-is misfiles every future one. Refuse,
            # so a person decides.
            raise InvariantViolation(
                f'Payee "{name}" already points at a different account. '
                "Rename one of them so each transfer payee names one account."
            )
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

        # Load pattern payees once so imported names can hit user-defined
        # regexes before falling through to creating brand-new payees.
        all_payees = await self.get_all(budget_id)
        pattern_payees = [p for p in all_payees if p.match_pattern]

        payee_map: dict[str, uuid.UUID] = {}
        for name in unique_names:
            if name.lower() in existing:
                payee_map[name] = existing[name.lower()].id
                continue
            matched = self._match_by_pattern(pattern_payees, name)
            if matched is not None:
                payee_map[name] = matched.id
                continue
            payee = await self.create(budget_id=budget_id, name=name)
            payee_map[name] = payee.id
        return payee_map

    async def merge(self, source_id: uuid.UUID, target_id: uuid.UUID) -> list[uuid.UUID]:
        """Reassign all transactions from source to target, then soft-delete source.

        The route guards `source_id` (PayeeAccess) but `target_id` comes from the
        request body; require both live in the same budget so a merge cannot
        re-point the caller's transactions onto another budget's payee.

        Returns the ids of the transactions that were moved, so the change log
        can undo the merge by moving exactly those back.
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
        result = await self.session.execute(
            update(Transaction)
            .where(Transaction.payee_id == source_id)
            .values(payee_id=target_id)
            .returning(Transaction.id)
            .execution_options(synchronize_session=False)
        )
        moved = list(result.scalars().all())
        await self.soft_delete(source_id)
        await self.session.flush()
        return moved

    async def delete(self, payee_id: uuid.UUID) -> None:
        await self.soft_delete(payee_id)

    async def find_duplicate_groups(
        self, budget_id: uuid.UUID, threshold: int = DUPLICATE_SUGGESTION_THRESHOLD
    ) -> list[DuplicateGroup]:
        """Find groups of similar payees using fuzzy matching.

        Complete-linkage grouping: a payee joins a group only if its similarity
        to EVERY member is >= threshold, so a chain like A~B, B~C can never pull
        a dissimilar A and C into one group. The reported similarity is the
        minimum pairwise score in the group (the weakest link), which by
        construction is always >= threshold.

        Groups are sorted by total transaction count descending.
        """
        # Exclude transfer payees
        payees_with_counts = [
            (p, c)
            for p, c, _last_used in await self.get_all_with_counts(budget_id)
            if p.transfer_account_id is None
        ]

        n = len(payees_with_counts)
        if n < 2:
            return []

        names = [p.name.lower() for p, _ in payees_with_counts]
        score = [[0] * n for _ in range(n)]
        pairs: list[tuple[int, int, int]] = []
        for i in range(n):
            for j in range(i + 1, n):
                s = int(fuzz.token_set_ratio(names[i], names[j]))
                score[i][j] = score[j][i] = s
                if s >= threshold:
                    pairs.append((s, i, j))

        # Greedy agglomeration, strongest pairs first, so the closest names
        # seed groups and borderline members attach to their best match.
        pairs.sort(key=lambda t: -t[0])
        group_of: dict[int, int] = {}
        groups: dict[int, list[int]] = {}
        next_gid = 0

        for _s, i, j in pairs:
            gi, gj = group_of.get(i), group_of.get(j)
            if gi is None and gj is None:
                groups[next_gid] = [i, j]
                group_of[i] = group_of[j] = next_gid
                next_gid += 1
            elif gi is None or gj is None:
                loner, gid = (i, gj) if gj is not None else (j, gi)
                if gid is not None and all(score[loner][m] >= threshold for m in groups[gid]):
                    groups[gid].append(loner)
                    group_of[loner] = gid
            elif gi != gj:
                if all(score[a][b] >= threshold for a in groups[gi] for b in groups[gj]):
                    for m in groups[gj]:
                        group_of[m] = gi
                    groups[gi].extend(groups.pop(gj))

        result: list[DuplicateGroup] = []
        for indices in groups.values():
            members = [payees_with_counts[i] for i in indices]
            total_count = sum(c for _, c in members)
            # Weakest link in the group — honest about the worst pair
            similarity = min(score[a][b] for x, a in enumerate(indices) for b in indices[x + 1 :])

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
