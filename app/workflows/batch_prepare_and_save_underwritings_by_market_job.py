from sqlalchemy.ext.asyncio import AsyncSession

from app.zillow.repositories.scheduled_listings_repository import (
    ScheduledListingsRepository,
)
from app.zillow.services.scheduled_listings_service import ScheduledListingsService
from app.workflows.prepare_and_save_underwriting_job import (
    PrepareAndSaveUnderwritingJob,
)


class BatchPrepareAndSaveUnderwritingsByMarketJob:
    """Runs the automated UW save workflow for recent active Zillow listings in a market."""

    def __init__(self, *, listings_service, prepare_and_save_job):
        self.listings_service = listings_service
        self.prepare_and_save_job = prepare_and_save_job

    @classmethod
    def from_session(
        cls, db: AsyncSession
    ) -> "BatchPrepareAndSaveUnderwritingsByMarketJob":
        return cls(
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            prepare_and_save_job=PrepareAndSaveUnderwritingJob.from_session(db),
        )

    async def run(
        self,
        *,
        market_id: int,
        since_hours: int,
        limit: int | None = None,
    ) -> dict:
        listings = await self.listings_service.get_active_since_by_market(
            market_id=market_id,
            since_hours=since_hours,
            limit=limit,
        )

        results = []
        saved = 0
        skipped_existing = 0
        skipped_no_purchase_price = 0
        failed = 0

        for listing in listings:
            try:
                result = await self.prepare_and_save_job.run(listing.zpid)
            except Exception as exc:
                failed += 1
                results.append(
                    {
                        "zpid": listing.zpid,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                continue

            if result["status"] == "saved":
                saved += 1
            elif result["status"] == "skipped_existing":
                skipped_existing += 1
            elif result["status"] == "skipped_no_purchase_price":
                skipped_no_purchase_price += 1
            results.append(result)

        return {
            "market_id": market_id,
            "found": len(listings),
            "processed": len(results),
            "saved": saved,
            "skipped_existing": skipped_existing,
            "skipped_no_purchase_price": skipped_no_purchase_price,
            "failed": failed,
            "results": results,
        }
