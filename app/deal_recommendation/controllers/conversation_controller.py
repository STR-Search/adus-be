from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.deal_recommendation.services.conversation_service import ConversationService


class ConversationController:
    def __init__(self, service: ConversationService, session: AsyncSession):
        self.service = service
        self.session = session

    async def create(self, *, title: str | None, user_id: int | None) -> dict:
        conversation = await self.service.create(
            title=title, user_id=user_id, model=get_config().DEAL_REC_MODEL
        )
        await self.session.commit()
        return {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        }

    async def list(self) -> dict:
        return {
            "items": [
                {
                    "id": c.id,
                    "title": c.title,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                }
                for c in await self.service.list()
            ]
        }

    async def get(self, conversation_id: UUID) -> dict | None:
        return await self.service.get(conversation_id)

    async def exists(self, conversation_id: UUID) -> bool:
        return await self.service.exists(conversation_id)

    async def trace(self, run_id: UUID) -> dict | None:
        return await self.service.trace(run_id)
