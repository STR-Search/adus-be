from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.external_api.services.external_api_service import ExternalApiService
from app.zillow.repositories.scheduled_listings_repository import (
    ScheduledListingsRepository,
)
from app.zillow.services.scheduled_listings_service import ScheduledListingsService
from app.workflows.prepare_and_save_underwriting_job import (
    PrepareAndSaveUnderwritingJob,
)


class BatchPrepareAndSaveUnderwritingsJob:
    """Runs the automated UW save workflow for recent active Zillow listings."""

    def __init__(self, *, db, listings_service, prepare_and_save_job, external_api_service):
        self.db = db
        self.listings_service = listings_service
        self.prepare_and_save_job = prepare_and_save_job
        self.external_api_service = external_api_service

    @classmethod
    def from_session(cls, db: AsyncSession) -> "BatchPrepareAndSaveUnderwritingsJob":
        # One service shared by every listing: its FRED lookup is memoized per
        # instance, and `run` warms it before the first transaction opens.
        external_api_service = ExternalApiService()
        return cls(
            db=db,
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            prepare_and_save_job=PrepareAndSaveUnderwritingJob.from_session(
                db, external_api_service=external_api_service
            ),
            external_api_service=external_api_service,
        )

    async def run(self, *, since_hours: int, limit: int | None = None) -> dict:
        # Warm the FRED rate before the first query, so this network round-trip
        # happens with no transaction open. SQLAlchemy autobegins on the first
        # read below, and every listing's work runs inside a transaction until
        # its commit — under the transaction pooler an open transaction pins a
        # Postgres backend, so waiting on a third party inside one holds a
        # backend hostage. Memoized, so the listings below reuse this result;
        # a failed fetch stays uncached and each listing still retries.
        await self.external_api_service.get_30y_fixed_rate()

        listings = await self.listings_service.get_active_since(
            since_hours=since_hours,
            limit=limit,
        )

        results = []
        saved = 0
        skipped_existing = 0
        skipped_no_purchase_price = 0
        failed = 0

        # Read the zpids up front: a rollback below expires every ORM instance
        # in the session, and re-reading an expired attribute would trigger a
        # lazy load outside the async context (MissingGreenlet).
        zpids = [listing.zpid for listing in listings]

        for zpid in zpids:
            try:
                result = await self.prepare_and_save_job.run(zpid)
            except Exception as exc:
                logger.exception(
                    "iron_bank.batch_prepare.listing_failed",
                    zpid=zpid,
                )
                # A failed listing may have aborted the transaction; roll back
                # so the remaining listings run on a clean session.
                await self.db.rollback()
                failed += 1
                results.append(
                    {
                        "zpid": zpid,
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
            "found": len(listings),
            "processed": len(results),
            "saved": saved,
            "skipped_existing": skipped_existing,
            "skipped_no_purchase_price": skipped_no_purchase_price,
            "failed": failed,
            "results": results,
        }
