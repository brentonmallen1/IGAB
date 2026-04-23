import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Integer, and_, case, cast, func, insert, or_, select, update

from igab.db.models import Payee, Transaction
from igab.repositories.base import BaseRepository

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
            q = q.where(
                or_(Payee.name.ilike(pattern), Transaction.memo.ilike(pattern))
            )
        if cleared:
            q = q.where(Transaction.cleared == cleared)
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

    async def count_pending_review_for_account(self, account_id: uuid.UUID) -> dict:
        """Count transactions needing attention for a single account."""
        unapproved_result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.account_id == account_id,
                Transaction.approved == False,  # noqa: E712
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
        )
        uncategorized_result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.account_id == account_id,
                Transaction.category_id.is_(None),
                Transaction.transfer_id.is_(None),
                Transaction.is_split == False,  # noqa: E712
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
        )
        return {
            "unapproved": unapproved_result.scalar_one(),
            "uncategorized": uncategorized_result.scalar_one(),
        }

    async def count_pending_review(self, budget_id: uuid.UUID) -> dict:
        """Count transactions needing attention: unapproved and/or uncategorized."""
        unapproved_result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.budget_id == budget_id,
                Transaction.approved == False,  # noqa: E712
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
        )
        uncategorized_result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.budget_id == budget_id,
                Transaction.category_id.is_(None),
                Transaction.is_split == False,  # noqa: E712
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
        )
        return {
            "unapproved": unapproved_result.scalar_one(),
            "uncategorized": uncategorized_result.scalar_one(),
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
        """Return {month_start: total_amount} for all months up to end_date."""
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
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
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
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.date <= end_date,
            )
            .group_by(Transaction.category_id, yr, mo)
        )
        out: dict[uuid.UUID, dict[date, Decimal]] = {}
        for row in result.mappings():
            month = date(row["yr"], row["mo"], 1)
            out.setdefault(row["category_id"], {})[month] = row["total"]
        return out

    async def sum_by_category(
        self,
        category_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Decimal:
        q = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.category_id == category_id,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.parent_transaction_id.is_(None),
        )
        if start_date:
            q = q.where(Transaction.date >= start_date)
        if end_date:
            q = q.where(Transaction.date <= end_date)
        result = await self.session.execute(q)
        return result.scalar_one()

    async def find_by_import_id(self, account_id: uuid.UUID, import_id: str) -> Transaction | None:
        result = await self.session.execute(
            select(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.import_id == import_id,
                Transaction.is_deleted == False,  # noqa: E712
            )
            .order_by(Transaction.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

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

    async def find_pending_by_import_id(
        self, account_id: uuid.UUID, import_id: str
    ) -> Transaction | None:
        """Find a pending (not-yet-posted) transaction by import_id for clearing."""
        result = await self.session.execute(
            select(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.import_id == import_id,
                Transaction.cleared == "pending",
                Transaction.is_deleted == False,  # noqa: E712
            )
            .order_by(Transaction.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

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
    ) -> list[Transaction]:
        """Find manual transactions that could match a synced transaction."""
        from datetime import timedelta

        date_low = txn_date - timedelta(days=date_window_days)
        date_high = txn_date + timedelta(days=date_window_days)
        result = await self.session.execute(
            select(Transaction).where(
                Transaction.account_id == account_id,
                Transaction.amount == amount,
                Transaction.date.between(date_low, date_high),
                Transaction.import_id.is_(None),
                Transaction.linked_transaction_id.is_(None),
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
        )
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

    async def find_existing_match(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        txn_date: date,
        date_window_days: int = 3,
    ) -> Transaction | None:
        """Find a transaction matching by exact amount and within ±3 days.

        Used to detect duplicates during sync for transactions without import_id.
        """
        from datetime import timedelta

        date_low = txn_date - timedelta(days=date_window_days)
        date_high = txn_date + timedelta(days=date_window_days)
        result = await self.session.execute(
            select(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.amount == amount,
                Transaction.date.between(date_low, date_high),
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
            .order_by(Transaction.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

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
