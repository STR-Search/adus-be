import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.markets.models.opex import OpexByBedrooms, OpexBySize


class OpexByBedroomsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, record_id: int) -> OpexByBedrooms | None:
        result = await self.db.execute(
            select(OpexByBedrooms).where(OpexByBedrooms.id == record_id)
        )
        return result.scalar_one_or_none()

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_id: int | None = None,
        bedrooms: int | None = None,
    ) -> tuple[list[OpexByBedrooms], int, int]:
        query = select(OpexByBedrooms)
        if market_id is not None:
            query = query.where(OpexByBedrooms.market_id == market_id)
        if bedrooms is not None:
            query = query.where(OpexByBedrooms.bedrooms == bedrooms)

        total: int = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        pages = math.ceil(total / page_size) if page_size > 0 else 0

        result = await self.db.execute(
            query.order_by(OpexByBedrooms.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        logger.debug(
            "opex.bedrooms.get_paginated",
            page=page,
            page_size=page_size,
            market_id=market_id,
            bedrooms=bedrooms,
            total=total,
        )
        return items, total, pages

    async def get_by_market_and_bedrooms(self, market_id: int, bedrooms: int) -> OpexByBedrooms | None:
        result = await self.db.execute(
            select(OpexByBedrooms).where(
                OpexByBedrooms.market_id == market_id,
                OpexByBedrooms.bedrooms == bedrooms,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> OpexByBedrooms:
        record = OpexByBedrooms(**data)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def update(self, record_id: int, data: dict) -> OpexByBedrooms | None:
        record = await self.get_by_id(record_id)
        if record is None:
            return None
        for key, value in data.items():
            setattr(record, key, value)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def delete(self, record_id: int) -> bool:
        record = await self.get_by_id(record_id)
        if record is None:
            return False
        await self.db.delete(record)
        await self.db.commit()
        return True


class OpexBySizeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, record_id: int) -> OpexBySize | None:
        result = await self.db.execute(
            select(OpexBySize).where(OpexBySize.id == record_id)
        )
        return result.scalar_one_or_none()

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_id: int | None = None,
        sqft: int | None = None,
    ) -> tuple[list[OpexBySize], int, int]:
        query = select(OpexBySize)
        if market_id is not None:
            query = query.where(OpexBySize.market_id == market_id)
        if sqft is not None:
            query = query.where(OpexBySize.sqft == sqft)

        total: int = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        pages = math.ceil(total / page_size) if page_size > 0 else 0

        result = await self.db.execute(
            query.order_by(OpexBySize.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        logger.debug(
            "opex.size.get_paginated",
            page=page,
            page_size=page_size,
            market_id=market_id,
            sqft=sqft,
            total=total,
        )
        return items, total, pages

    async def get_by_market_and_sqft(self, market_id: int, sqft: int) -> OpexBySize | None:
        result = await self.db.execute(
            select(OpexBySize).where(
                OpexBySize.market_id == market_id,
                OpexBySize.sqft == sqft,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> OpexBySize:
        record = OpexBySize(**data)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def update(self, record_id: int, data: dict) -> OpexBySize | None:
        record = await self.get_by_id(record_id)
        if record is None:
            return None
        for key, value in data.items():
            setattr(record, key, value)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def delete(self, record_id: int) -> bool:
        record = await self.get_by_id(record_id)
        if record is None:
            return False
        await self.db.delete(record)
        await self.db.commit()
        return True
