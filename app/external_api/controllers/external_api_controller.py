from fastapi import HTTPException

from app.core.logger import logger
from app.external_api.schemas.external_api import MortgageRateResponse
from app.external_api.services.external_api_service import ExternalApiService


class ExternalApiController:
    def __init__(self, service: ExternalApiService):
        self.service = service

    async def get_30y_fixed_rate(self) -> MortgageRateResponse:
        try:
            result = await self.service.get_30y_fixed_rate()
            if result is None:
                raise HTTPException(status_code=502, detail="Could not retrieve mortgage rate from FRED")
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error("external_api.get_30y_fixed_rate.error", error=str(e))
            raise HTTPException(status_code=502, detail="External API request failed")
