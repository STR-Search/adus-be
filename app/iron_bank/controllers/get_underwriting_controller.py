from decimal import Decimal

from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.enums import SortOrder, UnderwritingSortBy
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingEditContextResult,
    GetUnderwritingsResult,
)
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService


class GetUnderwritingController:
    def __init__(self, service: GetUnderwritingService):
        self.service = service

    async def get_underwritings(
        self,
        *,
        page: int,
        page_size: int,
        zpid: str | None = None,
        market_id: int | None = None,
        deal_status: str | None = None,
        analyst_id: int | None = None,
        source: str | None = None,
        min_purchase_price: Decimal | None = None,
        max_purchase_price: Decimal | None = None,
        min_total_oop: Decimal | None = None,
        max_total_oop: Decimal | None = None,
        sort_by: UnderwritingSortBy = UnderwritingSortBy.ID,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> GetUnderwritingsResult:
        try:
            return await self.service.get_all(
                page=page,
                page_size=page_size,
                zpid=zpid,
                market_id=market_id,
                deal_status=deal_status,
                analyst_id=analyst_id,
                source=source,
                min_purchase_price=min_purchase_price,
                max_purchase_price=max_purchase_price,
                min_total_oop=min_total_oop,
                max_total_oop=max_total_oop,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        except Exception as e:
            logger.error(
                "iron_bank.get_underwritings.error",
                page=page,
                page_size=page_size,
                zpid=zpid,
                market_id=market_id,
                deal_status=deal_status,
                analyst_id=analyst_id,
                source=source,
                min_purchase_price=min_purchase_price,
                max_purchase_price=max_purchase_price,
                min_total_oop=min_total_oop,
                max_total_oop=max_total_oop,
                sort_by=sort_by,
                sort_order=sort_order,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwritings")

    async def get_underwriting(
        self, underwriting_id: int
    ) -> GetUnderwritingEditContextResult:
        try:
            return await self.service.get_edit_context(underwriting_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.get_underwriting.error",
                underwriting_id=underwriting_id,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwriting")
