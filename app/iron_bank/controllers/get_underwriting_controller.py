from typing import Any

from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.get_underwriting import (
    ConstructionAmenityOption,
    ConstructionRemodelingOption,
    EditContextData,
    EditContextualData,
    GetUnderwritingEditContextResult,
    GetUnderwritingResult,
    GetUnderwritingsResult,
)
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService


class GetUnderwritingController:
    def __init__(
        self,
        service: GetUnderwritingService,
        construction_amenities_service: Any = None,
        construction_remodeling_service: Any = None,
    ):
        self.service = service
        self.construction_amenities_service = construction_amenities_service
        self.construction_remodeling_service = construction_remodeling_service

    async def get_underwritings(
        self,
        *,
        page: int,
        page_size: int,
        zpid: str | None = None,
        market_id: int | None = None,
    ) -> GetUnderwritingsResult:
        try:
            return await self.service.get_all(
                page=page,
                page_size=page_size,
                zpid=zpid,
                market_id=market_id,
            )
        except Exception as e:
            logger.error(
                "iron_bank.get_underwritings.error",
                page=page,
                page_size=page_size,
                zpid=zpid,
                market_id=market_id,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwritings")

    async def get_underwriting(self, underwriting_id: int) -> GetUnderwritingResult:
        try:
            return await self.service.get(underwriting_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.get_underwriting.error",
                underwriting_id=underwriting_id,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwriting")

    async def get_underwriting_edit_context(
        self, underwriting_id: int
    ) -> GetUnderwritingEditContextResult:
        try:
            underwriting = await self.service.get(underwriting_id)
            amenities = await self.construction_amenities_service.get_all()
            remodeling = await self.construction_remodeling_service.get_all()
            return GetUnderwritingEditContextResult(
                data=EditContextData(
                    underwriting=underwriting,
                    contextual=EditContextualData(
                        construction_amenities=[
                            ConstructionAmenityOption.model_validate(a.model_dump()) for a in amenities
                        ],
                        construction_remodeling=[
                            ConstructionRemodelingOption.model_validate(r.model_dump()) for r in remodeling
                        ],
                    ),
                )
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.get_underwriting_edit_context.error",
                underwriting_id=underwriting_id,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwriting edit context")
