import uuid
from datetime import date, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics.schemas import Granularity
from app.core.query_filters import date_range_conditions
from app.zillow.models.scheduled_listings import ScheduledListing
from app.zillow.models.scheduled_presets import ScheduledPreset


class ListingAnalyticsRepository:
    """Read-only aggregates over ``zillow.scheduled_listings`` and its presets."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def count_by_home_status(
        self,
        *,
        market_id: int | None = None,
        preset_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> list[tuple[str | None, int]]:
        query = (
            select(ScheduledListing.home_status, func.count())
            .where(*_listing_conditions(market_id, preset_id, created_from, created_to))
            .group_by(ScheduledListing.home_status)
        )
        result = await self.db.execute(query)
        return [(status, count) for status, count in result.all()]

    async def intake(
        self,
        *,
        granularity: Granularity,
        group_by_preset: bool,
        market_id: int | None = None,
        preset_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> list[tuple[uuid.UUID | None, str | None, date, int]]:
        """``(preset_id, preset name, period start, new listings)`` rows.

        ``created_at`` is the listing's first-seen time. Without
        ``group_by_preset`` the preset columns are ``None``.
        """
        period = cast(
            func.date_trunc(
                granularity.value, func.timezone("UTC", ScheduledListing.created_at)
            ),
            Date,
        ).label("period_start")
        conditions = [
            *_listing_conditions(market_id, preset_id, created_from, created_to),
            ScheduledListing.created_at.is_not(None),
        ]
        if group_by_preset:
            query = (
                select(
                    ScheduledListing.preset_id,
                    ScheduledPreset.name,
                    period,
                    func.count(),
                )
                .join(ScheduledPreset, ScheduledPreset.id == ScheduledListing.preset_id)
                .where(*conditions)
                .group_by(ScheduledListing.preset_id, ScheduledPreset.name, period)
            )
            result = await self.db.execute(query)
            return [tuple(row) for row in result.all()]

        query = select(period, func.count()).where(*conditions).group_by(period)
        result = await self.db.execute(query)
        return [(None, None, start, count) for start, count in result.all()]

    async def preset_runs(self) -> list[tuple]:
        """Active presets: ``(id, name, last_run, next_run, last_full_run, overdue)``."""
        query = select(
            ScheduledPreset.id,
            ScheduledPreset.name,
            ScheduledPreset.last_run,
            ScheduledPreset.next_run,
            ScheduledPreset.last_full_run,
            func.coalesce(ScheduledPreset.next_run < func.now(), False),
        ).where(ScheduledPreset.is_active.is_(True))
        result = await self.db.execute(query)
        return [tuple(row) for row in result.all()]

    async def count_stale_by_preset(
        self, *, stale_after_days: int, preset_id: uuid.UUID | None = None
    ) -> list[tuple[uuid.UUID, str, int]]:
        """Listings still tracked (``keep_updated``) but not seen recently."""
        cutoff = func.now() - timedelta(days=stale_after_days)
        query = (
            select(ScheduledListing.preset_id, ScheduledPreset.name, func.count())
            .join(ScheduledPreset, ScheduledPreset.id == ScheduledListing.preset_id)
            .where(
                ScheduledListing.keep_updated.is_(True),
                ScheduledListing.last_seen < cutoff,
            )
            .group_by(ScheduledListing.preset_id, ScheduledPreset.name)
        )
        if preset_id is not None:
            query = query.where(ScheduledListing.preset_id == preset_id)
        result = await self.db.execute(query)
        return [tuple(row) for row in result.all()]


def _listing_conditions(
    market_id: int | None,
    preset_id: uuid.UUID | None,
    created_from: date | None,
    created_to: date | None,
) -> list:
    conditions = date_range_conditions(
        ScheduledListing.created_at, created_from, created_to
    )
    if market_id is not None:
        # A listing's market is its preset's market. A subquery rather than a
        # join, so it composes with the preset join ``group_by_preset`` adds.
        conditions.append(
            ScheduledListing.preset_id.in_(
                select(ScheduledPreset.id).where(ScheduledPreset.market_id == market_id)
            )
        )
    if preset_id is not None:
        conditions.append(ScheduledListing.preset_id == preset_id)
    return conditions
