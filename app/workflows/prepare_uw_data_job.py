from sqlalchemy.ext.asyncio import AsyncSession

from app.external_api.services.external_api_service import ExternalApiService
from app.iron_bank.schemas.prepare_uw import MarketContext, PrepareUwDataResult
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
from app.markets.repositories.construction_repository import (
    ConstructionAmenitiesRepository,
    ConstructionRemodelingRepository,
)
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.opex_repository import OpexByBedroomsRepository, OpexBySizeRepository
from app.markets.repositories.realtor_repository import RealtorRepository
from app.markets.repositories.str_cribs_repository import StrCribsFeeDetailsRepository
from app.markets.services.construction_service import ConstructionAmenitiesService, ConstructionRemodelingService
from app.markets.services.market_service import MarketService
from app.markets.services.opex_service import OpexByBedroomsService, OpexBySizeService
from app.markets.services.str_cribs_service import StrCribsFeeDetailsService
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
        str_cribs_service,
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
        self.str_cribs_service = str_cribs_service
        self.external_api_service = external_api_service
        self.uw_data_service = uw_data_service

    @classmethod
    def from_session(cls, db: AsyncSession) -> "PrepareUwDataJob":
        market_repo = MarketRepository(db)
        return cls(
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            listing_details_service=ScheduledListingDetailsService(ScheduledListingDetailsRepository(db)),
            market_service=MarketService(
                market_repo, ConstructionAmenitiesRepository(db), RealtorRepository(db)
            ),
            opex_by_bedrooms_service=OpexByBedroomsService(OpexByBedroomsRepository(db), market_repo),
            opex_by_size_service=OpexBySizeService(OpexBySizeRepository(db), market_repo),
            construction_amenities_service=ConstructionAmenitiesService(ConstructionAmenitiesRepository(db)),
            construction_remodeling_service=ConstructionRemodelingService(ConstructionRemodelingRepository(db)),
            str_cribs_service=StrCribsFeeDetailsService(StrCribsFeeDetailsRepository(db)),
            external_api_service=ExternalApiService(),
            uw_data_service=PrepareUwDataService(),
        )

    async def build_market_context(
        self,
        *,
        market_id: int | None,
        bedrooms: int | None,
        area: int | None,
    ) -> MarketContext:
        """Fetch everything a draft underwriting derives from its market.

        Shared by both entry points: ``run`` (automated, market from the
        listing's preset) and the non-automated create-from-URL flow, which
        passes the analyst's ``market_id`` along with the bedrooms/sqft off the
        live Zillow fetch.

        A ``market_id`` of ``None`` means the analyst created the deal without a
        market. Rather than return nothing we load ``TEMPLATE_MARKET_ID`` — so
        the opex and amenity rows for this property's size exist — and hand back
        a zeroed copy for them to fill in.
        """
        is_template = market_id is None
        lookup_market_id = (
            self.uw_data_service.TEMPLATE_MARKET_ID if is_template else market_id
        )
        sqft = self.uw_data_service.normalize_sqft(area)

        market = await self.market_service.get_by_id(lookup_market_id)
        opex_by_bedrooms = await self.opex_by_bedrooms_service.get_by_market_and_bedrooms(
            bedrooms=bedrooms, market_id=lookup_market_id
        )
        opex_by_size = await self.opex_by_size_service.get_by_market_and_sqft(
            sqft=sqft, market_id=lookup_market_id
        )
        construction_amenities = await self.construction_amenities_service.get_all()
        construction_remodeling = await self.construction_remodeling_service.get_all()
        str_cribs_fee = (
            await self.str_cribs_service.get_by_area(area) if area is not None else None
        )
        fred = await self.external_api_service.get_30y_fixed_rate()

        context = self.uw_data_service.prepare_market_context(
            market=market,
            market_id=lookup_market_id,
            opex_by_bedrooms=opex_by_bedrooms,
            opex_by_size=opex_by_size,
            construction_amenities=construction_amenities,
            construction_remodeling=construction_remodeling,
            fred=fred,
            str_cribs_fee=str_cribs_fee,
        )
        if is_template:
            return self.uw_data_service.to_template_market_context(context)
        return context

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
        str_cribs_fee = (
            await self.str_cribs_service.get_by_area(listing.area)
            if listing.area is not None
            else None
        )
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
            str_cribs_fee=str_cribs_fee,
        )
