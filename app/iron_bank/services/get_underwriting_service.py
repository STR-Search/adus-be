from typing import Any

from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingResult,
    GetUnderwritingsResult,
)
from app.iron_bank.schemas.underwriting import UnderwritingBase


class GetUnderwritingService:
    def __init__(self, repository: UnderwritingRepository):
        self.repository = repository

    async def get(self, underwriting_id: int) -> GetUnderwritingResult:
        underwriting = await self.repository.get_by_id(underwriting_id)
        if underwriting is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")
        return self._to_result(underwriting)

    async def get_all(
        self,
        *,
        page: int,
        page_size: int,
        zpid: str | None = None,
        market_id: int | None = None,
    ) -> GetUnderwritingsResult:
        items, total, pages = await self.repository.get_all_paginated(
            page=page,
            page_size=page_size,
            zpid=zpid,
            market_id=market_id,
        )
        return GetUnderwritingsResult(
            data=[self._to_result(underwriting) for underwriting in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def _to_result(self, underwriting) -> GetUnderwritingResult:
        return GetUnderwritingResult.model_validate(
            {
                **self._parent_data(underwriting),
                "details": self._detail_data(underwriting.detail),
                "taxes": self._tax_data(underwriting.taxes),
                "optimization_list": [
                    self._optimization_item_data(item)
                    for item in underwriting.optimization_items
                ],
                "operating_expenses": [
                    self._operating_expense_data(expense)
                    for expense in underwriting.operating_expenses
                ],
                "comp_set": [
                    self._comp_set_data(comp) for comp in underwriting.comp_set
                ],
            }
        )

    def _parent_data(self, underwriting) -> dict[str, Any]:
        return {
            "id": underwriting.id,
            **{
                field: getattr(underwriting, field, None)
                for field in UnderwritingBase.model_fields
            },
        }

    def _detail_data(self, detail) -> dict[str, Any] | None:
        if detail is None:
            return None
        return {
            "purchase_details": detail.purchase_details,
            "y1_coc_incl_tax_savings": detail.y1_coc_incl_tax_savings,
            "forecasted_revenue": detail.forecasted_revenue,
            "cleaning_cost": detail.cleaning_cost,
            "zillow_property": detail.zillow_property,
            "analyst_notes": detail.analyst_notes,
        }

    def _tax_data(self, taxes) -> dict[str, Any] | None:
        if taxes is None:
            return None
        return {
            "land_assumptions_pct": taxes.land_assumptions_pct,
            "sla_multiplier_pct": taxes.sla_multiplier_pct,
            "improvement_basis": taxes.improvement_basis,
            "estimated_short_life_assets": taxes.estimated_short_life_assets,
            "bonus_amount_pct": taxes.bonus_amount_pct,
            "tax_rate_pct": taxes.tax_rate_pct,
            "y1_loss_from_depreciation": taxes.y1_loss_from_depreciation,
            "tax_savings": taxes.tax_savings,
        }

    def _optimization_item_data(self, item) -> dict[str, Any]:
        return {
            "category": item.category,
            "total_price": item.total_price,
            "metric": item.metric,
            "base_price": item.base_price,
            "spec": item.spec,
            "tier": item.tier,
        }

    def _operating_expense_data(self, expense) -> dict[str, Any]:
        return {
            "expense_name": expense.expense_name,
            "monthly_amount": expense.monthly_amount,
        }

    def _comp_set_data(self, comp) -> dict[str, Any]:
        return {
            "listing_url": comp.listing_url,
            "revenue": comp.revenue,
            "bedrooms": comp.bedrooms,
            "sleeps": comp.sleeps,
        }
