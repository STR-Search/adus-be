from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.zillow.controllers.zillow_controller import ZillowController
from app.zillow.repositories.scheduled_listings_repository import (
    ScheduledListingsRepository,
)
from app.zillow.schemas.scheduled_listings import ListingSummaryByMarket, PaginatedScheduledListings
from app.zillow.services.scheduled_listings_service import ScheduledListingsService

router = APIRouter(prefix="/zillow", tags=["zillow"])


def get_zillow_controller(db: AsyncSession = Depends(get_db)) -> ZillowController:
    return ZillowController(ScheduledListingsService(ScheduledListingsRepository(db)))


@router.get(
    "/markets/{market_id}/listings-summary",
    response_model=ListingSummaryByMarket,
)
async def get_listings_summary_by_market(
    market_id: int,
    controller: ZillowController = Depends(get_zillow_controller),
):
    return await controller.get_listings_summary_by_market(market_id)


@router.get("/listings", response_model=PaginatedScheduledListings)
async def get_zillow_listings_paginated(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    detail_url: str | None = Query(None),
    address_city: str | None = Query(None),
    address_state: str | None = Query(None),
    beds: int | None = Query(None),
    controller: ZillowController = Depends(get_zillow_controller),
):
    return await controller.get_zillow_listings_paginated(
        page=page,
        page_size=page_size,
        detail_url=detail_url,
        address_city=address_city,
        address_state=address_state,
        beds=beds,
    )
