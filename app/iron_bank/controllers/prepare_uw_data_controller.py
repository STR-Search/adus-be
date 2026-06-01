from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService


class PrepareUwDataController:
    def __init__(self, service: PrepareUwDataService):
        self.service = service

    async def get_prepare_uw_data(self, zillow_url: str) -> dict:
        try:
            return await self.service.get_uw_data_for_listing(zillow_url)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.prepare_uw_data.error",
                zillow_url=zillow_url,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwriting data")
