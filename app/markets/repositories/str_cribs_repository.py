from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.markets.models.str_cribs import StrCribsFeeDetails


class StrCribsFeeDetailsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, record_id: int) -> StrCribsFeeDetails | None:
        result = await self.db.execute(
            select(StrCribsFeeDetails).where(StrCribsFeeDetails.id == record_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[StrCribsFeeDetails]:
        query = select(StrCribsFeeDetails).order_by(StrCribsFeeDetails.sqft)
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        logger.debug("str_cribs.fee_details.get_all", count=len(items))
        return items

    async def create(self, data: dict) -> StrCribsFeeDetails:
        record = StrCribsFeeDetails(**data)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def update(self, record_id: int, data: dict) -> StrCribsFeeDetails | None:
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
