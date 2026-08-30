import re
import uuid
from collections.abc import Collection, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Integer,
    Select,
    and_,
    case,
    cast,
    func,
    insert,
    literal_column,
    not_,
    or_,
    select,
    update,
)
from sqlalchemy.orm import with_expression
from sqlalchemy.sql.elements import ColumnElement

from igab.db.models import (
    Category,
    CategoryGroup,
    Payee,
    Tag,
    Transaction,
    TransactionAttachment,
    category_tags,
    payee_tags,
)
from igab.domain.activity_class import ACTIVITY_CLASS, apply_class_joins
from igab.repositories.base import BaseRepository
from igab.repositories.category_filters import LINKED_TO_CARD
from igab.repositories.txn_filters import (
    BANK_UNLINKED,
    CARD_PAYMENT_FROM_CASH,
    CASH_FLOW_ROW,
    COUNTERPART_ACCOUNT_ID,
    DEBT_INTEREST_ROW,
    ESSENTIAL_TAGGED,
    LEAF,
    LOAN_PAYMENT_ROW,
    NEEDS_CATEGORY,
    NOT_DELETED,
    ON_BUDGET_ACCOUNT,
    ON_CARD_ACCOUNT,
    PAIRABLE_LEG,
    PARENT_ROW,
    PLAIN_DEPOSIT_ROW,
    POSTED,
    PROVISIONALLY_LINKED,
    UNBUDGETED_CARD_CREDIT,
    UNPAIRED_TRANSFER_LEG,
    USER_ENTERED,
    sync_created_pending,
)

if TYPE_CHECKING:
    pass


# A trailing dot is a half-typed amount, not a non-amount: "12." is what the
# user's keyboard holds for one keystroke on the way to "12.34". Rejecting it
# blanked the results mid-word, which reads as "typing a dot breaks search".
# `\d+\.?\d*` accepts 12, 12., 12.34; `\.\d+` keeps bare ".34" working.
_AMOUNT_SEARCH_RE = re.compile(r"\d+\.?\d*|\.\d+")


def _amount_from_search(search: str) -> Decimal | None:
    """A free-text search that reads as a plain number, e.g. '12.34' or '$1,200'."""
    raw = search.strip().lstrip("$").replace(",", "")
    if not _AMOUNT_SEARCH_RE.fullmatch(raw):
        return None
    try:
        return abs(Decimal(raw))
    except InvalidOperation:
        return None


