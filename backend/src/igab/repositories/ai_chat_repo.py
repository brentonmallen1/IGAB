"""Reading and writing chat threads and the model-call log."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from igab.db.models import AICall, AICallPayload, AIConversation, AIMessage


class AIChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_conversation(
        self, budget_id: uuid.UUID, user_id: uuid.UUID | None, title: str | None
    ) -> AIConversation:
        conversation = AIConversation(budget_id=budget_id, user_id=user_id, title=title)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_conversation(
        self, conversation_id: uuid.UUID, budget_id: uuid.UUID
    ) -> AIConversation | None:
        """Scoped by budget: a conversation id alone must not reach across."""
        result = await self.session.execute(
            select(AIConversation).where(
                AIConversation.id == conversation_id,
                AIConversation.budget_id == budget_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_with_messages(
        self, conversation_id: uuid.UUID, budget_id: uuid.UUID
    ) -> AIConversation | None:
        result = await self.session.execute(
            select(AIConversation)
            .options(selectinload(AIConversation.messages))
            .where(
                AIConversation.id == conversation_id,
                AIConversation.budget_id == budget_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_conversations(
        self, budget_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[AIConversation], int]:
        base = select(AIConversation).where(
            AIConversation.budget_id == budget_id,
            AIConversation.archived == False,  # noqa: E712
        )
        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.session.execute(
            base.order_by(AIConversation.updated_at.desc()).limit(limit).offset(offset)
        )
        return list(rows.scalars().all()), int(total or 0)

    async def message_counts(self, conversation_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not conversation_ids:
            return {}
        rows = await self.session.execute(
            select(AIMessage.conversation_id, func.count())
            .where(AIMessage.conversation_id.in_(conversation_ids))
            .group_by(AIMessage.conversation_id)
        )
        return {cid: count for cid, count in rows.all()}

    async def messages(self, conversation_id: uuid.UUID) -> list[AIMessage]:
        rows = await self.session.execute(
            select(AIMessage)
            .where(AIMessage.conversation_id == conversation_id)
            .order_by(AIMessage.seq)
        )
        return list(rows.scalars().all())

    async def add_message(self, conversation_id: uuid.UUID, **fields) -> AIMessage:
        message = AIMessage(conversation_id=conversation_id, **fields)
        self.session.add(message)
        await self.session.flush()
        return message

    async def delete_conversation(self, conversation: AIConversation) -> None:
        await self.session.delete(conversation)

    # ── the model-call log ───────────────────────────────────────────────

    async def list_calls(
        self,
        budget_id: uuid.UUID,
        *,
        feature: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AICall], int]:
        """Calls for this budget, plus the installation-level ones.

        A probe with no budget still happened on this install, and hiding it
        would make "Ollama is unreachable" invisible in the one place someone
        would look for it.
        """
        conditions = [(AICall.budget_id == budget_id) | (AICall.budget_id.is_(None))]
        if feature:
            conditions.append(AICall.feature == feature)
        base = select(AICall).where(*conditions)
        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.session.execute(
            base.order_by(AICall.created_at.desc(), AICall.round.desc()).limit(limit).offset(offset)
        )
        return list(rows.scalars().all()), int(total or 0)

    async def get_call(self, call_id: uuid.UUID, budget_id: uuid.UUID) -> AICall | None:
        result = await self.session.execute(
            select(AICall)
            .options(selectinload(AICall.payload))
            .where(
                AICall.id == call_id,
                (AICall.budget_id == budget_id) | (AICall.budget_id.is_(None)),
            )
        )
        return result.scalar_one_or_none()

    async def delete_payloads(self, budget_id: uuid.UUID) -> int:
        """Drop the heavy halves, keeping the fact that the calls happened."""
        ids = (
            select(AICall.id)
            .where((AICall.budget_id == budget_id) | (AICall.budget_id.is_(None)))
            .scalar_subquery()
        )
        rows = await self.session.execute(
            select(AICallPayload).where(AICallPayload.ai_call_id.in_(ids))
        )
        payloads = list(rows.scalars().all())
        for payload in payloads:
            await self.session.delete(payload)
        return len(payloads)
