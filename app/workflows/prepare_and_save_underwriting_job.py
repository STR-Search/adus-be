from sqlalchemy.ext.asyncio import AsyncSession

from app.airbnb_public.repositories.cleaned_data_repository import CleanedDataRepository
from app.airbnb_public.services.cleaned_data_service import CleanedDataService
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService
from app.iron_bank.services.underwriting_payload_builder import (
    UnderwritingPayloadBuilder,
)
from app.markets.repositories.market_repository import MarketRepository
from app.markets.services.market_service import MarketService
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
    ):
        self.prepare_job = prepare_job
        self.payload_builder = payload_builder
        self.save_service = save_service
        self.underwriting_repository = underwriting_repository

    @classmethod
    def from_session(cls, db: AsyncSession) -> "PrepareAndSaveUnderwritingJob":
        underwriting_repository = UnderwritingRepository(db)
        return cls(
            prepare_job=PrepareUwDataJob.from_session(db),
            payload_builder=UnderwritingPayloadBuilder(),
            save_service=SaveUnderwritingService(
                underwriting_repository,
                market_service=MarketService(MarketRepository(db)),
                listings_service=ScheduledListingsService(
                    ScheduledListingsRepository(db)
                ),
                cleaned_data_service=CleanedDataService(CleanedDataRepository(db)),
            ),
            underwriting_repository=underwriting_repository,
        )

    async def run(self, zpid: str) -> dict:
        existing = await self.underwriting_repository.get_by_zpid(zpid)
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
