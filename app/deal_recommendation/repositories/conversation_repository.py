from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.deal_recommendation.models import Conversation, Message


class ConversationRepository:
    """Conversations and their append-only Claude message history.

    Callers own the transaction (commit); nothing here commits.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, *, title: str | None, created_by_user_id: int | None, model: str
    ) -> Conversation:
        conversation = Conversation(
            title=title, created_by_user_id=created_by_user_id, model=model
        )
        self.db.add(conversation)
        await self.db.flush()
        await self.db.refresh(conversation)
        return conversation

    async def get(self, conversation_id: UUID) -> Conversation | None:
        return await self.db.get(Conversation, conversation_id)

    async def list_recent(self, limit: int = 50) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def set_title(self, conversation_id: UUID, title: str) -> None:
        await self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=title)
        )

    async def append_messages(
        self,
        conversation_id: UUID,
        items: Sequence[tuple[str, list[dict] | str]],
    ) -> list[Message]:
        """Append (role, content) pairs in order, continuing the seq numbering."""
        current = await self.db.scalar(
            select(func.coalesce(func.max(Message.seq), 0)).where(
                Message.conversation_id == conversation_id
            )
        )
        messages = [
            Message(conversation_id=conversation_id, seq=current + i, role=role, content=content)
            for i, (role, content) in enumerate(items, start=1)
        ]
        self.db.add_all(messages)
        await self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=func.now())
        )
        await self.db.flush()
        return messages

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.seq)
        )
        return list(result.scalars().all())

    async def load_history(self, conversation_id: UUID) -> list[dict]:
        return [
            {"role": m.role, "content": m.content}
            for m in await self.list_messages(conversation_id)
        ]
