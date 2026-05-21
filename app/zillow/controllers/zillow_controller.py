from fastapi import HTTPException

from app.core.logger import logger
from app.zillow.schemas.scheduled_listings import ListingSummaryByMarket, PaginatedScheduledListings
from app.zillow.services.scheduled_listings_service import ScheduledListingsService


class ZillowController:
    def __init__(self, service: ScheduledListingsService):
        self.service = service

    async def get_listings_summary_by_market(
        self, market_id: int
    ) -> ListingSummaryByMarket:
        try:
            return await self.service.get_listings_summary_by_market(market_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("zillow.listings_summary.error", market_id=market_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch listings summary")

    async def get_zillow_listings_paginated(
        self,
        page: int,
        page_size: int,
        detail_url: str | None = None,
        address_city: str | None = None,
        address_state: str | None = None,
        beds: int | None = None,
    ) -> PaginatedScheduledListings:
        try:
            return await self.service.get_zillow_listings_paginated(
                page=page,
                page_size=page_size,
                detail_url=detail_url,
                address_city=address_city,
                address_state=address_state,
                beds=beds,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("zillow.listings_paginated.error", page=page, page_size=page_size, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch listings")
