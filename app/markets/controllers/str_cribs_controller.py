from fastapi import HTTPException

from app.core.logger import logger
from app.markets.schemas.str_cribs import (
    StrCribsFeeDetailsCreateSchema,
    StrCribsFeeDetailsSchema,
    StrCribsFeeDetailsUpdateSchema,
)
from app.markets.services.str_cribs_service import StrCribsFeeDetailsService


class StrCribsFeeDetailsController:
    def __init__(self, service: StrCribsFeeDetailsService):
        self.service = service

    async def get_by_id(self, record_id: int) -> StrCribsFeeDetailsSchema:
        try:
            record = await self.service.get_by_id(record_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Str cribs fee detail {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("str_cribs.fee_details.get_by_id.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch str cribs fee detail")

    async def get_all(self) -> list[StrCribsFeeDetailsSchema]:
        try:
            return await self.service.get_all()
        except Exception as e:
            logger.error("str_cribs.fee_details.get_all.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to fetch str cribs fee details")

    async def create(self, data: StrCribsFeeDetailsCreateSchema) -> StrCribsFeeDetailsSchema:
        try:
            return await self.service.create(data)
        except Exception as e:
            logger.error("str_cribs.fee_details.create.error", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to create str cribs fee detail")

    async def update(self, record_id: int, data: StrCribsFeeDetailsUpdateSchema) -> StrCribsFeeDetailsSchema:
        try:
            record = await self.service.update(record_id, data)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Str cribs fee detail {record_id} not found")
            return record
        except HTTPException:
            raise
        except Exception as e:
            logger.error("str_cribs.fee_details.update.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update str cribs fee detail")

    async def delete(self, record_id: int) -> dict:
        try:
            deleted = await self.service.delete(record_id)
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Str cribs fee detail {record_id} not found")
            return {"detail": f"Str cribs fee detail {record_id} deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("str_cribs.fee_details.delete.error", record_id=record_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to delete str cribs fee detail")
