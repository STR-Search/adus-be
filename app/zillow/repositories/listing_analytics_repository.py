from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.zillow.models.scheduled_listings import ScheduledListing
from app.zillow.models.scheduled_presets import ScheduledPreset


class ListingAnalyticsRepository:
    """Read-only aggregate queries over ``zillow.scheduled_listings``."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def count_by_home_status(
        self,
        *,
        market_id: int | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> list[tuple[str | None, int]]:
        query = select(ScheduledListing.home_status, func.count()).group_by(
            ScheduledListing.home_status
        )
        if market_id is not None:
            query = query.join(
                ScheduledPreset, ScheduledPreset.id == ScheduledListing.preset_id
            ).where(ScheduledPreset.market_id == market_id)
        # Half-open UTC day range so ``created_to`` is fully inclusive.
        if created_from is not None:
            query = query.where(
                ScheduledListing.created_at
                >= datetime.combine(created_from, time.min, tzinfo=timezone.utc)
            )
        if created_to is not None:
            query = query.where(
                ScheduledListing.created_at
                < datetime.combine(
                    created_to + timedelta(days=1), time.min, tzinfo=timezone.utc
                )
            )

        result = await self.db.execute(query)
        return [(status, count) for status, count in result.all()]
