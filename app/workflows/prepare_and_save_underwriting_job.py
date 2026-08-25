from sqlalchemy.ext.asyncio import AsyncSession

from app.airbnb_public.repositories.cleaned_data_repository import CleanedDataRepository
from app.airbnb_public.services.cleaned_data_service import CleanedDataService
from app.external_api.services.external_api_service import ExternalApiService
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService
from app.iron_bank.services.underwriting_payload_builder import (
    UnderwritingPayloadBuilder,
)
from app.markets.repositories.construction_repository import ConstructionAmenitiesRepository
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.opex_repository import OpexByBedroomsRepository
from app.markets.repositories.realtor_repository import RealtorRepository
from app.markets.services.market_service import MarketService
from app.markets.services.opex_service import OpexByBedroomsService
from app.workflows.prepare_uw_data_job import PrepareUwDataJob
from app.zillow.repositories.scheduled_listings_repository import (
    ScheduledListingsRepository,
)
from app.zillow.services.scheduled_listings_service import ScheduledListingsService


class PrepareAndSaveUnderwritingJob:
    """Prepares one listing and persists it as a draft underwriting."""

    def __init__(
        self,
        *,
        prepare_job,
        payload_builder,
        save_service,
        underwriting_repository,
        listings_service=None,
    ):
        self.prepare_job = prepare_job
        self.payload_builder = payload_builder
        self.save_service = save_service
        self.underwriting_repository = underwriting_repository
        # Supplies the listing's detail_url for the duplicate guard's URL
        # fallback. Optional: without it the guard is zpid-only, as before.
        self.listings_service = listings_service

    @classmethod
    def from_session(
        cls,
        db: AsyncSession,
        *,
        external_api_service: ExternalApiService | None = None,
    ) -> "PrepareAndSaveUnderwritingJob":
        underwriting_repository = UnderwritingRepository(db)
        return cls(
            prepare_job=PrepareUwDataJob.from_session(
                db, external_api_service=external_api_service
            ),
            payload_builder=UnderwritingPayloadBuilder(),
            save_service=SaveUnderwritingService(
                underwriting_repository,
                market_service=MarketService(
                    MarketRepository(db),
                    ConstructionAmenitiesRepository(db),
                    RealtorRepository(db),
                ),
                listings_service=ScheduledListingsService(
                    ScheduledListingsRepository(db)
                ),
                cleaned_data_service=CleanedDataService(CleanedDataRepository(db)),
                opex_service=OpexByBedroomsService(
                    OpexByBedroomsRepository(db), MarketRepository(db)
                ),
            ),
            underwriting_repository=underwriting_repository,
            listings_service=ScheduledListingsService(
                ScheduledListingsRepository(db)
            ),
        )

    async def run(self, zpid: str) -> dict:
        existing = await self._find_existing(zpid)
        if existing is not None:
            return {
                "zpid": zpid,
                "status": "skipped_existing",
                "underwriting_id": existing.id,
            }

        prepared = await self.prepare_job.run(zpid)
        payload = self.payload_builder.build(prepared)
        purchase_price = payload.purchase_price
        details = getattr(payload, "details", None)
        if details is not None and details.purchase_details is not None:
            purchase_price = details.purchase_details.purchase_price

        if purchase_price is None:
            return {
                "zpid": zpid,
                "status": "skipped_no_purchase_price",
            }

        result = await self.save_service.save(payload)
        return {
            "zpid": zpid,
            "status": "saved",
            "underwriting_id": result.underwriting_id,
        }

    async def _find_existing(self, zpid: str):
        """Any underwriting already covering this listing, by zpid or by URL.

        The zpid check alone is not enough. Deals created from a URL before the
        scrape started persisting listings carry a NULL zpid, so they are
        invisible to it — and the automated run would then create a second,
        unrelated deal for a property an analyst has already underwritten. The
        listing_url fallback catches those. Roughly 1.6k such rows exist, and
        only a fraction have a recoverable zpid (see
        scripts/backfill_underwriting_zpids.py), so this fallback is the durable
        guard rather than a stopgap until the backfill runs.
        """
        existing = await self.underwriting_repository.get_by_zpid(zpid)
        if existing is not None:
            return existing

        if self.listings_service is None:
            return None

        listing = await self.listings_service.get_by_zpid(zpid)
        detail_url = getattr(listing, "detail_url", None)
        if not detail_url:
            return None

        return await self.underwriting_repository.get_by_listing_url(detail_url)
