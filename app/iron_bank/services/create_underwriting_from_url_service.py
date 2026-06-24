from typing import Any, Protocol

import structlog

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


class CreateUnderwritingFromUrlService:
    """Creates a draft non-automated underwriting from a Zillow URL.

    Orchestrates the whole non-automated entry point: guard against duplicates
    by listing URL, fetch property details from the external API, build a seeded
    save payload, and persist it via the generic save service. Saving itself
    performs no network calls. Returns the new underwriting id so the analyst
    can start filling it in via update.
    """

    def __init__(
        self,
        zillow_property_service: ZillowPropertyReader,
        save_service: SaveUnderwritingService,
        underwriting_reader: ExistingUnderwritingReader,
        builder: NonAutomatedUnderwritingPayloadBuilder | None = None,
    ):
        self.zillow_property_service = zillow_property_service
        self.save_service = save_service
        self.underwriting_reader = underwriting_reader
        self.builder = builder or NonAutomatedUnderwritingPayloadBuilder()

    async def create(self, *, url: str) -> SaveUnderwritingResult:
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

        payload = self.builder.build_from_zillow_property(
            listing_url=url,
            zillow_property=zillow_property,
        )
        return await self.save_service.save(payload)
