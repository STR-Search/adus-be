from datetime import date
from decimal import Decimal

from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.enums import SortOrder, UnderwritingSortBy
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingEditContextResult,
    GetUnderwritingsResult,
)
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService
from app.iron_bank.services.simulate_underwritings_service import (
    SimulateUnderwritingsService,
)


class GetUnderwritingController:
    def __init__(
        self,
        service: GetUnderwritingService,
        simulation_service: SimulateUnderwritingsService | None = None,
    ):
        self.service = service
        self.simulation_service = simulation_service

    async def get_underwritings(
        self,
        *,
        page: int,
        page_size: int,
        zpid: str | None = None,
        bedrooms: int | None = None,
        market_ids: list[int] | None = None,
        deal_status: str | None = None,
        analyst_id: int | None = None,
        owner_id: int | None = None,
        source: str | None = None,
        search: str | None = None,
        min_purchase_price: Decimal | None = None,
        max_purchase_price: Decimal | None = None,
        min_total_oop: Decimal | None = None,
        max_total_oop: Decimal | None = None,
        min_l_cash_on_cash: Decimal | None = None,
        max_l_cash_on_cash: Decimal | None = None,
        min_m_cash_on_cash: Decimal | None = None,
        max_m_cash_on_cash: Decimal | None = None,
        min_h_cash_on_cash: Decimal | None = None,
        max_h_cash_on_cash: Decimal | None = None,
        min_prr: Decimal | None = None,
        max_prr: Decimal | None = None,
        min_created_at: date | None = None,
        max_created_at: date | None = None,
        min_deal_approved: date | None = None,
        max_deal_approved: date | None = None,
        turnkey: bool | None = None,
        furnished: bool | None = None,
        luxury: bool | None = None,
        tax_efficient: bool | None = None,
        new_construction: bool | None = None,
        existing_airbnb: bool | None = None,
        arv: bool | None = None,
        high_cash_on_cash: bool | None = None,
        low_cash_on_cash: bool | None = None,
        add_inground_pool: bool | None = None,
        waterfront: bool | None = None,
        remote: bool | None = None,
        can_support_cohost: bool | None = None,
        sort_by: UnderwritingSortBy = UnderwritingSortBy.ID,
        sort_order: SortOrder = SortOrder.DESC,
        interest_rate: Decimal | None = None,
        down_payment_pct: Decimal | None = None,
    ) -> GetUnderwritingsResult:
        boolean_tags = {
            field: value
            for field, value in (
                ("turnkey", turnkey),
                ("furnished", furnished),
                ("luxury", luxury),
                ("tax_efficient", tax_efficient),
                ("new_construction", new_construction),
                ("existing_airbnb", existing_airbnb),
                ("arv", arv),
                ("high_cash_on_cash", high_cash_on_cash),
                ("low_cash_on_cash", low_cash_on_cash),
                ("add_inground_pool", add_inground_pool),
                ("waterfront", waterfront),
                ("remote", remote),
                ("can_support_cohost", can_support_cohost),
            )
            if value is not None
        }
        filters = dict(
            page=page,
            page_size=page_size,
            zpid=zpid,
            bedrooms=bedrooms,
            market_ids=market_ids,
            deal_status=deal_status,
            analyst_id=analyst_id,
            owner_id=owner_id,
            source=source,
            search=search,
            min_purchase_price=min_purchase_price,
            max_purchase_price=max_purchase_price,
            min_total_oop=min_total_oop,
            max_total_oop=max_total_oop,
            min_l_cash_on_cash=min_l_cash_on_cash,
            max_l_cash_on_cash=max_l_cash_on_cash,
            min_m_cash_on_cash=min_m_cash_on_cash,
            max_m_cash_on_cash=max_m_cash_on_cash,
            min_h_cash_on_cash=min_h_cash_on_cash,
            max_h_cash_on_cash=max_h_cash_on_cash,
            min_prr=min_prr,
            max_prr=max_prr,
            min_created_at=min_created_at,
            max_created_at=max_created_at,
            min_deal_approved=min_deal_approved,
            max_deal_approved=max_deal_approved,
            boolean_tags=boolean_tags,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        simulating = (
            interest_rate is not None or down_payment_pct is not None
        ) and self.simulation_service is not None
        try:
            if simulating:
                return await self.simulation_service.get_all_simulated(
                    **filters,
                    interest_rate=interest_rate,
                    down_payment_pct=down_payment_pct,
                )
            return await self.service.get_all(**filters)
        except Exception as e:
            logger.error(
                "iron_bank.get_underwritings.error",
                **filters,
                interest_rate=interest_rate,
                down_payment_pct=down_payment_pct,
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
