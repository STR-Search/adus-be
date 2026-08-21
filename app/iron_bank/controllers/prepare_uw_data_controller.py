from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.prepare_uw import BedroomContext, PrepareUwDataResult
from app.workflows.prepare_uw_data_job import (
    BedroomContextNotFoundError,
    PrepareUwDataJob,
)


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
            raise HTTPException(
                status_code=500, detail="Failed to fetch underwriting data"
            )

    async def get_bedroom_context(
        self,
        *,
        underwriting_id: int,
        bedrooms: int,
    ) -> BedroomContext:
        try:
            return await self.job.build_bedroom_context(
                underwriting_id=underwriting_id,
                bedrooms=bedrooms,
            )
        except BedroomContextNotFoundError as e:
            # Unknown underwriting, no market on it, or no opex row at this
            # bedroom count — a 404 lets the FE say so and leave the form
            # untouched instead of placing blanks.
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.bedroom_context.error",
                underwriting_id=underwriting_id,
                bedrooms=bedrooms,
                error=str(e),
            )
            raise HTTPException(
                status_code=500, detail="Failed to fetch bedroom context"
            )
