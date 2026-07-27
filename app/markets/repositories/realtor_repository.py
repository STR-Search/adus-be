from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.markets.models.realtor import Realtor


class RealtorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, record_id: int) -> Realtor | None:
        result = await self.db.execute(
            select(Realtor).where(
                Realtor.id == record_id,
                Realtor.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_ids(self, record_ids: set[int]) -> list[Realtor]:
        if not record_ids:
            return []
        result = await self.db.execute(
            select(Realtor).where(
                Realtor.id.in_(record_ids),
                Realtor.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_all(self, search: str | None = None) -> list[Realtor]:
        query = select(Realtor).where(Realtor.deleted_at.is_(None))
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    Realtor.name.ilike(pattern),
                    Realtor.email.ilike(pattern),
                    Realtor.brokerage.ilike(pattern),
                )
            )
        query = query.order_by(Realtor.id)
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        logger.debug("realtors.get_all", search=search, count=len(items))
        return items

    async def create(self, data: dict) -> Realtor:
        record = Realtor(**data)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def update(self, record_id: int, data: dict) -> Realtor | None:
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