def _search_predicate(search: str):
    """Free text matches payee name or memo — and the amount when it's numeric."""
    pattern = f"%{search}%"
    clauses: list[ColumnElement[bool]] = [
        Payee.name.ilike(pattern),
        Transaction.memo.ilike(pattern),
    ]
    amount = _amount_from_search(search)
    if amount is not None:
        clauses.append(func.abs(Transaction.amount) == amount)
    return or_(*clauses)


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction

    @staticmethod
    def with_computed(stmt: Select[tuple[Transaction]]) -> Select[tuple[Transaction]]:
        """Load every served computed field on a statement selecting Transaction.

        Every path that serializes a `TransactionResponse` has to go through
        here. One helper for all of them, so a new computed field cannot be
        forgotten on some listing path.

        `needs_category` is required in the schema, so a path that skips this
        raises rather than reporting an unfiled row as filed — the failure
        direction that matters when the number is a count of work the user
        still owes. `counterpart_account_id` is nullable (a plain transaction
        has none), so it cannot fail loudly the same way; the checklist suite
        in test_transfer_counterpart.py sweeps the serializing paths instead.
        """
        return stmt.options(
            with_expression(Transaction.needs_category, NEEDS_CATEGORY),
            with_expression(Transaction.counterpart_account_id, COUNTERPART_ACCOUNT_ID),
        )

    async def get(self, id: uuid.UUID) -> Transaction | None:
        # Overrides BaseRepository.get to carry needs_category. populate_existing
        # is load-bearing: after a flush the row is already in the identity map,
        # and SQLAlchemy leaves a with_expression attribute unset on an object
        # it has seen before — which would surface as None on exactly the
        # create/update responses, and only those.
        stmt = self.with_computed(
            select(Transaction).where(Transaction.id == id, NOT_DELETED)
        ).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def refresh(self, txn: Transaction) -> None:
        """Reload post-flush state, keeping `needs_category` populated.

        `Session.refresh()` takes no loader options, so it reloads the columns
        and silently drops the with_expression value — the row then serializes
        as None and the endpoint 500s. Re-selecting with the option costs the
        same single round trip and cannot lose it.

        No is_deleted filter: this refreshes an object already in hand, and a
        soft-deleted row still has to be snapshot-able for the change log.
        """
        stmt = self.with_computed(
            select(Transaction).where(Transaction.id == txn.id)
        ).execution_options(populate_existing=True)
        await self.session.execute(stmt)

    async def create(self, **kwargs: Any) -> Transaction:
        # Same round-trip count as the base implementation — it ends in a
        # refresh(), which is also a SELECT. This one just asks for the
        # expression too.
        obj = Transaction(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return await self.get_or_raise(obj.id)

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
        unpaired_transfers: bool = False,
    ) -> list[Transaction]:
        q = self.with_computed(select(Transaction)).where(
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
        # Supported here as well as budget-wide: the register sends the same
        # parsed filters either way, and a filter the account view silently
        # ignored would return every row under a heading promising otherwise.
        if unpaired_transfers:
            q = q.where(UNPAIRED_TRANSFER_LEG)
        if search:
            q = q.outerjoin(Payee, Transaction.payee_id == Payee.id)
            q = q.where(_search_predicate(search))
        if cleared:
            q = q.where(Transaction.cleared == cleared)
        if exclude_cleared:
            q = q.where(Transaction.cleared != exclude_cleared)
        # NEEDS_CATEGORY, not a local spelling of it. This filter kept the
        # pre-fix rule after every other site moved, so the account register's
        # Uncategorized filter still listed unpaired transfer legs while the
        # badge above it — counting the same thing — did not.
        if uncategorized and unapproved and is_or_mode:
            q = q.where(or_(NEEDS_CATEGORY, Transaction.approved == False))  # noqa: E712
        else:
            if uncategorized:
                q = q.where(NEEDS_CATEGORY)
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
            (NEEDS_CATEGORY, 1),
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
        activity_classes: list[str] | None = None,
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
        unpaired_transfers: bool = False,
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
        if activity_classes:
            # So a drill-down lists exactly what the chart that opened it
            # counted. Without this an $800 "Expenses" bar opened a panel
            # totalling $1,800, because the bar means SPENDING and the list
            # meant every negative row.
            where.append(ACTIVITY_CLASS.in_(list(activity_classes)))
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
        # The same rule the needs-attention badge counts. They disagreed: this
        # excluded neither transfers nor off-budget rows, so pressing the badge
        # opened a list longer than the badge promised.
        uncategorized_pred = NEEDS_CATEGORY
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
            where.append(_search_predicate(search))
        # Deliberately its own filter rather than a mode of `is_transfer`:
        # that one tests transfer_id alone, so it cannot express "has a
        # transfer payee but no partner" at all.
        if unpaired_transfers:
            where.append(UNPAIRED_TRANSFER_LEG)

        rows_q = self.with_computed(select(Transaction))
        totals_q = select(func.count(), func.coalesce(func.sum(Transaction.amount), 0)).select_from(
            Transaction
        )
        if activity_classes:
            # Only when the filter is in play: these are four LEFT JOINs, and
            # the ordinary register listing has no reason to pay for them.
            rows_q = apply_class_joins(rows_q)
            totals_q = apply_class_joins(totals_q)
        if search:
            rows_q = rows_q.outerjoin(Payee, Transaction.payee_id == Payee.id)
            totals_q = totals_q.outerjoin(Payee, Transaction.payee_id == Payee.id)
        if order == "register":
            priority_rank = case(
                (Transaction.cleared == "pending", 0),
                # Rows genuinely missing a category — off-budget accounts don't
                # use categories, and a transfer between two on-budget accounts
                # never needed one, linked or not.
                (NEEDS_CATEGORY, 1),
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

    async def count_ai_needs_review(self, budget_id: uuid.UUID) -> int:
        """How many AI-created transactions are still waiting to be reviewed.

        Counts transactions rather than jobs on purpose: a job whose
        transaction was deleted must not keep a badge lit, and the AI pipeline
        already tracks that case separately (transaction_removed).

        Exclusions mirror _count_pending_review — soft-deleted rows, split
        children, and 'pending' rows are not things the user can act on.
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared != "pending",
                Transaction.approved == False,  # noqa: E712
                Transaction.created_via.like("ai%"),
            )
        )
        return result.scalar_one() or 0

    async def _count_pending_review(self, base_where) -> dict:
        # Approval still applies everywhere; a category does not. See
        # NEEDS_CATEGORY for which rows a category is actually for.
        #
        # POSTED is applied here and NOT inside NEEDS_CATEGORY, on purpose.
        # This is a count of work the user can act on, and a pending row is not
        # actionable — the amount is provisional and the payee often arrives
        # with it. The Uncategorized *filter* deliberately keeps pending rows,
        # because a filter answers "show me rows matching this" rather than
        # "how much is waiting for me". So the badge and that filter can
        # legitimately differ by the number of pending uncategorized rows, and
        # only by that. Pinned in test_offbudget_categories.py.
        needs_category = NEEDS_CATEGORY
        unapproved = Transaction.approved == False  # noqa: E712

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
            ).where(and_(base_where, POSTED))
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
        """A parent's live lines, oldest first (new lines append). Carries the
        served fields: this is what the split endpoints serialize."""
        result = await self.session.execute(
            self.with_computed(select(Transaction))
            .where(
                Transaction.parent_transaction_id == parent_id,
                Transaction.is_deleted == False,  # noqa: E712
            )
            .order_by(Transaction.created_at, Transaction.id)
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

        ON_BUDGET_ACCOUNT keeps the category term over the same accounts as
        the balance term it is subtracted from: a categorized row on a
        tracking account moved envelopes (and, via the floor, Ready to
        Assign) while its account contributed nothing to any balance. Every
        legitimately categorized row is on-budget already — the transfer rule
        guarantees it — so this is a no-op on correct data and a repair on a
        stray row.
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
                ON_BUDGET_ACCOUNT,
                Transaction.date <= end_date,
            )
            .group_by(yr, mo)
        )
        return {date(row["yr"], row["mo"], 1): row["total"] for row in result.mappings()}

    async def count_for_account(self, account_id: uuid.UUID) -> int:
        """Live rows on the account — zero means the register is empty."""
        result = await self.session.execute(
            select(func.count()).where(
                Transaction.account_id == account_id,
                NOT_DELETED,
            )
        )
        return result.scalar_one()

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

    async def _sum_account_rows_by_month(
        self, account_id: uuid.UUID, end_date: date, *predicates
    ) -> dict[date, Decimal]:
        yr = cast(func.extract("year", Transaction.date), Integer)
        mo = cast(func.extract("month", Transaction.date), Integer)
        result = await self.session.execute(
            select(
                yr.label("yr"),
                mo.label("mo"),
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            )
            .where(Transaction.account_id == account_id, Transaction.date <= end_date, *predicates)
            .group_by(yr, mo)
        )
        return {date(row["yr"], row["mo"], 1): row["total"] for row in result.mappings()}

    async def sum_loan_payments_by_month(
        self, account_id: uuid.UUID, end_date: date
    ) -> dict[date, Decimal]:
        """{month_start: money that arrived from another account} on a debt's
        ledger — its payments. See LOAN_PAYMENT_ROW for why net movement is
        the wrong reading."""
        return await self._sum_account_rows_by_month(account_id, end_date, LOAN_PAYMENT_ROW)

    async def sum_debt_interest_by_month(
        self, account_id: uuid.UUID, end_date: date
    ) -> dict[date, Decimal]:
        """{month_start: interest and fees charged (negative)} on a debt's
        ledger — the plain outflows YNAB and a hand-kept register put there."""
        return await self._sum_account_rows_by_month(account_id, end_date, DEBT_INTEREST_ROW)

    async def sum_plain_deposits_by_month(
        self, account_id: uuid.UUID, end_date: date
    ) -> dict[date, Decimal]:
        """{month_start: positive rows with no partner account} on a debt's
        ledger — balance adjustments, or payments typed without a transfer,
        which the payment reading leaves out and the page should mention."""
        return await self._sum_account_rows_by_month(account_id, end_date, PLAIN_DEPOSIT_ROW)

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

        ON_BUDGET_ACCOUNT for the same reason as `sum_by_category_by_month`:
        the two must stay predicate-identical, and both must span the same
        accounts as the balance term.
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
                ON_BUDGET_ACCOUNT,
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

    async def sum_credit_outflows_by_category(
        self,
        category_ids: list[uuid.UUID],
        end_date: date,
    ) -> dict[uuid.UUID, dict[uuid.UUID, dict[date, Decimal]]]:
        """Net categorized card spending: {category: {card: {month: SIGNED net}}}.

        The funding-source input of domain/cards.py: how much of each
        category's month was spent on each card. NET per month and signed —
        refunds subtract, and a month that nets to a refund arrives
        NEGATIVE, never clamped: the release it carries belongs to a
        reservation made in an earlier month, and `card_funding`'s running
        walk is what decides how much of it releases. (Clamping here is how
        every cross-month refund got discarded and the set-asides ratcheted
        upward — "The Unreleased Reservation".) Same row predicates as
        `sum_all_categories_by_month`, narrowed to card accounts
        (`ON_CARD_ACCOUNT`), so the split can never claim more credit
        spending than the activity sum counted.

        `category_ids` is `CategoryRepository.spendable_ids`
        (`category_filters.SPENDABLE`). Whatever is not in that set and is not
        a payment from cash is an unbudgeted card credit, by construction —
        see `sum_unbudgeted_card_credits`.
        """
        if not category_ids:
            return {}
        yr = cast(func.extract("year", Transaction.date), Integer)
        mo = cast(func.extract("month", Transaction.date), Integer)
        result = await self.session.execute(
            select(
                Transaction.category_id,
                Transaction.account_id,
                yr.label("yr"),
                mo.label("mo"),
                func.sum(-Transaction.amount).label("outflow"),
            )
            .where(
                Transaction.category_id.in_(category_ids),
                NOT_DELETED,
                LEAF,
                POSTED,
                ON_CARD_ACCOUNT,
                Transaction.date <= end_date,
            )
            .group_by(Transaction.category_id, Transaction.account_id, yr, mo)
        )
        out: dict[uuid.UUID, dict[uuid.UUID, dict[date, Decimal]]] = {}
        for row in result.mappings():
            net = Decimal(str(row["outflow"]))
            if net == 0:
                continue
            month = date(row["yr"], row["mo"], 1)
            out.setdefault(row["category_id"], {}).setdefault(row["account_id"], {})[month] = net
        return out

    async def sum_card_payments_by_month(
        self,
        budget_id: uuid.UUID,
        end_date: date,
    ) -> dict[uuid.UUID, dict[date, Decimal]]:
        """Money that arrived on each card from the budget's cash:
        {card: {month: amount ≥ 0}} — the outflow side of the card's
        set-aside envelope.

        A payment is an inflow transfer leg on the card whose counterpart is
        a cash account. A direct deposit typed onto the card (a partner
        paying the card company themselves, a balance adjustment) reduces
        what is owed but drew on nobody's set-aside, so it is not counted —
        and a card→card balance transfer moves debt, not reserved cash, so
        the cash-counterpart test excludes it too. Both of those land in
        `sum_unbudgeted_card_credits` instead, which selects on the negation
        of the very same expression.
        """
        yr = cast(func.extract("year", Transaction.date), Integer)
        mo = cast(func.extract("month", Transaction.date), Integer)
        result = await self.session.execute(
            select(
                Transaction.account_id,
                yr.label("yr"),
                mo.label("mo"),
                func.sum(Transaction.amount).label("paid"),
            )
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                PARENT_ROW,
                POSTED,
                ON_CARD_ACCOUNT,
                CARD_PAYMENT_FROM_CASH,
                Transaction.date <= end_date,
            )
            .group_by(Transaction.account_id, yr, mo)
        )
        out: dict[uuid.UUID, dict[date, Decimal]] = {}
        for row in result.mappings():
            month = date(row["yr"], row["mo"], 1)
            out.setdefault(row["account_id"], {})[month] = Decimal(str(row["paid"]))
        return out

    async def sum_unbudgeted_card_credits(
        self,
        budget_id: uuid.UUID,
        end_date: date,
    ) -> dict[uuid.UUID, dict[date, Decimal]]:
        """Card inflows the budget has no claim on: {card: {month: amount >= 0}}.

        Neither a payment from the budget's cash (`sum_card_payments_by_month`)
        nor a category's own money coming back
        (`sum_credit_outflows_by_category`) — a partner paying the card
        themselves, a promotional credit, a bank adjustment. It reduces what is
        owed and touches no envelope, which is correct.

        It exists because the card reserve identity has to *name* it. Without
        this term the only honest form of `set_aside + uncovered == -balance`
        was one qualified into uselessness — "for a card with no assignments
        and no inflows that predate their reservations" — and those were
        precisely the histories that broke it.

        `txn_filters.UNBUDGETED_CARD_CREDIT` is the complement of the other two
        sums *written as one*: it negates `category_filters.SPENDABLE`, the
        same expression that picks the ids passed to
        `sum_credit_outflows_by_category`, and `CARD_PAYMENT_FROM_CASH`, the
        same expression `sum_card_payments_by_month` selects on. Spelled out
        independently it said `category_id IS NULL`, which excludes a row filed
        to a category that exists but cannot release — income, a card's own
        envelope — so such a row reached no term at all.
        """
        yr = cast(func.extract("year", Transaction.date), Integer)
        mo = cast(func.extract("month", Transaction.date), Integer)
        result = await self.session.execute(
            select(
                Transaction.account_id,
                yr.label("yr"),
                mo.label("mo"),
                func.sum(Transaction.amount).label("credited"),
            )
            .where(
                Transaction.budget_id == budget_id,
                UNBUDGETED_CARD_CREDIT,
                Transaction.date <= end_date,
            )
            .group_by(Transaction.account_id, yr, mo)
        )
        out: dict[uuid.UUID, dict[date, Decimal]] = {}
        for row in result.mappings():
            month = date(row["yr"], row["mo"], 1)
            out.setdefault(row["account_id"], {})[month] = Decimal(str(row["credited"]))
        return out

    _BULK_CHUNK = 1000  # ~15k params/chunk, well under asyncpg's 32767 limit

    async def bulk_create(self, transactions: Sequence[Mapping[str, Any]]) -> int:
        """Bulk insert transactions in chunks. Returns count inserted.

        Each chunk is its own INSERT statement, and Postgres validates the
        transfer_id self-FK at end of statement — rows must not reference ids
        in a LATER chunk. Callers linking rows to each other (the YNAB
        importer) insert with transfer_id NULL and link afterwards via
        bulk_link_transfers."""
        if not transactions:
            return 0
        for i in range(0, len(transactions), self._BULK_CHUNK):
            chunk = transactions[i : i + self._BULK_CHUNK]
            await self.session.execute(insert(Transaction).values(chunk))
        await self.session.flush()
        return len(transactions)

    async def list_unpaired_transfer_legs(self, budget_id: uuid.UUID) -> list[Transaction]:
        """Every leg the hygiene panel counts, oldest first.

        Same predicate as the count and the `is:unpaired` filter — the number,
        the list and the repair pass must be looking at one rule.
        """
        q = (
            self.with_computed(select(Transaction))
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                Transaction.parent_transaction_id.is_(None),
                Transaction.is_split == False,  # noqa: E712
                UNPAIRED_TRANSFER_LEG,
            )
            .order_by(Transaction.date, Transaction.created_at)
        )
        return list((await self.session.execute(q)).scalars().all())

    async def list_categorized_tracking_rows(self, budget_id: uuid.UUID) -> list[Transaction]:
        """Leaf rows on off-budget accounts that carry a category — every one
        a rule violation (domain/transfers.py: a category may sit only on an
        on-budget row). The activity sums exclude them, so they move no money;
        they are listed for the hygiene repair that strips them. Same
        predicate as the hygiene count, one rule for both."""
        q = (
            self.with_computed(select(Transaction))
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                LEAF,
                Transaction.category_id.isnot(None),
                ~ON_BUDGET_ACCOUNT,
            )
            .order_by(Transaction.date, Transaction.created_at, Transaction.id)
        )
        return list((await self.session.execute(q)).scalars().all())

    async def find_transfer_candidates(
        self,
        *,
        account_id: uuid.UUID,
        amount: Decimal,
        counterpart_account_id: uuid.UUID | None = None,
        on_date: date | None = None,
        date_tolerance_days: int = 0,
    ) -> list[Transaction]:
        """Rows in `account_id` that could be the missing side of a transfer.

        Always: live, unlinked, not part of a split, exactly `amount`.
        `counterpart_account_id` narrows to legs whose transfer payee points
        back at that account — the high-confidence shape auto-linking trusts.
        Left None, plain rows qualify too (a bank-imported far leg whose payee
        is "Online Transfer"), which is what the picker wants to offer.
        Dates: exact `on_date`, widened by `date_tolerance_days` either side.
        """
        q = self.with_computed(select(Transaction)).where(
            Transaction.account_id == account_id,
            PAIRABLE_LEG,
            Transaction.amount == amount,
        )
        if counterpart_account_id is not None:
            q = q.join(Payee, Transaction.payee_id == Payee.id).where(
                Payee.transfer_account_id == counterpart_account_id
            )
        if on_date is not None:
            if date_tolerance_days:
                q = q.where(
                    Transaction.date.between(
                        on_date - timedelta(days=date_tolerance_days),
                        on_date + timedelta(days=date_tolerance_days),
                    )
                )
            else:
                q = q.where(Transaction.date == on_date)
        q = q.order_by(Transaction.date, Transaction.created_at)
        return list((await self.session.execute(q)).scalars().all())

    async def list_pairable_legs(
        self, budget_id: uuid.UUID, *, since: date, until: date
    ) -> list[Transaction]:
        """Every unlinked, whole, live row in the budget between two dates.

        The raw material for `domain/transfers.pair_legs`, which decides which
        of them are two sides of one movement. Deliberately budget-wide and
        account-agnostic: `find_transfer_candidates` answers "given this row
        and this target account", which is the picker's question and needs a
        human to have named the account first. Nothing asked this one, which is
        why two synced legs of one payment never met.

        Bounded by date rather than by sync run: the far leg is routinely older
        than the rows that just arrived (a bank posts the two sides days
        apart), so a run-scoped query would miss exactly the pairs worth
        finding.
        """
        q = (
            select(Transaction)
            .where(
                Transaction.budget_id == budget_id,
                PAIRABLE_LEG,
                Transaction.date.between(since, until),
            )
            .order_by(Transaction.date, Transaction.created_at)
        )
        return list((await self.session.execute(q)).scalars().all())

    async def bulk_link_transfers(self, links: list[tuple[uuid.UUID, uuid.UUID]]) -> None:
        """Set transfer_id on already-inserted rows: (row_id, partner_id) pairs.

        Exists because a linked pair straddling a bulk_create chunk boundary
        used to violate the self-FK — the first chunk's statement referenced a
        partner row the next chunk hadn't inserted yet."""
        if not links:
            return
        for i in range(0, len(links), self._BULK_CHUNK):
            chunk = links[i : i + self._BULK_CHUNK]
            await self.session.execute(
                update(Transaction),
                [{"id": row_id, "transfer_id": partner_id} for row_id, partner_id in chunk],
            )
        await self.session.flush()

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
            sync_created_pending(sync_source),
            Transaction.is_deleted == False,  # noqa: E712
        )
        if window_start is not None:
            q = q.where(Transaction.date >= window_start)
        if active_sync_ids:
            q = q.where(Transaction.sync_id.notin_(active_sync_ids))
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def find_stale_provisional_links(
        self,
        account_id: uuid.UUID,
        sync_source: str,
        window_start: date | None,
        active_sync_ids: set[str],
    ) -> list[Transaction]:
        """User rows linked to a bank record the feed no longer reports.

        An `uncleared` row matched while the bank record was still an auth
        hold, whose id then vanished: the bank dropped the hold or
        re-identified it at posting. Such a row can never clear through its
        link again. `uncleared` only — a row the user marked cleared is done
        as far as they are concerned, and pre-`bank_posted_date` legacy rows
        are `cleared`, so this can never unlink one of them.
        """
        q = select(Transaction).where(
            Transaction.account_id == account_id,
            PROVISIONALLY_LINKED,
            Transaction.cleared == "uncleared",
            Transaction.sync_source == sync_source,
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

    # ─── Essentials: one query, three readers ──────────────────────────────

    async def _essential_scope(
        self, budget_id: uuid.UUID, bound_categories: Sequence[uuid.UUID] | None
    ) -> tuple[list, str]:
        """How "essential" is decided for this budget, and by which rule.

        Precedence: categories the user bound in the Guide ("bound"); else
        the Essential tag on categories or payees, when any is applied
        ("tag"); else all spending ("all") — the Guide's original fallback,
        which the report and the Overview card treat as "nothing tagged yet"
        rather than show a figure that equals burn rate.
        """
        if bound_categories:
            return [Transaction.category_id.in_(list(bound_categories))], "bound"
        tagged = select(Tag.id).where(
            Tag.budget_id == budget_id,
            Tag.system_key == "essential",
            Tag.is_deleted == False,  # noqa: E712
        )
        applied = (
            select(func.count())
            .select_from(category_tags)
            .where(category_tags.c.tag_id.in_(tagged))
            .scalar_subquery()
            + select(func.count())
            .select_from(payee_tags)
            .where(payee_tags.c.tag_id.in_(tagged))
            .scalar_subquery()
        )
        if (await self.session.execute(select(applied))).scalar_one() > 0:
            return [ESSENTIAL_TAGGED], "tag"
        return [], "all"

    @staticmethod
    def _essential_where(budget_id: uuid.UUID, since: date, until: date, scope: list) -> list:
        from igab.domain.activity_class import ActivityClass

        return [
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            LEAF,
            ON_BUDGET_ACCOUNT,
            Transaction.date >= since,
            Transaction.date <= until,
            ACTIVITY_CLASS == ActivityClass.SPENDING,
            *scope,
        ]

    async def essential_spend(
        self,
        budget_id: uuid.UUID,
        since: date,
        until: date,
        bound_categories: Sequence[uuid.UUID] | None = None,
    ) -> tuple[Decimal, str]:
        """Signed sum of essential spending in the window (outflows are
        negative), and the rule that scoped it — see `_essential_scope`."""
        scope, basis = await self._essential_scope(budget_id, bound_categories)
        total = (
            await self.session.execute(
                apply_class_joins(
                    select(func.coalesce(func.sum(Transaction.amount), 0))
                    .select_from(Transaction)
                    .where(*self._essential_where(budget_id, since, until, scope))
                )
            )
        ).scalar_one()
        return Decimal(total), basis

    async def essential_spend_by_category_month(
        self,
        budget_id: uuid.UUID,
        since: date,
        until: date,
        bound_categories: Sequence[uuid.UUID] | None = None,
    ) -> tuple[list, str]:
        """(category_id, category_name, group_name, month, total) rows over the
        same predicate as `essential_spend`, grouped by calendar month. A
        payee-tagged row without a category groups under None."""
        scope, basis = await self._essential_scope(budget_id, bound_categories)
        month = func.date_trunc(literal_column("'month'"), Transaction.date).label("month")
        q = (
            select(
                Transaction.category_id,
                Category.name.label("category_name"),
                CategoryGroup.name.label("group_name"),
                month,
                func.sum(Transaction.amount).label("total"),
            )
            .select_from(Transaction)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .outerjoin(CategoryGroup, CategoryGroup.id == Category.category_group_id)
            .where(*self._essential_where(budget_id, since, until, scope))
            .group_by(Transaction.category_id, Category.name, CategoryGroup.name, month)
        )
        rows = (await self.session.execute(apply_class_joins(q))).all()
        return list(rows), basis

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
            USER_ENTERED,
            Transaction.is_deleted == False,  # noqa: E712
            Transaction.parent_transaction_id.is_(None),
        )
        if exclude_id is not None:
            q = q.where(Transaction.id != exclude_id)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    # One bind parameter per id — stay far from asyncpg's 32767 ceiling, which
    # a decade-long multi-account YNAB export can genuinely reach.
    _IMPORT_ID_CHUNK = 10_000

    async def get_existing_import_ids(
        self, budget_id: uuid.UUID, import_ids: list[str]
    ) -> set[str]:
        """Return the subset of import_ids that already exist in the database."""
        found: set[str] = set()
        for i in range(0, len(import_ids), self._IMPORT_ID_CHUNK):
            chunk = import_ids[i : i + self._IMPORT_ID_CHUNK]
            result = await self.session.execute(
                select(Transaction.import_id).where(
                    Transaction.budget_id == budget_id,
                    Transaction.import_id.in_(chunk),
                    Transaction.is_deleted == False,  # noqa: E712
                )
            )
            found.update(row[0] for row in result.all() if row[0])
        return found

    async def find_existing_match_candidates(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        txn_date: date,
        date_window_days: int = 5,
        limit: int = 5,
        exclude_ids: Collection[uuid.UUID] | None = None,
        include_provisional: bool = False,
    ) -> list[tuple[Transaction, str | None]]:
        """Return (Transaction, payee_name) candidates matching by exact amount and date window.

        Used to detect duplicates during sync for transactions without import_id.
        Caller is responsible for scoring and selecting the best match.
        exclude_ids: rows already claimed earlier in the same sync run — filtered
        before LIMIT so consumption can't starve the candidate pool.
        include_provisional: also offer PROVISIONALLY_LINKED rows (see
        txn_filters) — for a posted feed record, whose bank may have
        re-identified it since the pending record those rows were linked to.
        """
        from datetime import timedelta

        date_low = txn_date - timedelta(days=date_window_days)
        date_high = txn_date + timedelta(days=date_window_days)
        linked = or_(BANK_UNLINKED, PROVISIONALLY_LINKED) if include_provisional else BANK_UNLINKED
        query = (
            select(Transaction, Payee.name)
            .outerjoin(Payee, Transaction.payee_id == Payee.id)
            .where(
                Transaction.account_id == account_id,
                Transaction.amount == amount,
                Transaction.date.between(date_low, date_high),
                linked,
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
        """Find the category from the most recent transaction for this payee.

        Joined to `categories` rather than reading `category_id` alone: a
        deleted category still sits on the rows it was deleted from until the
        hygiene repair runs, and handing it back here re-filed every new
        transaction for that payee into an envelope the budget no longer
        shows — the orphan population growing on its own.

        A card's set-aside envelope is excluded for the same reason and a
        sharper one: `TransactionService.create` validates the category the
        *caller* supplied, then resolves this one afterwards. Nothing may be
        filed to a card envelope, so inheriting one here would walk straight
        past that guard — and one historical bad row would then re-file every
        future transaction for that payee into money the budget cannot show.
        """
        result = await self.session.execute(
            select(Transaction.category_id)
            .join(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.payee_id == payee_id,
                Transaction.category_id.isnot(None),
                Transaction.is_deleted == False,  # noqa: E712
                Category.is_deleted == False,  # noqa: E712
                not_(LINKED_TO_CARD),
            )
            .order_by(Transaction.date.desc(), Transaction.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_most_recent_payee_for_category(
        self,
        budget_id: uuid.UUID,
        category_id: uuid.UUID,
    ) -> tuple[uuid.UUID, str] | None:
        """Find the payee from the most recent transaction in this category.

        Transfer payees are excluded — prefill should suggest a merchant,
        not the other side of an account transfer.
        """
        result = await self.session.execute(
            select(Transaction.payee_id, Payee.name)
            .join(Payee, Payee.id == Transaction.payee_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.category_id == category_id,
                Transaction.is_deleted == False,  # noqa: E712
                Payee.transfer_account_id.is_(None),
            )
            .order_by(Transaction.date.desc(), Transaction.created_at.desc())
            .limit(1)
        )
        row = result.first()
        return (row[0], row[1]) if row else None

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
