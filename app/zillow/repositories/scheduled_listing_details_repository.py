import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.zillow.models.scheduled_listing_details import ScheduledListingDetail


class ScheduledListingDetailsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_zpid(self, zpid: str) -> ScheduledListingDetail | None:
        result = await self.db.execute(
            select(ScheduledListingDetail).where(ScheduledListingDetail.zpid == zpid)
        )
        return result.scalar_one_or_none()

    async def get_by_zpids(self, zpids: list[str]) -> list[ScheduledListingDetail]:
        if not zpids:
            return []
        result = await self.db.execute(
            select(ScheduledListingDetail).where(
                ScheduledListingDetail.zpid.in_(zpids)
            )
        )
        return list(result.scalars().all())

    async def get_price_changed_since(
        self,
        *,
        since_hours: int,
        limit: int | None = None,
    ) -> list[str]:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).date()
        query = (
            select(ScheduledListingDetail.zpid)
            .where(ScheduledListingDetail.price_change_date >= cutoff_date)
            .order_by(
                ScheduledListingDetail.price_change_date.desc(),
                ScheduledListingDetail.zpid,
            )
        )
        if limit is not None:
            query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_all(
        self, page: int, page_size: int
    ) -> tuple[list[ScheduledListingDetail], int, int]:
        query = select(ScheduledListingDetail)
        total: int = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        pages = math.ceil(total / page_size) if page_size > 0 else 0
        result = await self.db.execute(
            query.order_by(ScheduledListingDetail.zpid)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        logger.debug(
            "zillow.scheduled_listing_details.get_all",
            page=page,
            page_size=page_size,
            total=total,
        )
        return items, total, pages

    async def get_by_preset_id(
        self, preset_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[ScheduledListingDetail], int, int]:
        query = select(ScheduledListingDetail).where(
            ScheduledListingDetail.preset_id == preset_id
        )
        total: int = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        pages = math.ceil(total / page_size) if page_size > 0 else 0
        result = await self.db.execute(
            query.order_by(ScheduledListingDetail.zpid)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        logger.debug(
            "zillow.scheduled_listing_details.get_by_preset_id",
            preset_id=preset_id,
            page=page,
            page_size=page_size,
            total=total,
        )
        return items, total, pages

    async def get_active(
        self, page: int, page_size: int
    ) -> tuple[list[ScheduledListingDetail], int, int]:
        query = (
            select(ScheduledListingDetail)
            .where(ScheduledListingDetail.keep_updated.is_(True))
            .where(ScheduledListingDetail.remove_listing.is_(False))
        )
        total: int = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        pages = math.ceil(total / page_size) if page_size > 0 else 0
        result = await self.db.execute(
            query.order_by(ScheduledListingDetail.zpid)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        logger.debug(
            "zillow.scheduled_listing_details.get_active",
            page=page,
            page_size=page_size,
            total=total,
        )
        return items, total, pages
