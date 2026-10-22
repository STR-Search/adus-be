from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.controllers.analytics_controller import AnalyticsController
from app.core.database import get_db
from app.iron_bank.repositories.underwriting_analytics_repository import (
    UnderwritingAnalyticsRepository,
)
from app.iron_bank.schemas.underwriting_analytics import DealStatusBreakdown
from app.iron_bank.services.analytics.underwriting_analytics_service import (
    UnderwritingAnalyticsService,
)
from app.zillow.repositories.listing_analytics_repository import (
    ListingAnalyticsRepository,
)
from app.zillow.schemas.listing_analytics import HomeStatusBreakdown
from app.zillow.services.listing_analytics_service import ListingAnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_analytics_controller(db: AsyncSession = Depends(get_db)) -> AnalyticsController:
    return AnalyticsController(
        underwriting_analytics=UnderwritingAnalyticsService(
            UnderwritingAnalyticsRepository(db)
        ),
        listing_analytics=ListingAnalyticsService(ListingAnalyticsRepository(db)),
    )


@router.get("/underwritings/deal-status-breakdown", response_model=DealStatusBreakdown)
async def get_deal_status_breakdown(
    market_id: int | None = Query(None),
    analyst_id: int | None = Query(None),
    added_from: date | None = Query(None, description="Inclusive, on deal_added (UTC)"),
    added_to: date | None = Query(None, description="Inclusive, on deal_added (UTC)"),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_deal_status_breakdown(
        market_id=market_id,
        analyst_id=analyst_id,
        added_from=added_from,
        added_to=added_to,
    )


@router.get("/listings/home-status-breakdown", response_model=HomeStatusBreakdown)
async def get_home_status_breakdown(
    market_id: int | None = Query(None),
    created_from: date | None = Query(None, description="Inclusive, on created_at (UTC)"),
    created_to: date | None = Query(None, description="Inclusive, on created_at (UTC)"),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_home_status_breakdown(
        market_id=market_id,
        created_from=created_from,
        created_to=created_to,
    )
