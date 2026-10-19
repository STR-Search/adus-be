from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deal_recommendation.models import ClientProfileVersion, Recommendation


class RecommendationRepository:
    """Client-profile versions and presented shortlists. Callers own commits."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_profile(
        self, *, conversation_id: UUID, run_id: UUID, profile: dict
    ) -> int:
        current = await self.db.scalar(
            select(func.coalesce(func.max(ClientProfileVersion.version), 0)).where(
                ClientProfileVersion.conversation_id == conversation_id
            )
        )
        version = current + 1
        self.db.add(
            ClientProfileVersion(
                conversation_id=conversation_id,
                run_id=run_id,
                version=version,
                profile=profile,
            )
        )
        await self.db.flush()
        return version

    async def latest_profile(self, conversation_id: UUID) -> dict | None:
        return await self.db.scalar(
            select(ClientProfileVersion.profile)
            .where(ClientProfileVersion.conversation_id == conversation_id)
            .order_by(ClientProfileVersion.version.desc())
            .limit(1)
        )

    async def list_profiles(self, conversation_id: UUID) -> list[ClientProfileVersion]:
        result = await self.db.execute(
            select(ClientProfileVersion)
            .where(ClientProfileVersion.conversation_id == conversation_id)
            .order_by(ClientProfileVersion.version)
        )
        return list(result.scalars().all())

    async def add_recommendations(
        self, *, run_id: UUID, conversation_id: UUID, items: Sequence[dict]
    ) -> None:
        self.db.add_all(
            Recommendation(run_id=run_id, conversation_id=conversation_id, **item)
            for item in items
        )
        await self.db.flush()

    async def list_for_conversation(self, conversation_id: UUID) -> list[Recommendation]:
        result = await self.db.execute(
            select(Recommendation)
            .where(Recommendation.conversation_id == conversation_id)
            .order_by(Recommendation.created_at, Recommendation.rank)
        )
        return list(result.scalars().all())
