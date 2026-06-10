from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.get_underwriting import GetUnderwritingResult
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService


class GetUnderwritingController:
    def __init__(self, service: GetUnderwritingService):
        self.service = service

    async def get_underwriting(self, underwriting_id: int) -> GetUnderwritingResult:
        try:
            return await self.service.get(underwriting_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.get_underwriting.error",
                underwriting_id=underwriting_id,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwriting")
