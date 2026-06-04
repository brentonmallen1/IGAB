import uuid

from sqlalchemy import delete, select

from igab.db.models import TransactionAttachment
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

    async def has_attachments(self, transaction_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not transaction_ids:
            return set()
        result = await self.session.execute(
            select(TransactionAttachment.transaction_id)
            .where(TransactionAttachment.transaction_id.in_(transaction_ids))
            .distinct()
        )
        return set(result.scalars().all())
