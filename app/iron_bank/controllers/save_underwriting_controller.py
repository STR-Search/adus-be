from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.save_underwriting import (
    SaveUnderwritingPayload,
    SaveUnderwritingResult,
)
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService


class SaveUnderwritingController:
    def __init__(self, service: SaveUnderwritingService):
        self.service = service

    async def save_underwriting(
        self,
        payload: SaveUnderwritingPayload,
    ) -> SaveUnderwritingResult:
        try:
            return await self.service.save(payload)
        except Exception as e:
            logger.error(
                "iron_bank.save_underwriting.error",
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to save underwriting")
