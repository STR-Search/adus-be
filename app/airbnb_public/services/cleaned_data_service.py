from typing import Protocol

from app.airbnb_public.models.cleaned_data import CleanedData
from app.airbnb_public.schemas.cleaned_data import (
    CleanedDataSchema,
    RevenuePotentialPercentiles,
)


class CleanedDataReader(Protocol):
    async def get_by_id(self, cleaned_data_id: int) -> CleanedData | None: ...

    async def get_revenue_potential_percentiles(
        self,
        *,
        key_market: str,
        bedrooms: int,
    ) -> tuple[float | None, float | None, float | None]: ...


class CleanedDataService:
    def __init__(self, repository: CleanedDataReader):
        self.repository = repository

    async def get_by_id(self, cleaned_data_id: int) -> CleanedDataSchema | None:
        item = await self.repository.get_by_id(cleaned_data_id)
        if item is None:
            return None
        return CleanedDataSchema.model_validate(item)

    async def get_revenue_potential_percentiles(
        self,
        *,
        key_market: str,
        bedrooms: int,
    ) -> RevenuePotentialPercentiles | None:
        low, mid, high = await self.repository.get_revenue_potential_percentiles(
            key_market=key_market,
            bedrooms=bedrooms,
        )
        if low is None or mid is None or high is None:
            return None
        return RevenuePotentialPercentiles(low=low, mid=mid, high=high)
