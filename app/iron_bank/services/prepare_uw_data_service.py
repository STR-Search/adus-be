from app.external_api.services.external_api_service import ExternalApiService
from app.iron_bank.defaults import UW_CONFIG_DEFAULTS
from app.markets.schemas.opex import OpexByBedroomsSchema, OpexBySizeSchema
from app.markets.services.construction_service import (
    ConstructionAmenitiesService,
    ConstructionRemodelingService,
)
from app.markets.services.market_service import MarketService
from app.markets.services.opex_service import OpexByBedroomsService, OpexBySizeService
from app.zillow.models.scheduled_listings import ScheduledListing
from app.zillow.schemas.scheduled_listing_details import ScheduledListingDetailSchema
from app.zillow.services.scheduled_listing_details_service import ScheduledListingDetailsService
from app.zillow.services.scheduled_listings_service import ScheduledListingsService


class PrepareUwDataService:
    def __init__(
        self,
        listings_service: ScheduledListingsService,
        listing_details_service: ScheduledListingDetailsService,
        market_service: MarketService,
        opex_by_bedrooms_service: OpexByBedroomsService,
        opex_by_size_service: OpexBySizeService,
        construction_amenities_service: ConstructionAmenitiesService,
        construction_remodeling_service: ConstructionRemodelingService,
        external_api_service: ExternalApiService,
    ):
        self.listings_service = listings_service
        self.listing_details_service = listing_details_service
        self.market_service = market_service
        self.opex_by_bedrooms_service = opex_by_bedrooms_service
        self.opex_by_size_service = opex_by_size_service
        self.construction_amenities_service = construction_amenities_service
        self.construction_remodeling_service = construction_remodeling_service
        self.external_api_service = external_api_service

    _SQFT_CHECKPOINTS = [1000, 1500, 2000, 2750, 3500, 4500]
    _OPEX_METADATA_FIELDS = {"id", "market_id", "market_slug", "bedrooms", "sqft"}
    _OPEX_CLEANING_FIELDS = {"cleaning_fee", "num_of_turns"}
    _OPEX_RANGED_FIELDS = {"pool_hot_tub_low", "pool_hot_tub_high", "furnishings_low", "furnishings_high"}

    def _normalize_raw_zillow_area_value(self, area: int | None) -> int | None:
        if area is None:
            return None
        for checkpoint in self._SQFT_CHECKPOINTS:
            if area <= checkpoint:
                return checkpoint
        return self._SQFT_CHECKPOINTS[-1]

    def _transform_zillow_property(
        self,
        listing: ScheduledListing,
        listing_details: ScheduledListingDetailSchema | None,
    ) -> dict:
        return {
            "id": listing.zpid,
            "url": listing.detail_url,
            "thumbnail": listing.img_src,
            "price": listing.price,
            "address": listing.address,
            "bedrooms": listing.beds,
            "bathrooms": listing.baths,
            "area": listing.area,
            "original_photos": listing_details.original_photos if listing_details else None,
            "lot_size_sqft": listing_details.lot_size_sqft if listing_details else None,
        }

    def _transform_opex_costs(
        self,
        opex_by_bedrooms: OpexByBedroomsSchema | None,
        opex_by_size: OpexBySizeSchema | None,
    ) -> dict:
        bedrooms_data = opex_by_bedrooms.model_dump() if opex_by_bedrooms is not None else {}
        size_data = opex_by_size.model_dump() if opex_by_size is not None else {}

        exclude = self._OPEX_METADATA_FIELDS | self._OPEX_CLEANING_FIELDS | self._OPEX_RANGED_FIELDS
        absolute = {k: v for k, v in {**bedrooms_data, **size_data}.items() if k not in exclude}

        return {
            "cleaning": {
                "fee": bedrooms_data.get("cleaning_fee"),
                "num_of_turns": bedrooms_data.get("num_of_turns"),
            },
            "ranged": {
                "pool_hot_tub": {
                    "low": bedrooms_data.get("pool_hot_tub_low"),
                    "high": bedrooms_data.get("pool_hot_tub_high"),
                },
                "furnishings": {
                    "low": bedrooms_data.get("furnishings_low"),
                    "high": bedrooms_data.get("furnishings_high"),
                },
            },
            "absolute": absolute,
        }

    async def get_uw_data_for_listing(self, zpid: str) -> dict:
        listing = await self.listings_service.get_by_zpid(zpid)
        if listing is None:
            raise ValueError("No listing found for the provided zpid")

        bedrooms = listing.beds
        sqft = self._normalize_raw_zillow_area_value(listing.area)
        market_id = listing.preset.market_id if listing.preset else None

        market = await self.market_service.get_by_id(market_id) if market_id is not None else None
        listing_details = await self.listing_details_service.get_by_zpid(listing.zpid)
        opex_by_bedrooms = await self.opex_by_bedrooms_service.get_by_market_and_bedrooms(bedrooms=bedrooms, market_id=market_id)
        opex_by_size = await self.opex_by_size_service.get_by_market_and_sqft(sqft=sqft, market_id=market_id)
        amenities = await self.construction_amenities_service.get_all()
        remodeling = await self.construction_remodeling_service.get_all()
        fred = await self.external_api_service.get_30y_fixed_rate()

        config = UW_CONFIG_DEFAULTS.model_dump()
        if fred is not None:
            config["fred"] = {"value": fred.value / 100, "date": fred.date}

        return {
            "market_name": market.market_name if market else None,
            "market_id": market_id,
            "market_slug": market.market_slug if market else None,
            "zillow_property": self._transform_zillow_property(listing, listing_details),
            "opex": self._transform_opex_costs(opex_by_bedrooms, opex_by_size),
            "construction_amenities": amenities,
            "construction_remodeling": remodeling,
            "config": config,
        }
