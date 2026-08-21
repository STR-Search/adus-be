from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.external_api.services.external_api_service import ExternalApiService
from app.iron_bank.enums import OpexKeyedOn
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.prepare_uw import (
    BedroomContext,
    MarketContext,
    PrepareUwDataResult,
)
from app.iron_bank.services import opex_catalog
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


class BedroomContextNotFoundError(Exception):
    """A bedroom context cannot be built for this underwriting.

    Covers every 404 condition the endpoint has -- no such underwriting, the
    deal has no market, or the market has no opex row at the requested bedroom
    count -- each with its own message. They are one contract: "there is no
    context to return, and here is why".

    Deliberately not a ValueError: pydantic's ValidationError is one, so a
    ValueError-based signal here would let a malformed opex row surface as a
    404 "no data at that bedroom count" instead of the 500 it actually is.
    """


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
        underwriting_repository,
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
        self.underwriting_repository = underwriting_repository

    @classmethod
    def from_session(
        cls,
        db: AsyncSession,
        *,
        external_api_service: ExternalApiService | None = None,
    ) -> "PrepareUwDataJob":
        """Build the job for one session.

        ``external_api_service`` memoizes its FRED lookup per instance, so a
        batch caller passes one in to share a single fetch across every listing
        and to warm it before the first transaction opens.
        """
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
            external_api_service=external_api_service or ExternalApiService(),
            uw_data_service=PrepareUwDataService(),
            underwriting_repository=UnderwritingRepository(db),
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

    async def build_bedroom_context(
        self,
        *,
        underwriting_id: int,
        bedrooms: int,
    ) -> BedroomContext:
        """The seed values that move when an analyst changes the bedroom count.

        Post-creation counterpart to ``build_market_context``: that one seeds a
        brand-new draft from Zillow's bedroom count, this one re-seeds an
        existing underwriting at a count the analyst is considering. Only the
        ``(market_id, bedrooms)``-keyed half is returned — the sqft-keyed opex
        rows, the STR Cribs fee (keyed on area) and the financing defaults do
        not move with bedrooms, so they are left out rather than returned for
        the FE to ignore.

        ``market_id`` and ``purchase_price`` are read off the underwriting
        rather than accepted from the caller, so the property-tax blob can
        never be computed against a stale price the FE happened to be holding.
        ``bedrooms`` stays a parameter: it is the *prospective* count being
        previewed, which is precisely what ``underwriting.bedrooms`` is not yet.

        The opex figures come back as ``operating_expenses`` — a *partial* list,
        carrying this underwriting's own row ids so the client merges by id
        rather than matching labels itself. The deal's existing rows are already
        eager-loaded by ``get_by_id``, so this costs no extra query.

        Raises ``BedroomContextNotFoundError`` — a 404 — when there is no such
        underwriting, when it has no market, or when the market has no opex row
        at this bedroom count (markets do not cover every count). Handing back
        an all-null context instead would let the FE place blanks over the
        analyst's existing numbers.
        """
        underwriting = await self.underwriting_repository.get_by_id(underwriting_id)
        if underwriting is None:
            raise BedroomContextNotFoundError(
                f"Underwriting {underwriting_id} not found"
            )
        if underwriting.market_id is None:
            raise BedroomContextNotFoundError(
                f"Underwriting {underwriting_id} has no market, so there are no "
                "market figures to re-seed"
            )

        market_id = underwriting.market_id
        purchase_price = self._purchase_price_of(underwriting)

        opex_by_bedrooms = await self.opex_by_bedrooms_service.get_by_market_and_bedrooms(
            bedrooms=bedrooms, market_id=market_id
        )
        if opex_by_bedrooms is None:
            raise BedroomContextNotFoundError(
                f"No opex data for market {market_id} at {bedrooms} bedrooms"
            )

        # opex_by_size is deliberately not looked up — it is keyed on sqft, so a
        # bedroom change leaves it alone. Passing None (rather than calling with
        # sqft=None, which would emit "sqft IS NULL" and match by accident)
        # keeps its rows out of the catalog entirely, and the keyed_on filter
        # below would drop them regardless.
        opex = opex_catalog.transform_opex_costs(opex_by_bedrooms, None)
        catalog = opex_catalog.build_opex_options(
            opex_by_bedrooms=opex_by_bedrooms,
            opex_by_size=None,
            purchase_price=purchase_price,
        )
        operating_expenses = opex_catalog.resolve_opex_updates(
            [row for row in catalog if row.keyed_on is OpexKeyedOn.BEDROOMS],
            underwriting.operating_expenses,
        )

        # str_cribs_fee=None leaves the "Design / Project Management" option
        # unpriced; it is filtered out below along with the (empty) catalog.
        options = self.uw_data_service.build_amenities_options(
            opex_by_bedrooms, [], None
        )
        bedroom_keyed_ids = {
            PrepareUwDataService.FURNISHINGS_OPTION_ID,
            PrepareUwDataService.CONSOLIDATED_SHIPPING_OPTION_ID,
        }

        return BedroomContext.model_validate(
            {
                "bedrooms": bedrooms,
                "operating_expenses": operating_expenses,
                "cleaning_cost": opex_catalog.build_cleaning_cost(
                    opex.get("cleaning") or {}
                ),
                "property_taxes": opex_catalog.build_opex_property_taxes(
                    property_tax_pct=opex.get("property_tax_pct"),
                    purchase_price=purchase_price,
                ),
                "construction_amenities": [
                    option
                    for option in options
                    if option.get("id") in bedroom_keyed_ids
                ],
                # Mirrors _apply_opex_config_values, which maps these two opex
                # columns onto the config the payload builder reads.
                "land_assumptions_pct": opex_by_bedrooms.land_value,
                "annual_re_appreciation_pct": opex_by_bedrooms.appreciation,
            }
        )

    @staticmethod
    def _purchase_price_of(underwriting) -> Decimal | None:
        """The price the property-tax blob is a percentage of.

        The top-level column is promoted from ``purchase_details`` on every
        save/update that carries it, so it is normally authoritative; the blob
        is read as a fallback for rows where the promotion never ran. ``None``
        is a legitimate answer for a deal with no price yet — the tax blob
        simply comes back null and the rest of the context is still useful.
        """
        if underwriting.purchase_price is not None:
            return underwriting.purchase_price

        purchase_details = getattr(underwriting.detail, "purchase_details", None)
        if isinstance(purchase_details, dict):
            price = purchase_details.get("purchase_price")
            if price is not None:
                return Decimal(str(price))

        return None

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
