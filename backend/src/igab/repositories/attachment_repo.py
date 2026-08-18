import uuid

from sqlalchemy import delete, select, update

from igab.db.models import Budget, Transaction, TransactionAttachment
from igab.repositories.base import BaseRepository


class AttachmentRepository(BaseRepository[TransactionAttachment]):
    model = TransactionAttachment

    async def get_by_id(self, attachment_id: uuid.UUID) -> TransactionAttachment | None:
        result = await self.session.execute(
            select(TransactionAttachment).where(TransactionAttachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def get_for_transaction(self, transaction_id: uuid.UUID) -> list[TransactionAttachment]:
        result = await self.session.execute(
            select(TransactionAttachment)
            .where(TransactionAttachment.transaction_id == transaction_id)
            .order_by(TransactionAttachment.created_at)
        )
        return list(result.scalars().all())

    async def find_duplicate_in_budget(
        self, budget_id: uuid.UUID, content_hash: str
    ) -> TransactionAttachment | None:
        """An attachment in this budget holding byte-identical source content.

        Scoped through the owning transaction, and skips soft-deleted ones so a
        receipt the user already threw away can be submitted again.
        """
        result = await self.session.execute(
            select(TransactionAttachment)
            .join(Transaction, TransactionAttachment.transaction_id == Transaction.id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                TransactionAttachment.content_hash == content_hash,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_media(
        self, attachment_id: uuid.UUID, *, width: int, height: int, file_size: int
    ) -> None:
        """Refresh the stored media metadata after an in-place re-encode."""
        await self.session.execute(
            update(TransactionAttachment)
            .where(TransactionAttachment.id == attachment_id)
            .values(width=width, height=height, file_size=file_size)
        )
        await self.session.flush()

    async def delete_attachment(self, attachment_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(TransactionAttachment).where(TransactionAttachment.id == attachment_id)
        )
        await self.session.flush()

    async def reassign(self, from_transaction_id: uuid.UUID, to_transaction_id: uuid.UUID) -> None:
        """Move all attachments from one transaction to another (merge flow)."""
        await self.session.execute(
            update(TransactionAttachment)
            .where(TransactionAttachment.transaction_id == from_transaction_id)
            .values(transaction_id=to_transaction_id)
        )
        await self.session.flush()

    async def has_attachments(
        self, transaction_ids: list[uuid.UUID], user_id: uuid.UUID
    ) -> set[uuid.UUID]:
        """Return the subset of `transaction_ids` that have attachments.

        Scoped to `user_id`: transactions belonging to another user's budget are
        excluded, so this cannot be used to probe attachment existence for
        arbitrary transaction ids.
        """
        if not transaction_ids:
            return set()
        result = await self.session.execute(
            select(TransactionAttachment.transaction_id)
            .join(Transaction, TransactionAttachment.transaction_id == Transaction.id)
            .join(Budget, Transaction.budget_id == Budget.id)
            .where(
                TransactionAttachment.transaction_id.in_(transaction_ids),
                Budget.user_id == user_id,
            )
            .distinct()
        )
        return set(result.scalars().all())
