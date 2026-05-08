from fastapi import HTTPException

from app.core.logger import logger
from app.markets.schemas.construction import (
    ConstructionCostsAmenitiesCreateSchema,
    ConstructionCostsAmenitiesSchema,
    ConstructionCostsAmenitiesUpdateSchema,
    ConstructionCostsRemodelingCreateSchema,
    ConstructionCostsRemodelingSchema,
    ConstructionCostsRemodelingUpdateSchema,
)
from app.markets.services.construction_service import (
    ConstructionAmenitiesService,
    ConstructionRemodelingService,
)


class ConstructionAmenitiesController:
    def __init__(self, service: ConstructionAmenitiesService):
        self.service = service

    async def get_by_id(self, record_id: int) -> ConstructionCostsAmenitiesSchema:
        try:
            record = await self.service.get_by_id(record_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Amenity {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("construction.amenities.get_by_id.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch amenity")

    async def get_all(
        self,
        location: str | None = None,
        search: str | None = None,
    ) -> list[ConstructionCostsAmenitiesSchema]:
        try:
            return await self.service.get_all(location=location, search=search)
        except Exception as e:
            logger.error("construction.amenities.get_all.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch amenities")

    async def create(self, data: ConstructionCostsAmenitiesCreateSchema) -> ConstructionCostsAmenitiesSchema:
        try:
            return await self.service.create(data)
        except Exception as e:
            logger.error("construction.amenities.create.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to create amenity")

    async def update(self, record_id: int, data: ConstructionCostsAmenitiesUpdateSchema) -> ConstructionCostsAmenitiesSchema:
        try:
            record = await self.service.update(record_id, data)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Amenity {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("construction.amenities.update.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update amenity")

    async def delete(self, record_id: int) -> dict:
        try:
            deleted = await self.service.delete(record_id)
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Amenity {record_id} not found")
            return {"detail": f"Amenity {record_id} deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("construction.amenities.delete.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to delete amenity")


class ConstructionRemodelingController:
    def __init__(self, service: ConstructionRemodelingService):
        self.service = service

    async def get_by_id(self, record_id: int) -> ConstructionCostsRemodelingSchema:
        try:
            record = await self.service.get_by_id(record_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Remodeling record {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("construction.remodeling.get_by_id.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch remodeling record")

    async def get_all(
        self,
        location: str | None = None,
        search: str | None = None,
    ) -> list[ConstructionCostsRemodelingSchema]:
        try:
            return await self.service.get_all(location=location, search=search)
        except Exception as e:
            logger.error("construction.remodeling.get_all.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch remodeling records")

    async def create(self, data: ConstructionCostsRemodelingCreateSchema) -> ConstructionCostsRemodelingSchema:
        try:
            return await self.service.create(data)
        except Exception as e:
            logger.error("construction.remodeling.create.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to create remodeling record")

    async def update(self, record_id: int, data: ConstructionCostsRemodelingUpdateSchema) -> ConstructionCostsRemodelingSchema:
        try:
            record = await self.service.update(record_id, data)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Remodeling record {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("construction.remodeling.update.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update remodeling record")

    async def delete(self, record_id: int) -> dict:
        try:
            deleted = await self.service.delete(record_id)
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Remodeling record {record_id} not found")
            return {"detail": f"Remodeling record {record_id} deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("construction.remodeling.delete.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to delete remodeling record")
