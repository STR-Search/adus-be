from sqlalchemy import func, select
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

    async def get_revenue_potential_percentiles(
        self,
        *,
        key_market: str,
        bedrooms: int,
    ) -> tuple[float | None, float | None, float | None]:
        result = await self.db.execute(
            select(
                func.percentile_cont(0.8)
                .within_group(CleanedData.revenue_potential)
                .label("low"),
                func.percentile_cont(0.87)
                .within_group(CleanedData.revenue_potential)
                .label("mid"),
                func.percentile_cont(0.94)
                .within_group(CleanedData.revenue_potential)
                .label("high"),
            )
            .where(CleanedData.key_market == key_market)
            .where(CleanedData.bedrooms == bedrooms)
            .where(CleanedData.revenue_potential.is_not(None))
        )
        row = result.one()
        return row.low, row.mid, row.high
