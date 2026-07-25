import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Integer, and_, case, cast, func, insert, or_, select, update

from igab.db.models import Payee, Transaction
from igab.repositories.base import BaseRepository
from igab.repositories.txn_filters import CASH_FLOW_ROW, LEAF, NOT_DELETED, PARENT_ROW, POSTED

if TYPE_CHECKING:
    import polars as pl


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction

    async def get_for_account(
        self,
        account_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
        start_date: date | None = None,
        end_date: date | None = None,
        search: str | None = None,
        cleared: str | None = None,
        exclude_cleared: str | None = None,
        uncategorized: bool = False,
        unapproved: bool = False,
        is_or_mode: bool = False,
        category_ids: list[uuid.UUID] | None = None,
        payee_ids: list[uuid.UUID] | None = None,
        amount_min: float | None = None,
        amount_max: float | None = None,
    ) -> list[Transaction]:
        q = select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.parent_transaction_id.is_(None),
        )
        if search:
            q = q.outerjoin(Payee, Transaction.payee_id == Payee.id)
            pattern = f"%{search}%"
            q = q.where(or_(Payee.name.ilike(pattern), Transaction.memo.ilike(pattern)))
        if cleared:
            q = q.where(Transaction.cleared == cleared)
        if exclude_cleared:
            q = q.where(Transaction.cleared != exclude_cleared)
        if uncategorized and unapproved and is_or_mode:
            q = q.where(
                or_(
                    and_(
                        Transaction.category_id.is_(None),
                        Transaction.is_split == False,  # noqa: E712
                    ),
                    Transaction.approved == False,  # noqa: E712
                )
            )
        else:
            if uncategorized:
                q = q.where(
                    Transaction.category_id.is_(None),
                    Transaction.is_split == False,  # noqa: E712
                )
            if unapproved:
                q = q.where(Transaction.approved == False)  # noqa: E712
        if start_date:
            q = q.where(Transaction.date >= start_date)
        if end_date:
            q = q.where(Transaction.date <= end_date)
        if category_ids:
            q = q.where(Transaction.category_id.in_(category_ids))
        if payee_ids:
            q = q.where(Transaction.payee_id.in_(payee_ids))
        if amount_min is not None:
            q = q.where(func.abs(Transaction.amount) >= amount_min)
        if amount_max is not None:
            q = q.where(func.abs(Transaction.amount) <= amount_max)
        priority_rank = case(
            (Transaction.cleared == "pending", 0),
            (
                and_(
                    Transaction.category_id.is_(None),
                    Transaction.transfer_id.is_(None),
                    Transaction.is_split == False,  # noqa: E712
                ),
                1,
            ),
            (Transaction.cleared == "uncleared", 2),
            else_=3,
        )
        q = q.order_by(priority_rank, Transaction.date.desc(), Transaction.created_at.desc())
        result = await self.session.execute(q.limit(limit).offset(offset))
        return list(result.scalars().all())

    async def list_for_budget(
        self,
        budget_id: uuid.UUID,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        search: str | None = None,
        category_ids: list[uuid.UUID] | None = None,
        payee_ids: list[uuid.UUID] | None = None,
        account_ids: list[uuid.UUID] | None = None,
        scope: str = "parent",
        posted_only: bool = False,
        cash_flow_only: bool = False,
        direction: str | None = None,
        day_of_week: int | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[Transaction], int, Decimal]:
        """Budget-wide listing for report drill-downs.

        scope="leaf" selects category-carrying rows (split children included,
        parents excluded); scope="parent" selects account-balance rows. The
        count/sum aggregate runs over the same predicate as the page query so
        callers can reconcile a paginated list against report totals.
        """
        where = [Transaction.budget_id == budget_id, NOT_DELETED]
        where.append(LEAF if scope == "leaf" else PARENT_ROW)
        if posted_only:
            where.append(POSTED)
        if cash_flow_only:
            where.append(CASH_FLOW_ROW)
        if direction == "outflow":
            where.append(Transaction.amount < 0)
        elif direction == "inflow":
            where.append(Transaction.amount > 0)
        if start_date:
            where.append(Transaction.date >= start_date)
        if end_date:
            where.append(Transaction.date <= end_date)
        if category_ids:
            where.append(Transaction.category_id.in_(category_ids))
        if payee_ids:
            where.append(Transaction.payee_id.in_(payee_ids))
        if account_ids:
            where.append(Transaction.account_id.in_(account_ids))
        if day_of_week is not None:
            # isodow is Monday=1..Sunday=7; the API uses Monday=0..Sunday=6
            where.append(func.extract("isodow", Transaction.date) == day_of_week + 1)
        if search:
            pattern = f"%{search}%"
            where.append(or_(Payee.name.ilike(pattern), Transaction.memo.ilike(pattern)))

        rows_q = select(Transaction)
        totals_q = select(func.count(), func.coalesce(func.sum(Transaction.amount), 0)).select_from(
            Transaction
        )
        if search:
            rows_q = rows_q.outerjoin(Payee, Transaction.payee_id == Payee.id)
            totals_q = totals_q.outerjoin(Payee, Transaction.payee_id == Payee.id)
        rows_q = (
            rows_q.where(*where)
            .order_by(Transaction.date.desc(), Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        totals_q = totals_q.where(*where)

        rows = list((await self.session.execute(rows_q)).scalars().all())
        total_count, total_amount = (await self.session.execute(totals_q)).one()
        return rows, int(total_count), Decimal(total_amount)

    async def count_pending_review_for_account(self, account_id: uuid.UUID) -> dict:
        """Count transactions needing attention for a single account, with breakdown."""
        return await self._count_pending_review(
            and_(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
        )

    async def count_pending_review(self, budget_id: uuid.UUID) -> dict:
        """Count transactions needing attention: unapproved and/or uncategorized, with breakdown."""
        return await self._count_pending_review(
            and_(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
        )

    async def _count_pending_review(self, base_where) -> dict:
        needs_category = and_(
            Transaction.category_id.is_(None),
            Transaction.is_split == False,  # noqa: E712
            Transaction.transfer_id.is_(None),
        )
        unapproved = Transaction.approved == False  # noqa: E712
        not_pending = Transaction.cleared != "pending"

        result = await self.session.execute(
            select(
                func.sum(cast(case((and_(unapproved, needs_category), 1), else_=0), Integer)).label(
                    "both"
                ),
                func.sum(
                    cast(case((and_(unapproved, ~needs_category), 1), else_=0), Integer)
                ).label("unapproved_only"),
                func.sum(
                    cast(case((and_(~unapproved, needs_category), 1), else_=0), Integer)
                ).label("uncategorized_only"),
            ).where(and_(base_where, not_pending))
        )
        row = result.one()
        both = row.both or 0
        unapproved_only = row.unapproved_only or 0
        uncategorized_only = row.uncategorized_only or 0
        return {
            "unapproved_only": unapproved_only,
            "uncategorized_only": uncategorized_only,
            "both": both,
            "total": unapproved_only + uncategorized_only + both,
            "unapproved": unapproved_only + both,
            "uncategorized": uncategorized_only + both,
        }

    async def get_splits(self, parent_id: uuid.UUID) -> list[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(
                Transaction.parent_transaction_id == parent_id,
                Transaction.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def sum_by_category_by_month(
        self,
        category_id: uuid.UUID,
        end_date: date,
    ) -> dict[date, Decimal]:
        """Return {month_start: total_amount} for all months up to end_date.

        Category activity sums LEAF rows (plain transactions + split children;
        split parents carry no category) and only POSTED amounts.
        """
        yr = cast(func.extract("year", Transaction.date), Integer)
        mo = cast(func.extract("month", Transaction.date), Integer)
        result = await self.session.execute(
            select(
                yr.label("yr"),
                mo.label("mo"),
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            )
            .where(
                Transaction.category_id == category_id,
                NOT_DELETED,
                LEAF,
                POSTED,
                Transaction.date <= end_date,
            )
            .group_by(yr, mo)
        )
        return {date(row["yr"], row["mo"], 1): row["total"] for row in result.mappings()}

    async def sum_all_categories_by_month(
        self,
        category_ids: list[uuid.UUID],
        end_date: date,
    ) -> dict[uuid.UUID, dict[date, Decimal]]:
        """Batch return {category_id: {month_start: total_amount}} through end_date."""
        if not category_ids:
            return {}
        yr = cast(func.extract("year", Transaction.date), Integer)
        mo = cast(func.extract("month", Transaction.date), Integer)
        result = await self.session.execute(
            select(
                Transaction.category_id,
                yr.label("yr"),
                mo.label("mo"),
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.category_id.in_(category_ids),
                NOT_DELETED,
                LEAF,
                POSTED,
                Transaction.date <= end_date,
            )
            .group_by(Transaction.category_id, yr, mo)
        )
        out: dict[uuid.UUID, dict[date, Decimal]] = {}
        for row in result.mappings():
            month = date(row["yr"], row["mo"], 1)
            out.setdefault(row["category_id"], {})[month] = row["total"]
        return out

    _BULK_CHUNK = 1000  # ~12k params/chunk, well under asyncpg's 65535 limit

    async def bulk_create(self, transactions: list[dict]) -> int:
        """Bulk insert transactions in chunks. Returns count inserted."""
        if not transactions:
            return 0
        for i in range(0, len(transactions), self._BULK_CHUNK):
            chunk = transactions[i : i + self._BULK_CHUNK]
            await self.session.execute(insert(Transaction).values(chunk))
        await self.session.flush()
        return len(transactions)

    async def bulk_create_from_df(self, df: "pl.DataFrame") -> int:
        """Bulk insert transactions from a Polars DataFrame."""
        return await self.bulk_create(df.to_dicts())

    async def find_by_sync_id(self, account_id: uuid.UUID, sync_id: str) -> Transaction | None:
        """Find a transaction by bank sync ID (SimpleFIN, Plaid, etc.)."""
        result = await self.session.execute(
            select(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.sync_id == sync_id,
                Transaction.is_deleted == False,  # noqa: E712
            )
            .order_by(Transaction.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_stale_pending_synced(
        self,
        account_id: uuid.UUID,
        sync_source: str,
        window_start: date | None,
        active_sync_ids: set[str],
    ) -> list[Transaction]:
        """Sync-created pending rows inside the fetched window whose bank id no
        longer appears in the feed — the bank dropped the auth or re-identified
        it at posting. Never matches user-created rows (sync_source filter).
        """
        q = select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.cleared == "pending",
            Transaction.sync_source == sync_source,
            Transaction.sync_id.isnot(None),
            Transaction.is_deleted == False,  # noqa: E712
        )
        if window_start is not None:
            q = q.where(Transaction.date >= window_start)
        if active_sync_ids:
            q = q.where(Transaction.sync_id.notin_(active_sync_ids))
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def update_cleared(self, transaction_id: uuid.UUID, cleared: str) -> None:
        await self.session.execute(
            update(Transaction).where(Transaction.id == transaction_id).values(cleared=cleared)
        )
        await self.session.flush()

    async def get_oldest_cleared_date_for_account(self, account_id: uuid.UUID) -> date | None:
        """Return the date of the oldest cleared or reconciled transaction on the account."""
        result = await self.session.execute(
            select(func.min(Transaction.date)).where(
                Transaction.account_id == account_id,
                Transaction.cleared.in_(["cleared", "reconciled"]),
                Transaction.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def find_similar_transactions(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        txn_date: date,
        exclude_id: uuid.UUID | None = None,
        date_window_days: int = 3,
    ) -> list[Transaction]:
        """Find non-reconciled transactions with exact amount and within ±3 days."""
        from datetime import timedelta

        date_low = txn_date - timedelta(days=date_window_days)
        date_high = txn_date + timedelta(days=date_window_days)
        q = select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.amount == amount,
            Transaction.date.between(date_low, date_high),
            Transaction.cleared != "reconciled",
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.parent_transaction_id.is_(None),
        )
        if exclude_id is not None:
            q = q.where(Transaction.id != exclude_id)
        result = await self.session.execute(q.limit(5))
        return list(result.scalars().all())

    async def find_match_candidates(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        txn_date: date,
        date_window_days: int = 3,
        exclude_id: uuid.UUID | None = None,
    ) -> list[Transaction]:
        """Find manual transactions that could match a synced transaction."""
        from datetime import timedelta

        date_low = txn_date - timedelta(days=date_window_days)
        date_high = txn_date + timedelta(days=date_window_days)
        q = select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.amount == amount,
            Transaction.date.between(date_low, date_high),
            Transaction.import_id.is_(None),
            Transaction.sync_id.is_(None),
            Transaction.linked_transaction_id.is_(None),
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.parent_transaction_id.is_(None),
        )
        if exclude_id is not None:
            q = q.where(Transaction.id != exclude_id)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_existing_import_ids(
        self, budget_id: uuid.UUID, import_ids: list[str]
    ) -> set[str]:
        """Return the subset of import_ids that already exist in the database."""
        if not import_ids:
            return set()
        result = await self.session.execute(
            select(Transaction.import_id).where(
                Transaction.budget_id == budget_id,
                Transaction.import_id.in_(import_ids),
                Transaction.is_deleted == False,  # noqa: E712
            )
        )
        return {row[0] for row in result.all() if row[0]}

    async def find_existing_match_candidates(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        txn_date: date,
        date_window_days: int = 5,
        limit: int = 5,
    ) -> list[tuple[Transaction, str | None]]:
        """Return (Transaction, payee_name) candidates matching by exact amount and date window.

        Used to detect duplicates during sync for transactions without import_id.
        Caller is responsible for scoring and selecting the best match.
        """
        from datetime import timedelta

        date_low = txn_date - timedelta(days=date_window_days)
        date_high = txn_date + timedelta(days=date_window_days)
        result = await self.session.execute(
            select(Transaction, Payee.name)
            .outerjoin(Payee, Transaction.payee_id == Payee.id)
            .where(
                Transaction.account_id == account_id,
                Transaction.amount == amount,
                Transaction.date.between(date_low, date_high),
                Transaction.sync_id.is_(None),  # Exclude already-synced transactions
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
            .order_by(Transaction.date.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_all_with_payee_for_account(
        self,
        account_id: uuid.UUID,
    ) -> list[tuple[Transaction, str | None]]:
        """Return all non-deleted parent transactions with their payee names for an account."""
        result = await self.session.execute(
            select(Transaction, Payee.name)
            .outerjoin(Payee, Transaction.payee_id == Payee.id)
            .where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
            .order_by(Transaction.date.desc())
        )
        return [(row[0], row[1]) for row in result.all()]

    async def find_duplicate_candidate_pairs(
        self,
        account_id: uuid.UUID,
        date_window_days: int = 5,
    ) -> list[tuple[Transaction, str | None, Transaction, str | None]]:
        """Same-amount transaction pairs within a date window, paired in SQL.

        Replaces an O(n²) Python sweep: the self-join emits only pairs that
        already match on amount and date proximity; the caller scores payees.
        Returns (txn_a, payee_a_name, txn_b, payee_b_name) with a.id < b.id
        so each pair appears exactly once.
        """
        from datetime import timedelta

        from sqlalchemy.orm import aliased

        other = aliased(Transaction)
        payee_a = aliased(Payee)
        payee_b = aliased(Payee)
        window = timedelta(days=date_window_days)

        result = await self.session.execute(
            select(Transaction, payee_a.name, other, payee_b.name)
            .join(
                other,
                and_(
                    other.account_id == Transaction.account_id,
                    other.amount == Transaction.amount,
                    other.id > Transaction.id,
                    other.date.between(Transaction.date - window, Transaction.date + window),
                    other.is_deleted == False,  # noqa: E712
                    other.parent_transaction_id.is_(None),
                ),
            )
            .outerjoin(payee_a, Transaction.payee_id == payee_a.id)
            .outerjoin(payee_b, other.payee_id == payee_b.id)
            .where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
        )
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def get_most_common_category_for_payee(
        self,
        budget_id: uuid.UUID,
        payee_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """Find the most frequently used category for a payee across existing transactions."""
        result = await self.session.execute(
            select(Transaction.category_id, func.count(Transaction.id).label("cnt"))
            .where(
                Transaction.budget_id == budget_id,
                Transaction.payee_id == payee_id,
                Transaction.category_id.isnot(None),
                Transaction.is_deleted == False,  # noqa: E712
            )
            .group_by(Transaction.category_id)
            .order_by(func.count(Transaction.id).desc())
            .limit(1)
        )
        row = result.first()
        return row.category_id if row else None

    async def get_for_budget(
        self,
        budget_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        category_id: uuid.UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Transaction]:
        q = select(Transaction).where(
            Transaction.budget_id == budget_id,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.parent_transaction_id.is_(None),
        )
        if start_date:
            q = q.where(Transaction.date >= start_date)
        if end_date:
            q = q.where(Transaction.date <= end_date)
        if category_id:
            q = q.where(Transaction.category_id == category_id)
        q = q.order_by(Transaction.date.desc()).limit(limit).offset(offset)
        result = await self.session.execute(q)
        return list(result.scalars().all())
