import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Integer, cast, func, insert, select

from igab.db.models import Transaction
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
    ) -> list[Transaction]:
        q = (
            select(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
            .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        )
        if start_date:
            q = q.where(Transaction.date >= start_date)
        if end_date:
            q = q.where(Transaction.date <= end_date)
        result = await self.session.execute(q.limit(limit).offset(offset))
        return list(result.scalars().all())

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
            select(Transaction).where(
                Transaction.account_id == account_id,
                Transaction.import_id == import_id,
                Transaction.is_deleted == False,  # noqa: E712
            )
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
