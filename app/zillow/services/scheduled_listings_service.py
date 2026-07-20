import uuid

from fastapi import HTTPException

from app.zillow.models.scheduled_listings import ScheduledListing
from app.zillow.repositories.scheduled_listings_repository import (
    ScheduledListingsRepository,
)
from app.zillow.schemas.scheduled_listings import (
    ListingSummaryByMarket,
    PaginatedScheduledListings,
    ScheduledListingResult,
)


class ScheduledListingsService:
    def __init__(self, repository: ScheduledListingsRepository):
        self.repository = repository

    async def get_by_zpid(self, zpid: str) -> ScheduledListing | None:
        return await self.repository.get_by_zpid(zpid)

    async def set_remove_listing(self, zpid: str, remove: bool) -> bool:
        return await self.repository.set_remove_listing(zpid, remove)

    async def get_by_detail_url(self, detail_url: str) -> ScheduledListing | None:
        return await self.repository.get_by_detail_url(detail_url)

    async def get_by_zpids(
        self, zpids: list[str]
    ) -> dict[str, ScheduledListing]:
        listings = await self.repository.get_by_zpids(zpids)
        return {listing.zpid: listing for listing in listings}

    async def get_active_since(
        self,
        *,
        since_hours: int,
        limit: int | None = None,
    ) -> list[ScheduledListing]:
        return await self.repository.get_active_since(
            since_hours=since_hours,
            limit=limit,
        )

    async def get_active_since_by_market(
        self,
        *,
        market_id: int,
        since_hours: int,
        limit: int | None = None,
    ) -> list[ScheduledListing]:
        return await self.repository.get_active_since_by_market(
            market_id=market_id,
            since_hours=since_hours,
            limit=limit,
        )

    async def get_active_since_by_preset(
        self,
        *,
        preset_id: uuid.UUID,
        since_hours: int,
        limit: int | None = None,
    ) -> list[ScheduledListing]:
        return await self.repository.get_active_since_by_preset(
            preset_id=preset_id,
            since_hours=since_hours,
            limit=limit,
        )

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
