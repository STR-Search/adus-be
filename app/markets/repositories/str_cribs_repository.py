from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.markets.models.str_cribs import StrCribsFeeDetails


class StrCribsFeeDetailsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, record_id: int) -> StrCribsFeeDetails | None:
        result = await self.db.execute(
            select(StrCribsFeeDetails).where(
                StrCribsFeeDetails.id == record_id,
                StrCribsFeeDetails.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[StrCribsFeeDetails]:
        query = (
            select(StrCribsFeeDetails)
            .where(StrCribsFeeDetails.deleted_at.is_(None))
            .order_by(StrCribsFeeDetails.sqft)
        )
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        logger.debug("str_cribs.fee_details.get_all", count=len(items))
        return items

    async def get_by_area(self, area: int) -> StrCribsFeeDetails | None:
        """Resolve the fee tier for a property's raw sqft.

        ``sqft`` is the inclusive upper bound of each tier, so the first row
        whose ``sqft >= area`` is the matching tier. The open-ended top tier
        uses a max-int32 sentinel, so any area resolves to a row.
        """
        result = await self.db.execute(
            select(StrCribsFeeDetails)
            .where(
                StrCribsFeeDetails.sqft >= area,
                StrCribsFeeDetails.deleted_at.is_(None),
            )
            .order_by(StrCribsFeeDetails.sqft)
            .limit(1)
        )
        return result.scalar_one_or_none()

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
        record.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True
