from sqlalchemy.ext.asyncio import AsyncSession

from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository


class SyncUnderwritingPropertyPendingJob:
    """Re-sync ``property_pending`` on underwritings from their Zillow listings.

    Mirrors the boolean logic applied at save time in
    ``SaveUnderwritingService._apply_listing_boolean_fields``: a listing whose
    ``home_status`` is anything other than ``FOR_SALE`` (or missing) is treated
    as pending. This keeps that flag current as listings change status after
    the underwriting was first saved.

    The value is a pure function of the joined listing's ``home_status``, so the
    whole set is reconciled in a single ``UPDATE ... FROM`` rather than row by
    row — no per-row recomputation is needed (unlike price reconciliation).
    """

    def __init__(self, *, underwriting_repository):
        self.underwriting_repository = underwriting_repository

    @classmethod
    def from_session(cls, db: AsyncSession) -> "SyncUnderwritingPropertyPendingJob":
        return cls(underwriting_repository=UnderwritingRepository(db))

    async def run(self) -> dict:
        updated = await self.underwriting_repository.bulk_sync_property_pending()
        return {"updated": updated}
