import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.logger import logger
from app.zillow.models.scheduled_listings import ScheduledListing
from app.zillow.models.scheduled_presets import ScheduledPreset


class ScheduledListingsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, zpid: str) -> ScheduledListing | None:
        result = await self.db.execute(
            select(ScheduledListing).where(ScheduledListing.zpid == zpid)
        )
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ScheduledListing]:
        result = await self.db.execute(
            select(ScheduledListing)
            .order_by(ScheduledListing.zpid)
            .offset(skip)
            .limit(limit)
        )
        items = list(result.scalars().all())
        logger.debug(
            "zillow.scheduled_listings.get_all",
            skip=skip,
            limit=limit,
            count=len(items),
        )
        return items

    async def get_by_preset_id(self, preset_id: uuid.UUID) -> list[ScheduledListing]:
        result = await self.db.execute(
            select(ScheduledListing)
            .where(ScheduledListing.preset_id == preset_id)
            .order_by(ScheduledListing.zpid)
        )
        items = list(result.scalars().all())
        logger.debug(
            "zillow.scheduled_listings.get_by_preset_id",
            preset_id=preset_id,
            count=len(items),
        )
        return items

    async def get_active(
        self, preset_id: uuid.UUID | None = None
    ) -> list[ScheduledListing]:
        """Returns listings where keep_updated=True and remove_listing=False."""
        query = (
            select(ScheduledListing)
            .where(ScheduledListing.keep_updated.is_(True))
            .where(ScheduledListing.remove_listing.is_(False))
        )
        if preset_id is not None:
            query = query.where(ScheduledListing.preset_id == preset_id)
        query = query.order_by(ScheduledListing.zpid)
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        logger.debug(
            "zillow.scheduled_listings.get_active",
            preset_id=preset_id,
            count=len(items),
        )
        return items

    async def get_active_since(
        self,
        *,
        since_hours: int,
        limit: int | None = None,
    ) -> list[ScheduledListing]:
        """Returns active listings created in the last since_hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        query = (
            select(ScheduledListing)
            .where(ScheduledListing.keep_updated.is_(True))
            .where(ScheduledListing.remove_listing.is_(False))
            .where(ScheduledListing.created_at >= cutoff)
            .order_by(ScheduledListing.created_at.desc(), ScheduledListing.zpid)
        )
        if limit is not None:
            query = query.limit(limit)

        result = await self.db.execute(query)
        items = list(result.scalars().all())
        logger.debug(
            "zillow.scheduled_listings.get_active_since",
            since_hours=since_hours,
            limit=limit,
            count=len(items),
        )
        return items

    async def get_passing_filters(self, preset_id: uuid.UUID) -> list[ScheduledListing]:
        result = await self.db.execute(
            select(ScheduledListing)
            .where(ScheduledListing.preset_id == preset_id)
            .where(ScheduledListing.passes_preset_filters.is_(True))
            .order_by(ScheduledListing.zpid)
        )
        items = list(result.scalars().all())
        logger.debug(
            "zillow.scheduled_listings.get_passing_filters",
            preset_id=preset_id,
            count=len(items),
        )
        return items

    async def get_listings_summary_by_market(self, market_id: int) -> dict:
        cities_q = (
            select(ScheduledListing.address_city)
            .join(ScheduledPreset, ScheduledPreset.id == ScheduledListing.preset_id)
            .where(ScheduledPreset.market_id == market_id)
            .distinct()
        )
        states_q = (
            select(ScheduledListing.address_state)
            .join(ScheduledPreset, ScheduledPreset.id == ScheduledListing.preset_id)
            .where(ScheduledPreset.market_id == market_id)
            .distinct()
        )
        beds_q = (
            select(ScheduledListing.beds)
            .join(ScheduledPreset, ScheduledPreset.id == ScheduledListing.preset_id)
            .where(ScheduledPreset.market_id == market_id)
            .distinct()
        )

        cities_result = await self.db.execute(cities_q)
        states_result = await self.db.execute(states_q)
        beds_result = await self.db.execute(beds_q)

        return {
            "cities": [r.address_city for r in cities_result.all()],
            "states": [r.address_state for r in states_result.all()],
            "beds": [r.beds for r in beds_result.all()],
        }

    async def get_by_zpid(self, zpid: str) -> ScheduledListing | None:
        result = await self.db.execute(
            select(ScheduledListing)
            .options(joinedload(ScheduledListing.preset))
            .where(ScheduledListing.zpid == zpid)
        )
        return result.scalar_one_or_none()

    async def get_by_detail_url(self, detail_url: str) -> ScheduledListing | None:
        result = await self.db.execute(
            select(ScheduledListing)
            .options(joinedload(ScheduledListing.preset))
            .where(ScheduledListing.detail_url == detail_url)
        )
        return result.scalar_one_or_none()

    async def get_zillow_listings_paginated(
        self,
        page: int,
        page_size: int,
        detail_url: str | None = None,
        address_city: str | None = None,
        address_state: str | None = None,
        beds: int | None = None,
    ) -> tuple[list[Row[Any]], int, int]:
        query = select(
            ScheduledListing.zpid,
            ScheduledListing.detail_url,
            ScheduledListing.address,
            ScheduledListing.address_city,
            ScheduledListing.address_state,
            ScheduledListing.beds,
        )

        if detail_url is not None:
            query = query.where(ScheduledListing.detail_url.ilike(f"%{detail_url}%"))
        if address_city is not None:
            query = query.where(ScheduledListing.address_city == address_city)
        if address_state is not None:
            query = query.where(ScheduledListing.address_state == address_state)
        if beds is not None:
            query = query.where(ScheduledListing.beds == beds)

        total: int = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        pages = math.ceil(total / page_size) if page_size > 0 else 0

        result = await self.db.execute(
            query.order_by(ScheduledListing.zpid)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.all())

        logger.debug(
            "zillow.scheduled_listings.get_zillow_listings_paginated",
            page=page,
            page_size=page_size,
            total=total,
        )
        return items, total, pages
