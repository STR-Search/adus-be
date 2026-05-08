from fastapi import HTTPException

from app.core.logger import logger
from app.markets.schemas.opex import (
    OpexByBedroomsCreateSchema,
    OpexByBedroomsSchema,
    OpexByBedroomsUpdateSchema,
    OpexBySizeCreateSchema,
    OpexBySizeSchema,
    OpexBySizeUpdateSchema,
)
from app.markets.services.opex_service import OpexByBedroomsService, OpexBySizeService


class OpexByBedroomsController:
    def __init__(self, service: OpexByBedroomsService):
        self.service = service

    async def get_by_id(self, record_id: int) -> OpexByBedroomsSchema:
        try:
            record = await self.service.get_by_id(record_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Opex bedrooms record {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("opex.bedrooms.get_by_id.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch opex bedrooms record")

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_id: int | None = None,
        market_slug: str | None = None,
        bedrooms: int | None = None,
    ) -> dict:
        try:
            items, total, pages = await self.service.get_paginated(
                page=page,
                page_size=page_size,
                market_id=market_id,
                market_slug=market_slug,
                bedrooms=bedrooms,
            )
            return {"items": items, "total": total, "pages": pages, "page": page, "page_size": page_size}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error("opex.bedrooms.get_paginated.error", page=page, page_size=page_size, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch opex bedrooms records")

    async def create(self, data: OpexByBedroomsCreateSchema) -> OpexByBedroomsSchema:
        try:
            return await self.service.create(data)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error("opex.bedrooms.create.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to create opex bedrooms record")

    async def update(self, record_id: int, data: OpexByBedroomsUpdateSchema) -> OpexByBedroomsSchema:
        try:
            record = await self.service.update(record_id, data)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Opex bedrooms record {record_id} not found")
            return record
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error("opex.bedrooms.update.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update opex bedrooms record")

    async def delete(self, record_id: int) -> dict:
        try:
            deleted = await self.service.delete(record_id)
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Opex bedrooms record {record_id} not found")
            return {"detail": f"Opex bedrooms record {record_id} deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("opex.bedrooms.delete.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to delete opex bedrooms record")


class OpexBySizeController:
    def __init__(self, service: OpexBySizeService):
        self.service = service

    async def get_by_id(self, record_id: int) -> OpexBySizeSchema:
        try:
            record = await self.service.get_by_id(record_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Opex size record {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("opex.size.get_by_id.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch opex size record")

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        market_id: int | None = None,
        market_slug: str | None = None,
        sqft: int | None = None,
    ) -> dict:
        try:
            items, total, pages = await self.service.get_paginated(
                page=page,
                page_size=page_size,
                market_id=market_id,
                market_slug=market_slug,
                sqft=sqft,
            )
            return {"items": items, "total": total, "pages": pages, "page": page, "page_size": page_size}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error("opex.size.get_paginated.error", page=page, page_size=page_size, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch opex size records")

    async def create(self, data: OpexBySizeCreateSchema) -> OpexBySizeSchema:
        try:
            return await self.service.create(data)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error("opex.size.create.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to create opex size record")

    async def update(self, record_id: int, data: OpexBySizeUpdateSchema) -> OpexBySizeSchema:
        try:
            record = await self.service.update(record_id, data)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Opex size record {record_id} not found")
            return record
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error("opex.size.update.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update opex size record")

    async def delete(self, record_id: int) -> dict:
        try:
            deleted = await self.service.delete(record_id)
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Opex size record {record_id} not found")
            return {"detail": f"Opex size record {record_id} deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("opex.size.delete.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to delete opex size record")
