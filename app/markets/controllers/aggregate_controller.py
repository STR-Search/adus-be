from fastapi import HTTPException

from app.core.logger import logger
from app.markets.services.aggregate_service import AutomatedDealUnderwritingService


class AutomatedDealUnderwritingController:
    def __init__(self, service: AutomatedDealUnderwritingService):
        self.service = service

    async def get_underwriting_data(
        self,
        bedrooms: int,
        sqft: int,
        market_id: int | None = None,
        market_slug: str | None = None,
    ) -> dict:
        try:
            return await self.service.get_underwriting_data(
                bedrooms=bedrooms,
                sqft=sqft,
                market_id=market_id,
                market_slug=market_slug,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "underwriting.get_underwriting_data.error",
                bedrooms=bedrooms,
                sqft=sqft,
                market_id=market_id,
                market_slug=market_slug,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwriting data")
