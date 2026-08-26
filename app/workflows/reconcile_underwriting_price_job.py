import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.services.deal_status_service import TERMINAL_DEAL_STATUSES
from app.iron_bank.services.purchase_price_reconciliation_payload_builder import (
    PurchasePriceReconciliationPayloadBuilder,
)
from app.iron_bank.services.update_underwriting_service import UpdateUnderwritingService
from app.zillow.repositories.scheduled_listings_repository import (
    ScheduledListingsRepository,
)
from app.zillow.services.scheduled_listings_service import ScheduledListingsService

logger = structlog.get_logger(__name__)


class ReconcileUnderwritingPriceJob:
    """Pushes a Zillow price change onto every underwriting for that listing.

    A zpid maps to many underwritings once deals are duplicated into versions,
    so this fans out over all of them rather than the newest alone. Reconciling
    only one would leave the other versions holding a stale purchase_price —
    and since purchase price drives PRR, total OOP and all three cash-on-cash
    figures, those rows would go quietly wrong while still reading as current.

    Deals in a terminal deal_status are skipped: a deal under contract has an
    agreed price Zillow no longer governs, deleted deals are dead, and training
    deals are fixed teaching artifacts.

    Each underwriting is reconciled independently — one failure is recorded
    against that row and the rest still run.
    """

    def __init__(
        self,
        *,
        listings_service,
        underwriting_repository,
        payload_builder,
        update_service,
    ):
        self.listings_service = listings_service
        self.underwriting_repository = underwriting_repository
        self.payload_builder = payload_builder
        self.update_service = update_service

    @classmethod
    def from_session(cls, db: AsyncSession) -> "ReconcileUnderwritingPriceJob":
        underwriting_repository = UnderwritingRepository(db)
        return cls(
            listings_service=ScheduledListingsService(ScheduledListingsRepository(db)),
            underwriting_repository=underwriting_repository,
            payload_builder=PurchasePriceReconciliationPayloadBuilder(),
            update_service=UpdateUnderwritingService(underwriting_repository),
        )

    async def run(self, zpid: str) -> dict:
        underwritings = await self.underwriting_repository.get_all_by_zpid(zpid)
        if not underwritings:
            return {"zpid": zpid, "status": "skipped_no_underwriting", "results": []}

        listing = await self.listings_service.get_by_zpid(zpid)
        raw_price = (
            None if listing is None else listing.unformatted_price or listing.price
        )
        purchase_price = self.payload_builder.normalize_purchase_price(raw_price)
        if purchase_price is None:
            return {
                "zpid": zpid,
                "status": "skipped_no_purchase_price",
                "results": [
                    {
                        "underwriting_id": underwriting.id,
                        "version": underwriting.version,
                        "status": "skipped_no_purchase_price",
                    }
                    for underwriting in underwritings
                ],
            }

        # Two phases, and the split is load-bearing. Every ORM read happens in
        # the plan phase, before the first write; the write phase then works
        # only from plain values and detached payloads.
        #
        # It has to be this way because writes share one session: a failing
        # ``repository.update`` rolls that session back, and ``rollback()``
        # expires every instance loaded by ``get_all_by_zpid`` — not just the
        # row that failed, and regardless of ``expire_on_commit``. Touching any
        # of them afterwards triggers a synchronous lazy refresh, which raises
        # MissingGreenlet under asyncio. Reading a later row's deal_status
        # mid-loop would therefore turn one failed version into a crash that
        # skips every version after it — the precise opposite of the per-row
        # isolation this job promises.
        planned = self._plan(underwritings, purchase_price)
        results = await self._apply(planned)
        return {
            "zpid": zpid,
            "status": self._aggregate_status(results),
            "results": results,
        }

    def _plan(self, underwritings, purchase_price) -> list[dict]:
        """Decide every row's fate and build its payload. ORM reads only."""
        planned = []
        for underwriting in underwritings:
            entry = {
                "underwriting_id": underwriting.id,
                "version": underwriting.version,
                "status": None,
                "payload": None,
            }
            if underwriting.deal_status in TERMINAL_DEAL_STATUSES:
                entry["status"] = "skipped_terminal_status"
            elif underwriting.purchase_price == purchase_price:
                entry["status"] = "skipped_same_price"
            else:
                try:
                    entry["payload"] = self.payload_builder.build(
                        underwriting=underwriting,
                        purchase_price=purchase_price,
                    )
                except Exception as exc:
                    # Most often a version missing purchase details, forecasted
                    # revenue, or taxes — which the builder rejects outright.
                    self._log_failure(entry, exc)
                    entry["status"] = "failed"
                    entry["error"] = str(exc)
            planned.append(entry)
        return planned

    async def _apply(self, planned: list[dict]) -> list[dict]:
        """Write the planned payloads. Touches no ORM instance."""
        for entry in planned:
            if entry["status"] is not None:
                continue
            try:
                await self.update_service.reconcile_purchase_price(
                    entry["underwriting_id"], entry["payload"]
                )
            except Exception as exc:
                self._log_failure(entry, exc)
                entry["status"] = "failed"
                entry["error"] = str(exc)
            else:
                entry["status"] = "updated"

        return [
            {key: value for key, value in entry.items() if key != "payload"}
            for entry in planned
        ]

    @staticmethod
    def _log_failure(entry: dict, exc: Exception) -> None:
        logger.warning(
            "iron_bank.reconcile_price.underwriting_failed",
            underwriting_id=entry["underwriting_id"],
            version=entry["version"],
            error=str(exc),
        )

    @staticmethod
    def _aggregate_status(results: list[dict]) -> str:
        """One status for the zpid, worst-news-first.

        ``failed`` outranks ``updated`` so a partial failure is never reported
        as a clean run — the per-row results carry the detail.
        """
        statuses = {result["status"] for result in results}
        for status in (
            "failed",
            "updated",
            "skipped_same_price",
            "skipped_terminal_status",
        ):
            if status in statuses:
                return status
        return "skipped_same_price"
