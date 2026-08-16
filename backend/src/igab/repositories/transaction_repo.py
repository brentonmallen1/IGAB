import uuid
from collections.abc import Collection
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Integer, and_, case, cast, func, insert, or_, select, update

from igab.db.models import Payee, Transaction, TransactionAttachment
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
        has_attachment: bool | None = None,
        direction: str | None = None,
        is_transfer: bool | None = None,
    ) -> list[Transaction]:
        q = select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.parent_transaction_id.is_(None),
        )
        if direction == "outflow":
            q = q.where(Transaction.amount < 0)
        elif direction == "inflow":
            q = q.where(Transaction.amount > 0)
        if is_transfer is not None:
            q = q.where(
                Transaction.transfer_id.is_not(None)
                if is_transfer
                else Transaction.transfer_id.is_(None)
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
        if has_attachment is not None:
            attachment_exists = (
                select(TransactionAttachment.id)
                .where(TransactionAttachment.transaction_id == Transaction.id)
                .exists()
            )
            q = q.where(attachment_exists if has_attachment else ~attachment_exists)
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
        # id as final tiebreaker: bulk imports give thousands of rows identical
        # created_at, and offset pagination over a non-unique order silently
        # skips/duplicates rows across pages.
        q = q.order_by(
            priority_rank,
            Transaction.date.desc(),
            Transaction.created_at.desc(),
            Transaction.id.desc(),
        )
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
        cleared: str | None = None,
        exclude_cleared: str | None = None,
        uncategorized: bool = False,
        unapproved: bool = False,
        is_or_mode: bool = False,
        amount_min: float | None = None,
        amount_max: float | None = None,
        has_attachment: bool | None = None,
        is_transfer: bool | None = None,
        order: str = "date",
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[Transaction], int, Decimal]:
        """Budget-wide listing for report drill-downs and the all-accounts register.

        scope="leaf" selects category-carrying rows (split children included,
        parents excluded); scope="parent" selects account-balance rows. The
        count/sum aggregate runs over the same predicate as the page query so
        callers can reconcile a paginated list against report totals.

        order="register" sorts pending → needs-category → uncleared → rest
        (same priority as the per-account register) so paginated clients load
        rows needing attention first; order="date" is plain date-desc.
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
        if is_transfer is not None:
            where.append(
                Transaction.transfer_id.is_not(None)
                if is_transfer
                else Transaction.transfer_id.is_(None)
            )
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
        if cleared:
            where.append(Transaction.cleared == cleared)
        if exclude_cleared:
            where.append(Transaction.cleared != exclude_cleared)
        uncategorized_pred = and_(
            Transaction.category_id.is_(None),
            Transaction.is_split == False,  # noqa: E712
        )
        if uncategorized and unapproved and is_or_mode:
            where.append(or_(uncategorized_pred, Transaction.approved == False))  # noqa: E712
        else:
            if uncategorized:
                where.append(uncategorized_pred)
            if unapproved:
                where.append(Transaction.approved == False)  # noqa: E712
        if amount_min is not None:
            where.append(func.abs(Transaction.amount) >= amount_min)
        if amount_max is not None:
            where.append(func.abs(Transaction.amount) <= amount_max)
        if has_attachment is not None:
            attachment_exists = (
                select(TransactionAttachment.id)
                .where(TransactionAttachment.transaction_id == Transaction.id)
                .exists()
            )
            where.append(attachment_exists if has_attachment else ~attachment_exists)
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
        if order == "register":
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
            ordering = (
                priority_rank,
                Transaction.date.desc(),
                Transaction.created_at.desc(),
                Transaction.id.desc(),
            )
        else:
            ordering = (
                Transaction.date.desc(),
                Transaction.created_at.desc(),
                Transaction.id.desc(),
            )
        rows_q = rows_q.where(*where).order_by(*ordering).limit(limit).offset(offset)
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

    async def sum_by_account_by_month(
        self,
        account_id: uuid.UUID,
        end_date: date,
    ) -> dict[date, Decimal]:
        """Return {month_start: net balance change} for all months up to end_date.

        Account-balance semantics: PARENT_ROW rows only (a split parent's
        amount equals its children's sum) and POSTED amounts. A month's total
        is exactly how much the account balance moved during that month.
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
                Transaction.account_id == account_id,
                NOT_DELETED,
                PARENT_ROW,
                POSTED,
                Transaction.date <= end_date,
            )
            .group_by(yr, mo)
        )
        return {date(row["yr"], row["mo"], 1): row["total"] for row in result.mappings()}

    async def sum_category_outflows_by_month(
        self,
        category_id: uuid.UUID,
        end_date: date,
    ) -> dict[date, Decimal]:
        """Return {month_start: outflow total (negative)} through end_date.

        Only spending rows (amount < 0): used to read a debt-linked
        category's outflows as debt payments — an unrelated refund landing
        in the category must not be mistaken for a reversed payment.
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
                CASH_FLOW_ROW,
                Transaction.amount < 0,
                Transaction.date <= end_date,
            )
            .group_by(yr, mo)
        )
        return {date(row["yr"], row["mo"], 1): row["total"] for row in result.mappings()}

    async def sum_all_categories_by_month(
        self,
        category_ids: list[uuid.UUID],
        end_date: date | None = None,
    ) -> dict[uuid.UUID, dict[date, Decimal]]:
        """Batch return {category_id: {month_start: total_amount}} through end_date.

        end_date=None returns all months, including future-dated activity —
        the snapshot rebuild needs the full timeline.
        """
        if not category_ids:
            return {}
        yr = cast(func.extract("year", Transaction.date), Integer)
        mo = cast(func.extract("month", Transaction.date), Integer)
        q = (
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
            )
            .group_by(Transaction.category_id, yr, mo)
        )
        if end_date is not None:
            q = q.where(Transaction.date <= end_date)
        result = await self.session.execute(q)
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

    async def set_children_cleared(self, parent_id: uuid.UUID, cleared: str) -> None:
        """Mirror a parent's cleared state onto its split children.

        Children must always share the parent's cleared status; any code path
        that upgrades a split parent's cleared state goes through here.
        """
        await self.session.execute(
            update(Transaction)
            .where(
                Transaction.parent_transaction_id == parent_id,
                Transaction.is_deleted == False,  # noqa: E712
            )
            .values(cleared=cleared)
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
        # Nearest-first with a unique tiebreak: an unordered LIMIT could
        # arbitrarily evict the closest row when same-amount rows crowd the
        # window (daily coffee, weekly fill-ups).
        q = q.order_by(
            func.abs(Transaction.date - txn_date),
            Transaction.date.desc(),
            Transaction.id,
        )
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
            # sync_id alone misses id-less feeds: a sync-created row without a
            # bank id is still bank-sourced, never a "manual" match candidate.
            Transaction.sync_source.is_(None),
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
        exclude_ids: Collection[uuid.UUID] | None = None,
    ) -> list[tuple[Transaction, str | None]]:
        """Return (Transaction, payee_name) candidates matching by exact amount and date window.

        Used to detect duplicates during sync for transactions without import_id.
        Caller is responsible for scoring and selecting the best match.
        exclude_ids: rows already claimed earlier in the same sync run — filtered
        before LIMIT so consumption can't starve the candidate pool.
        """
        from datetime import timedelta

        date_low = txn_date - timedelta(days=date_window_days)
        date_high = txn_date + timedelta(days=date_window_days)
        query = (
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
            # Nearest-first, so the LIMIT can't evict the true match when many
            # same-amount rows crowd the window (daily coffee, weekly fill-ups).
            .order_by(func.abs(Transaction.date - txn_date), Transaction.date.desc())
            .limit(limit)
        )
        if exclude_ids:
            query = query.where(Transaction.id.notin_(list(exclude_ids)))
        result = await self.session.execute(query)
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
                # A merge must keep the structured row (split parent or
                # transfer leg), so a pair where BOTH sides are structured can
                # never be accepted — don't offer it for review at all.
                or_(
                    and_(
                        Transaction.is_split == False,  # noqa: E712
                        Transaction.transfer_id.is_(None),
                    ),
                    and_(
                        other.is_split == False,  # noqa: E712
                        other.transfer_id.is_(None),
                    ),
                ),
            )
        )
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def get_most_recent_category_for_payee(
        self,
        budget_id: uuid.UUID,
        payee_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """Find the category from the most recent transaction for this payee."""
        result = await self.session.execute(
            select(Transaction.category_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.payee_id == payee_id,
                Transaction.category_id.isnot(None),
                Transaction.is_deleted == False,  # noqa: E712
            )
            .order_by(Transaction.date.desc(), Transaction.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

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
        q = q.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).offset(offset)
        result = await self.session.execute(q)
        return list(result.scalars().all())
