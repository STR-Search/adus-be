import math

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.markets.models.market import MarketKeysMaster


class MarketRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, market_id: int) -> MarketKeysMaster | None:
        result = await self.db.execute(
            select(MarketKeysMaster).where(MarketKeysMaster.id == market_id)
        )
        return result.scalar_one_or_none()

    async def get_by_market_slug(self, market_slug: str) -> MarketKeysMaster | None:
        result = await self.db.execute(
            select(MarketKeysMaster).where(MarketKeysMaster.market_slug == market_slug)
        )
        return result.scalar_one_or_none()

    async def get_slug_map(self, market_ids: set[int]) -> dict[int, str]:
        if not market_ids:
            return {}
        result = await self.db.execute(
            select(MarketKeysMaster.id, MarketKeysMaster.market_slug).where(
                MarketKeysMaster.id.in_(market_ids)
            )
        )
        return {row.id: row.market_slug for row in result}

    async def create(self, data: dict) -> MarketKeysMaster:
        market = MarketKeysMaster(**data)
        self.db.add(market)
        await self.db.commit()
        await self.db.refresh(market)
        return market

    async def update(self, market_id: int, data: dict) -> MarketKeysMaster | None:
        market = await self.get_by_id(market_id)
        if market is None:
            return None
        for key, value in data.items():
            setattr(market, key, value)
        await self.db.commit()
        await self.db.refresh(market)
        return market

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_status: str | None = None,
        analyst_owner: str | None = None,
        search: str | None = None,
    ) -> tuple[list[MarketKeysMaster], int, int]:
        query = select(MarketKeysMaster)

        if market_status is not None:
            query = query.where(MarketKeysMaster.market_status == market_status)
        if analyst_owner is not None:
            query = query.where(MarketKeysMaster.analyst_owner == analyst_owner)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    MarketKeysMaster.market_name.ilike(pattern),
                    MarketKeysMaster.market_name_current.ilike(pattern),
                    MarketKeysMaster.market_slug.ilike(pattern),
                    MarketKeysMaster.analyst_owner.ilike(pattern),
                )
            )

        total: int = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        pages = math.ceil(total / page_size) if page_size > 0 else 0

        result = await self.db.execute(
            query.order_by(MarketKeysMaster.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.scalars().all())

        logger.debug(
            "market.get_paginated",
            page=page,
            page_size=page_size,
            total=total,
        )
        return items, total, pages

    async def delete(self, market_id: int) -> bool:
        market = await self.get_by_id(market_id)
        if market is None:
            return False
        await self.db.delete(market)
        await self.db.commit()
        return True
