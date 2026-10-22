from datetime import date

from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.underwriting_analytics import DealStatusBreakdown
from app.iron_bank.services.analytics.underwriting_analytics_service import (
    UnderwritingAnalyticsService,
)
from app.zillow.schemas.listing_analytics import HomeStatusBreakdown
from app.zillow.services.listing_analytics_service import ListingAnalyticsService


class AnalyticsController:
    def __init__(
        self,
        underwriting_analytics: UnderwritingAnalyticsService,
        listing_analytics: ListingAnalyticsService,
    ):
        self.underwriting_analytics = underwriting_analytics
        self.listing_analytics = listing_analytics

    async def get_deal_status_breakdown(
        self,
        *,
        market_id: int | None = None,
        analyst_id: int | None = None,
        added_from: date | None = None,
        added_to: date | None = None,
    ) -> DealStatusBreakdown:
        self._validate_range(added_from, added_to)
        try:
            return await self.underwriting_analytics.get_deal_status_breakdown(
                market_id=market_id,
                analyst_id=analyst_id,
                added_from=added_from,
                added_to=added_to,
            )
        except Exception as e:
            logger.error("analytics.deal_status_breakdown.error", error=str(e))
            raise HTTPException(
                status_code=500, detail="Failed to fetch deal status breakdown"
            )

    async def get_home_status_breakdown(
        self,
        *,
        market_id: int | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> HomeStatusBreakdown:
        self._validate_range(created_from, created_to)
        try:
            return await self.listing_analytics.get_home_status_breakdown(
                market_id=market_id,
                created_from=created_from,
                created_to=created_to,
            )
        except Exception as e:
            logger.error("analytics.home_status_breakdown.error", error=str(e))
            raise HTTPException(
                status_code=500, detail="Failed to fetch home status breakdown"
            )

    @staticmethod
    def _validate_range(start: date | None, end: date | None) -> None:
        if start is not None and end is not None and start > end:
            raise HTTPException(
                status_code=400, detail="Range start must be on or before range end"
            )
