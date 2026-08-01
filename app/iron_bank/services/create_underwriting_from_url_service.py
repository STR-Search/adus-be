from typing import Any, Protocol

import structlog

from app.iron_bank.schemas.prepare_uw import MarketContext
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingResult
from app.iron_bank.services.non_automated_underwriting_payload_builder import (
    NonAutomatedUnderwritingPayloadBuilder,
)
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService

logger = structlog.get_logger(__name__)


class UnderwritingAlreadyExistsError(Exception):
    """Raised when an underwriting already exists for the given listing URL."""

    def __init__(self, underwriting_id: int):
        self.underwriting_id = underwriting_id
        super().__init__(
            f"An underwriting already exists for this property "
            f"(underwriting_id={underwriting_id})"
        )


class ZillowPropertyReader(Protocol):
    async def fetch_property_details(
        self, *, url: str
    ) -> dict[str, Any] | None: ...


class ExistingUnderwritingReader(Protocol):
    async def get_by_listing_url(self, listing_url: str) -> Any | None: ...


class MarketContextReader(Protocol):
    """Satisfied by ``app.workflows.prepare_uw_data_job.PrepareUwDataJob``.

    Structural, not imported: the market/opex/amenity lookups live in the
    workflows layer because they cross domains, and iron_bank must not import
    back into it. The router does the wiring.
    """

    async def build_market_context(
        self, *, market_id: int | None, bedrooms: int | None, area: int | None
    ) -> MarketContext: ...


class CreateUnderwritingFromUrlService:
    """Creates a draft non-automated underwriting from a Zillow URL.

    Orchestrates the whole non-automated entry point: guard against duplicates
    by listing URL, fetch property details from the external API, load the
    market context for the analyst's ``market_id`` (or a zeroed template when
    they didn't pick one), build a seeded save payload, and persist it via the
    generic save service. Saving itself performs no network calls. Returns the
    new underwriting id so the analyst can start filling it in via update.
    """

    def __init__(
        self,
        zillow_property_service: ZillowPropertyReader,
        save_service: SaveUnderwritingService,
        underwriting_reader: ExistingUnderwritingReader,
        market_context_reader: MarketContextReader | None = None,
        builder: NonAutomatedUnderwritingPayloadBuilder | None = None,
    ):
        self.zillow_property_service = zillow_property_service
        self.save_service = save_service
        self.underwriting_reader = underwriting_reader
        self.market_context_reader = market_context_reader
        self.builder = builder or NonAutomatedUnderwritingPayloadBuilder()

    async def create(
        self, *, url: str, market_id: int | None = None
    ) -> SaveUnderwritingResult:
        # Idempotency: the stored listing_url is exactly the request URL, so we
        # can short-circuit before spending an external API call.
        existing = await self.underwriting_reader.get_by_listing_url(url)
        if existing is not None:
            logger.info(
                "iron_bank.create_underwriting_from_url.already_exists",
                url=url,
                underwriting_id=existing.id,
            )
            raise UnderwritingAlreadyExistsError(existing.id)

        zillow_property = await self.zillow_property_service.fetch_property_details(
            url=url
        )
        if zillow_property is None:
            logger.warning(
                "iron_bank.create_underwriting_from_url.fetch_failed",
                url=url,
            )
            raise ValueError(
                "Could not fetch Zillow property details for the given URL"
            )

        market_context = await self._build_market_context(market_id, zillow_property)
        payload = self.builder.build_from_zillow_property(
            listing_url=url,
            zillow_property=zillow_property,
            market_context=market_context,
        )
        return await self.save_service.save(payload)

    async def _build_market_context(
        self, market_id: int | None, zillow_property: dict[str, Any]
    ) -> MarketContext | None:
        """Load the market context keyed to the fetched property's size.

        The opex rows are keyed by bedrooms and sqft, both of which come off the
        live fetch. Returns ``None`` when no reader is configured, in which case
        the payload falls back to defaults with no line items.
        """
        if self.market_context_reader is None:
            logger.warning(
                "iron_bank.create_underwriting_from_url.no_market_context_reader",
                market_id=market_id,
                detail="opex and rehab line items will not be seeded",
            )
            return None

        context = await self.market_context_reader.build_market_context(
            market_id=market_id,
            # Zillow reports bedrooms as a number that may arrive as a float,
            # unlike scheduled_listings.beds; the opex lookup keys on an int.
            bedrooms=self._as_int(zillow_property.get("bedrooms")),
            area=self._as_int(zillow_property.get("area")),
        )
        logger.info(
            "iron_bank.create_underwriting_from_url.market_context_loaded",
            requested_market_id=market_id,
            resolved_market_id=context.market_id,
            is_template=context.market_id is None,
            opex_row_count=len(context.opex.absolute),
        )
        return context

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
