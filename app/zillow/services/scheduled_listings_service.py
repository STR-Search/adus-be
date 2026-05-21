from fastapi import HTTPException

from app.zillow.repositories.scheduled_listings_repository import ScheduledListingsRepository
from app.zillow.schemas.scheduled_listings import (
    ListingSummaryByMarket,
    PaginatedScheduledListings,
    ScheduledListingResult,
)


class ScheduledListingsService:
    def __init__(self, repository: ScheduledListingsRepository):
        self.repository = repository

    async def get_listings_summary_by_market(
        self, market_id: int
    ) -> ListingSummaryByMarket:
        data = await self.repository.get_listings_summary_by_market(market_id)
        return ListingSummaryByMarket.model_validate(data)

    async def get_zillow_listings_paginated(
        self,
        page: int,
        page_size: int,
        detail_url: str | None = None,
        address_city: str | None = None,
        address_state: str | None = None,
        beds: int | None = None,
    ) -> PaginatedScheduledListings:
        if all(p is None for p in [detail_url, address_city, address_state, beds]):
            raise HTTPException(
                status_code=400,
                detail="At least one filter parameter is required",
            )

        items, total, pages = await self.repository.get_zillow_listings_paginated(
            page=page,
            page_size=page_size,
            detail_url=detail_url,
            address_city=address_city,
            address_state=address_state,
            beds=beds,
        )
        return PaginatedScheduledListings(
            items=[ScheduledListingResult.model_validate(row) for row in items],
            total=total,
            pages=pages,
        )
