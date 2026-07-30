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
