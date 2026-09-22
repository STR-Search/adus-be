from decimal import Decimal

from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingResult
from app.iron_bank.services.create_blank_underwriting_service import (
    CreateBlankUnderwritingService,
)


class CreateBlankUnderwritingController:
    """Mirrors ``CreateUnderwritingFromUrlController`` minus its 409/422 cases.

    There is no listing to be a duplicate of, to fail to scrape, or to
    contradict the requested market, so the only failures left are a bad
    request and an unexpected one.
    """

    def __init__(self, service: CreateBlankUnderwritingService):
        self.service = service

    async def create_blank(
        self,
        *,
        purchase_price: Decimal,
        market_id: int | None = None,
        bedrooms: int | None = None,
        bathrooms: Decimal | None = None,
        current_user_id: int | None = None,
    ) -> SaveUnderwritingResult:
        try:
            return await self.service.create(
                purchase_price=purchase_price,
                market_id=market_id,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                current_user_id=current_user_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.create_blank_underwriting.error",
                error=str(e),
            )
            raise HTTPException(
                status_code=500, detail="Failed to create blank underwriting"
            )
