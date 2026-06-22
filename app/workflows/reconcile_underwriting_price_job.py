from sqlalchemy.ext.asyncio import AsyncSession

from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.services.purchase_price_reconciliation_payload_builder import (
    PurchasePriceReconciliationPayloadBuilder,
)
from app.iron_bank.services.update_underwriting_service import UpdateUnderwritingService
from app.zillow.repositories.scheduled_listings_repository import (
    ScheduledListingsRepository,
)
from app.zillow.services.scheduled_listings_service import ScheduledListingsService


class ReconcileUnderwritingPriceJob:
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
        underwriting = await self.underwriting_repository.get_by_zpid(zpid)
        if underwriting is None:
            return {"zpid": zpid, "status": "skipped_no_underwriting"}

        listing = await self.listings_service.get_by_zpid(zpid)
        raw_price = (
            None if listing is None else listing.unformatted_price or listing.price
        )
        purchase_price = self.payload_builder.normalize_purchase_price(raw_price)
        if purchase_price is None:
            return {
                "zpid": zpid,
                "status": "skipped_no_purchase_price",
                "underwriting_id": underwriting.id,
            }
        if underwriting.purchase_price == purchase_price:
            return {
                "zpid": zpid,
                "status": "skipped_same_price",
                "underwriting_id": underwriting.id,
            }

        payload = self.payload_builder.build(
            underwriting=underwriting,
            purchase_price=purchase_price,
        )
        await self.update_service.reconcile_purchase_price(underwriting.id, payload)
        return {
            "zpid": zpid,
            "status": "updated",
            "underwriting_id": underwriting.id,
        }
