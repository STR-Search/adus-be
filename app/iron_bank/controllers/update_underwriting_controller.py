from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.update_underwriting import (
    UpdateUnderwritingPayload,
    UpdateUnderwritingResult,
)
from app.iron_bank.services.update_underwriting_service import UpdateUnderwritingService


class UpdateUnderwritingController:
    def __init__(self, service: UpdateUnderwritingService):
        self.service = service

    async def update_underwriting(
        self,
        underwriting_id: int,
        payload: UpdateUnderwritingPayload,
    ) -> UpdateUnderwritingResult:
        try:
            return await self.service.update(underwriting_id, payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.update_underwriting.error",
                underwriting_id=underwriting_id,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to update underwriting")
