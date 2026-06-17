from sqlalchemy.ext.asyncio import AsyncSession

from app.external_api.services.external_api_service import ExternalApiService
from app.iron_bank.schemas.prepare_uw import PrepareUwDataResult
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


class PrepareUwDataJob:
    """Application-level orchestrator for preparing UW data.

    The only place that knows about both the zillow and iron_bank domains.
    Entry points (the /iron-bank/prepare-uw-data route today, a CRON task
    later) call this job; domains never import each other.
    """

    def __init__(
        self,
        *,
        listings_service,
        listing_details_service,
        market_service,
        opex_by_bedrooms_service,
        opex_by_size_service,
        construction_amenities_service,
        construction_remodeling_service,
        external_api_service,
        uw_data_service,
    ):
        self.listings_service = listings_service
        self.listing_details_service = listing_details_service
        self.market_service = market_service
        self.opex_by_bedrooms_service = opex_by_bedrooms_service
        self.opex_by_size_service = opex_by_size_service
        self.construction_amenities_service = construction_amenities_service
        self.construction_remodeling_service = construction_remodeling_service
        self.external_api_service = external_api_service
        self.uw_data_service = uw_data_service

    @classmethod
    def from_session(cls, db: AsyncSession) -> "PrepareUwDataJob":
        market_repo = MarketRepository(db)
        return cls(
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            listing_details_service=ScheduledListingDetailsService(ScheduledListingDetailsRepository(db)),
            market_service=MarketService(market_repo),
            opex_by_bedrooms_service=OpexByBedroomsService(OpexByBedroomsRepository(db), market_repo),
            opex_by_size_service=OpexBySizeService(OpexBySizeRepository(db), market_repo),
            construction_amenities_service=ConstructionAmenitiesService(ConstructionAmenitiesRepository(db)),
            construction_remodeling_service=ConstructionRemodelingService(ConstructionRemodelingRepository(db)),
            external_api_service=ExternalApiService(),
            uw_data_service=PrepareUwDataService(),
        )

    async def run(self, zpid: str) -> PrepareUwDataResult:
        listing = await self.listings_service.get_by_zpid(zpid)
        if listing is None:
            raise ValueError("No listing found for the provided zpid")

        market_id = listing.preset.market_id if listing.preset else None
        sqft = self.uw_data_service.normalize_sqft(listing.area)

        market = await self.market_service.get_by_id(market_id) if market_id is not None else None
        listing_details = await self.listing_details_service.get_by_zpid(listing.zpid)
        opex_by_bedrooms = await self.opex_by_bedrooms_service.get_by_market_and_bedrooms(
            bedrooms=listing.beds, market_id=market_id
        )
        opex_by_size = await self.opex_by_size_service.get_by_market_and_sqft(sqft=sqft, market_id=market_id)
        construction_amenities = await self.construction_amenities_service.get_all()
        construction_remodeling = await self.construction_remodeling_service.get_all()
        fred = await self.external_api_service.get_30y_fixed_rate()

        return self.uw_data_service.prepare(
            listing=listing,
            listing_details=listing_details,
            market=market,
            market_id=market_id,
            opex_by_bedrooms=opex_by_bedrooms,
            opex_by_size=opex_by_size,
            construction_amenities=construction_amenities,
            construction_remodeling=construction_remodeling,
            fred=fred,
        )
