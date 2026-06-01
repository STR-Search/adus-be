from app.markets.services.construction_service import ConstructionAmenitiesService, ConstructionRemodelingService
from app.markets.services.opex_service import OpexByBedroomsService, OpexBySizeService
from app.zillow.repositories.scheduled_listings_repository import ScheduledListingsRepository


class PrepareUwDataService:
    def __init__(
        self,
        listings_repo: ScheduledListingsRepository,
        opex_by_bedrooms_service: OpexByBedroomsService,
        opex_by_size_service: OpexBySizeService,
        construction_amenities_service: ConstructionAmenitiesService,
        construction_remodeling_service: ConstructionRemodelingService,
    ):
        self.listings_repo = listings_repo
        self.opex_by_bedrooms_service = opex_by_bedrooms_service
        self.opex_by_size_service = opex_by_size_service
        self.construction_amenities_service = construction_amenities_service
        self.construction_remodeling_service = construction_remodeling_service

    _SQFT_CHECKPOINTS = [1000, 1500, 2000, 2750, 3500, 4500]

    def _normalize_raw_zillow_area_value(self, area: int | None) -> int | None:
        if area is None:
            return None
        for checkpoint in self._SQFT_CHECKPOINTS:
            if area <= checkpoint:
                return checkpoint
        return self._SQFT_CHECKPOINTS[-1]

    async def get_uw_data_for_listing(self, zillow_url: str) -> dict:
        listing = await self.listings_repo.get_by_detail_url(zillow_url)
        if listing is None:
            raise ValueError("No listing found for the provided Zillow URL")

        bedrooms = listing.beds
        sqft = self._normalize_raw_zillow_area_value(listing.area)
        market_id = listing.preset.market_id if listing.preset else None

        opex_by_bedrooms = await self.opex_by_bedrooms_service.get_by_market_and_bedrooms(
            bedrooms=bedrooms,
            market_id=market_id,
        )
        opex_by_size = await self.opex_by_size_service.get_by_market_and_sqft(
            sqft=sqft,
            market_id=market_id,
        )
        amenities = await self.construction_amenities_service.get_all()
        remodeling = await self.construction_remodeling_service.get_all()

        return {
            "opex_by_bedrooms": opex_by_bedrooms,
            "opex_by_size": opex_by_size,
            "construction_amenities": amenities,
            "construction_remodeling": remodeling,
        }
