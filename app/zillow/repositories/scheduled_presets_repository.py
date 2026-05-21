import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.zillow.models.scheduled_presets import ScheduledPreset


class ScheduledPresetsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, preset_id: uuid.UUID) -> ScheduledPreset | None:
        result = await self.db.execute(
            select(ScheduledPreset).where(ScheduledPreset.id == preset_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ScheduledPreset]:
        result = await self.db.execute(
            select(ScheduledPreset).order_by(ScheduledPreset.name).offset(skip).limit(limit)
        )
        items = list(result.scalars().all())
        logger.debug("zillow.scheduled_presets.get_all", skip=skip, limit=limit, count=len(items))
        return items

    async def get_active(self) -> list[ScheduledPreset]:
        result = await self.db.execute(
            select(ScheduledPreset)
            .where(ScheduledPreset.is_active.is_(True))
            .order_by(ScheduledPreset.name)
        )
        items = list(result.scalars().all())
        logger.debug("zillow.scheduled_presets.get_active", count=len(items))
        return items

    async def get_by_market_id(self, market_id: int) -> list[ScheduledPreset]:
        result = await self.db.execute(
            select(ScheduledPreset)
            .where(ScheduledPreset.market_id == market_id)
            .order_by(ScheduledPreset.name)
        )
        items = list(result.scalars().all())
        logger.debug("zillow.scheduled_presets.get_by_market_id", market_id=market_id, count=len(items))
        return items

    async def get_due_for_run(self) -> list[ScheduledPreset]:
        """Returns active presets whose next_run is at or before now."""
        now = datetime.now(tz=timezone.utc)
        result = await self.db.execute(
            select(ScheduledPreset)
            .where(ScheduledPreset.is_active.is_(True))
            .where(ScheduledPreset.next_run <= now)
            .order_by(ScheduledPreset.next_run)
        )
        items = list(result.scalars().all())
        logger.debug("zillow.scheduled_presets.get_due_for_run", count=len(items))
        return items
