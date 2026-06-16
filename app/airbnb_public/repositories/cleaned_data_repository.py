from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.airbnb_public.models.cleaned_data import CleanedData


class CleanedDataRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, cleaned_data_id: int) -> CleanedData | None:
        result = await self.db.execute(
            select(CleanedData).where(CleanedData.id == cleaned_data_id)
        )
        return result.scalar_one_or_none()
