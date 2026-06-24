from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingResult
from app.iron_bank.services.create_underwriting_from_url_service import (
    CreateUnderwritingFromUrlService,
    UnderwritingAlreadyExistsError,
)


class CreateUnderwritingFromUrlController:
    def __init__(self, service: CreateUnderwritingFromUrlService):
        self.service = service

    async def create_from_url(self, *, url: str) -> SaveUnderwritingResult:
        try:
            return await self.service.create(url=url)
        except UnderwritingAlreadyExistsError as e:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "An underwriting already exists for this property",
                    "underwriting_id": e.underwriting_id,
                },
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.create_underwriting_from_url.error",
                error=str(e),
            )
            raise HTTPException(
                status_code=500, detail="Failed to create underwriting from URL"
            )
