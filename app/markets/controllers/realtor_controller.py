from fastapi import HTTPException

from app.core.logger import logger
from app.markets.schemas.realtor import (
    RealtorCreateSchema,
    RealtorSchema,
    RealtorUpdateSchema,
)
from app.markets.services.realtor_service import RealtorService


class RealtorController:
    def __init__(self, service: RealtorService):
        self.service = service

    async def get_by_id(self, record_id: int) -> RealtorSchema:
        try:
            record = await self.service.get_by_id(record_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Realtor {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("realtors.get_by_id.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch realtor")

    async def get_all(self, search: str | None = None) -> list[RealtorSchema]:
        try:
            return await self.service.get_all(search=search)
        except Exception as e:
            logger.error("realtors.get_all.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch realtors")

    async def create(self, data: RealtorCreateSchema) -> RealtorSchema:
        try:
            return await self.service.create(data)
        except Exception as e:
            logger.error("realtors.create.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to create realtor")

    async def update(self, record_id: int, data: RealtorUpdateSchema) -> RealtorSchema:
        try:
            record = await self.service.update(record_id, data)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Realtor {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("realtors.update.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update realtor")

    async def delete(self, record_id: int) -> dict:
        try:
            deleted = await self.service.delete(record_id)
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Realtor {record_id} not found")
            return {"detail": f"Realtor {record_id} deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("realtors.delete.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to delete realtor")
