from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.prepare_uw import PrepareUwDataResult
from app.workflows.prepare_uw_data_job import PrepareUwDataJob


class PrepareUwDataController:
    def __init__(self, job: PrepareUwDataJob):
        self.job = job

    async def get_prepare_uw_data(self, zpid: str) -> PrepareUwDataResult:
        try:
            return await self.job.run(zpid)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.prepare_uw_data.error",
                zpid=zpid,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwriting data")
