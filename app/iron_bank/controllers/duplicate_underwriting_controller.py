from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.duplicate_underwriting import DuplicateUnderwritingResult
from app.iron_bank.services.duplicate_underwriting_service import (
    DuplicateUnderwritingService,
)


class DuplicateUnderwritingController:
    def __init__(self, service: DuplicateUnderwritingService):
        self.service = service

    async def duplicate_underwriting(
        self,
        *,
        underwriting_id: int,
        current_user_id: int | None = None,
    ) -> DuplicateUnderwritingResult:
        try:
            return await self.service.duplicate(
                underwriting_id=underwriting_id,
                current_user_id=current_user_id,
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.duplicate_underwriting.error",
                underwriting_id=underwriting_id,
                error=str(e),
            )
            raise HTTPException(
                status_code=500, detail="Failed to duplicate underwriting"
            )
