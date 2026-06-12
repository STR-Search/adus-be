from sqlalchemy.ext.asyncio import AsyncSession

from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService
from app.iron_bank.services.underwriting_payload_builder import UnderwritingPayloadBuilder
from app.workflows.prepare_uw_data_job import PrepareUwDataJob


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
            save_service=SaveUnderwritingService(underwriting_repository),
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
        result = await self.save_service.save(payload)
        return {
            "zpid": zpid,
            "status": "saved",
            "underwriting_id": result.underwriting_id,
        }
