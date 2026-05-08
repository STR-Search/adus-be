from app.markets.schemas.construction import ConstructionCostsAmenitiesSchema, ConstructionCostsRemodelingSchema
from app.markets.schemas.opex import OpexByBedroomsSchema, OpexBySizeSchema
from app.markets.services.construction_service import ConstructionAmenitiesService, ConstructionRemodelingService
from app.markets.services.opex_service import OpexByBedroomsService, OpexBySizeService


class AutomatedDealUnderwritingService:
    def __init__(
        self,
        opex_by_bedrooms_service: OpexByBedroomsService,
        opex_by_size_service: OpexBySizeService,
        construction_amenities_service: ConstructionAmenitiesService,
        construction_remodeling_service: ConstructionRemodelingService,
    ):
        self.opex_by_bedrooms_service = opex_by_bedrooms_service
        self.opex_by_size_service = opex_by_size_service
        self.construction_amenities_service = construction_amenities_service
        self.construction_remodeling_service = construction_remodeling_service

    async def get_underwriting_data(
        self,
        bedrooms: int,
        sqft: int,
        market_id: int | None = None,
        market_slug: str | None = None,
    ) -> dict:
        if market_id is not None and market_slug is not None:
            raise ValueError("Provide either market_id or market_slug, not both")

        opex_by_bedrooms = await self.opex_by_bedrooms_service.get_by_market_and_bedrooms(
            bedrooms=bedrooms,
            market_id=market_id,
            market_slug=market_slug,
        )
        opex_by_size = await self.opex_by_size_service.get_by_market_and_sqft(
            sqft=sqft,
            market_id=market_id,
            market_slug=market_slug,
        )
        amenities = await self.construction_amenities_service.get_all()
        remodeling = await self.construction_remodeling_service.get_all()

        return {
            "opex_by_bedrooms": opex_by_bedrooms,
            "opex_by_size": opex_by_size,
            "construction_amenities": amenities,
            "construction_remodeling": remodeling,
        }
