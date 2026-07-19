from collections.abc import Sequence

from fastapi import HTTPException

from app.core.logger import logger
from app.core.reference_data.schemas import (
    CreateEnumOptionPayload,
    EnumOptionRead,
    ReferenceDataResult,
    UpdateEnumOptionPayload,
)
from app.core.reference_data.service import ReferenceDataService


class ReferenceDataController:
    def __init__(self, service: ReferenceDataService):
        self.service = service

    async def get_reference_data(
        self,
        domain: str | None = None,
        set_codes: Sequence[str] | None = None,
    ) -> ReferenceDataResult:
        try:
            return await self.service.get_reference_data(
                domain=domain, set_codes=set_codes
            )
        except Exception as e:
            logger.error("reference_data.get.error", error=str(e))
            raise HTTPException(
                status_code=500, detail="Failed to fetch reference data"
            )

    async def create_option(
        self, payload: CreateEnumOptionPayload
    ) -> EnumOptionRead:
        try:
            return await self.service.create_option(payload)
        except Exception as e:
            logger.error("reference_data.create.error", error=str(e))
            raise HTTPException(
                status_code=500, detail="Failed to create reference option"
            )

    async def update_option(
        self, option_id: int, payload: UpdateEnumOptionPayload
    ) -> EnumOptionRead:
        try:
            option = await self.service.update_option(option_id, payload)
            if option is None:
                raise HTTPException(
                    status_code=404, detail=f"Enum option {option_id} not found"
                )
            return option
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "reference_data.update.error", option_id=option_id, error=str(e)
            )
            raise HTTPException(
                status_code=500, detail="Failed to update reference option"
            )
