from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.iron_bank.controllers.prepare_uw_data_controller import PrepareUwDataController
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
from app.markets.repositories.construction_repository import (
    ConstructionAmenitiesRepository,
    ConstructionRemodelingRepository,
)
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.opex_repository import OpexByBedroomsRepository, OpexBySizeRepository
from app.markets.services.construction_service import ConstructionAmenitiesService, ConstructionRemodelingService
from app.markets.services.market_service import MarketService
from app.markets.services.opex_service import OpexByBedroomsService, OpexBySizeService
from app.zillow.repositories.scheduled_listing_details_repository import ScheduledListingDetailsRepository
from app.zillow.repositories.scheduled_listings_repository import ScheduledListingsRepository
from app.zillow.services.scheduled_listing_details_service import ScheduledListingDetailsService
from app.zillow.services.scheduled_listings_service import ScheduledListingsService

router = APIRouter(prefix="/iron-bank", tags=["iron_bank"])


def get_prepare_uw_data_controller(db: AsyncSession = Depends(get_db)) -> PrepareUwDataController:
    market_repo = MarketRepository(db)
    service = PrepareUwDataService(
        listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
        listing_details_service=ScheduledListingDetailsService(ScheduledListingDetailsRepository(db)),
        market_service=MarketService(market_repo),
        opex_by_bedrooms_service=OpexByBedroomsService(OpexByBedroomsRepository(db), market_repo),
        opex_by_size_service=OpexBySizeService(OpexBySizeRepository(db), market_repo),
        construction_amenities_service=ConstructionAmenitiesService(ConstructionAmenitiesRepository(db)),
        construction_remodeling_service=ConstructionRemodelingService(ConstructionRemodelingRepository(db)),
    )
    return PrepareUwDataController(service)


@router.get("/prepare-uw-data", tags=["iron_bank"])
async def get_prepare_uw_data(
    zillow_url: str = Query(...),
    controller: PrepareUwDataController = Depends(get_prepare_uw_data_controller),
):
    return await controller.get_prepare_uw_data(zillow_url=zillow_url)
