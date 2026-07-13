from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.markets.models.construction import ConstructionCostsAmenities, ConstructionCostsRemodeling


class ConstructionAmenitiesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, record_id: int) -> ConstructionCostsAmenities | None:
        result = await self.db.execute(
            select(ConstructionCostsAmenities).where(
                ConstructionCostsAmenities.id == record_id,
                ConstructionCostsAmenities.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        location: str | None = None,
        search: str | None = None,
    ) -> list[ConstructionCostsAmenities]:
        query = select(ConstructionCostsAmenities).where(
            ConstructionCostsAmenities.deleted_at.is_(None)
        )
        if location is not None:
            query = query.where(ConstructionCostsAmenities.location == location)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                ConstructionCostsAmenities.amenity_name.ilike(pattern)
                | ConstructionCostsAmenities.notes.ilike(pattern)
            )
        query = query.order_by(ConstructionCostsAmenities.id)
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        logger.debug("construction.amenities.get_all", location=location, search=search, count=len(items))
        return items

    async def create(self, data: dict) -> ConstructionCostsAmenities:
        record = ConstructionCostsAmenities(**data)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def update(self, record_id: int, data: dict) -> ConstructionCostsAmenities | None:
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
        record.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True


class ConstructionRemodelingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, record_id: int) -> ConstructionCostsRemodeling | None:
        result = await self.db.execute(
            select(ConstructionCostsRemodeling).where(
                ConstructionCostsRemodeling.id == record_id,
                ConstructionCostsRemodeling.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        location: str | None = None,
        search: str | None = None,
    ) -> list[ConstructionCostsRemodeling]:
        query = select(ConstructionCostsRemodeling).where(
            ConstructionCostsRemodeling.deleted_at.is_(None)
        )
        if location is not None:
            query = query.where(ConstructionCostsRemodeling.location == location)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                ConstructionCostsRemodeling.rehab_item.ilike(pattern)
                | ConstructionCostsRemodeling.metric.ilike(pattern)
                | ConstructionCostsRemodeling.notes.ilike(pattern)
            )
        query = query.order_by(ConstructionCostsRemodeling.id)
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        logger.debug("construction.remodeling.get_all", location=location, search=search, count=len(items))
        return items

    async def create(self, data: dict) -> ConstructionCostsRemodeling:
        record = ConstructionCostsRemodeling(**data)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def update(self, record_id: int, data: dict) -> ConstructionCostsRemodeling | None:
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
        record.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True
