from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.workflows.reconcile_underwriting_price_job import (
    ReconcileUnderwritingPriceJob,
)
from app.zillow.repositories.scheduled_listing_details_repository import (
    ScheduledListingDetailsRepository,
)
from app.zillow.services.scheduled_listing_details_service import (
    ScheduledListingDetailsService,
)


class BatchReconcileUnderwritingPricesJob:
    def __init__(self, *, db, listing_details_service, reconcile_job):
        self.db = db
        self.listing_details_service = listing_details_service
        self.reconcile_job = reconcile_job

    @classmethod
    def from_session(cls, db: AsyncSession) -> "BatchReconcileUnderwritingPricesJob":
        return cls(
            db=db,
            listing_details_service=ScheduledListingDetailsService(
                ScheduledListingDetailsRepository(db)
            ),
            reconcile_job=ReconcileUnderwritingPriceJob.from_session(db),
        )

    async def run(self, *, since_hours: int, limit: int | None = None) -> dict:
        zpids = await self.listing_details_service.get_price_changed_zpids_since(
            since_hours=since_hours,
            limit=limit,
        )
        # Counts are keyed by status and seeded with the known ones so the shape
        # of the response stays stable when a batch happens to contain none of a
        # given outcome. setdefault on write means a new status added to the
        # reconcile job shows up here instead of raising KeyError mid-batch.
        counts = {
            "updated": 0,
            "skipped_same_price": 0,
            "skipped_no_underwriting": 0,
            "skipped_no_purchase_price": 0,
            "skipped_terminal_status": 0,
            "failed": 0,
        }
        # A zpid now covers every version of the deal, so the per-listing counts
        # above no longer say how many rows actually moved. These do.
        underwriting_counts = dict.fromkeys(counts, 0)
        results = []
        for zpid in zpids:
            try:
                result = await self.reconcile_job.run(zpid)
            except Exception as exc:
                logger.exception(
                    "iron_bank.batch_reconcile.listing_failed",
                    zpid=zpid,
                )
                # A failed zpid may have aborted the transaction; roll back so
                # the remaining zpids run on a clean session. Without this the
                # next query raises PendingRollbackError and every remaining
                # zpid fails, turning one transient error into a failed batch.
                await self.db.rollback()
                counts["failed"] += 1
                results.append({"zpid": zpid, "status": "failed", "error": str(exc)})
                continue
            counts[result["status"]] = counts.setdefault(result["status"], 0) + 1
            for row in result.get("results", []):
                underwriting_counts[row["status"]] = (
                    underwriting_counts.setdefault(row["status"], 0) + 1
                )
            results.append(result)
        return {
            "found": len(zpids),
            "processed": len(results),
            **counts,
            "underwritings": underwriting_counts,
            "results": results,
        }
