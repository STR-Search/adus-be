from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.iron_bank.schemas.underwriting import UnderwritingBase


class GetUnderwritingDetails(BaseModel):
    purchase_details: dict[str, Any] | None = None
    y1_coc_incl_tax_savings: dict[str, Any] | None = None
    forecasted_revenue: dict[str, Any] | None = None
    cleaning_cost: dict[str, Any] | None = None
    analyst_notes: str | None = None


class GetUnderwritingTaxes(BaseModel):
    land_assumptions_pct: Decimal | None = None
    improvement_basis: Decimal | None = None
    estimated_short_life_assets: Decimal | None = None
    bonus_amount_pct: Decimal | None = None
    tax_rate_pct: Decimal | None = None
    y1_loss_from_depreciation: Decimal | None = None
    tax_savings: Decimal | None = None


class GetUnderwritingOptimizationItem(BaseModel):
    category: str | None = None
    total_price: Decimal | None = None
    metric: str | None = None
    base_price: Decimal | None = None
    spec: str | None = None
    tier: str | None = None


class GetUnderwritingOperatingExpense(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    expense_name: str | None = Field(default=None, alias="expense")
    monthly_amount: Decimal | None = Field(default=None, alias="monthly")


class GetUnderwritingCompSet(BaseModel):
    listing_url: str | None = None
    revenue: Decimal | None = None
    bedrooms: int | None = None
    sleeps: int | None = None


class GetUnderwritingResult(UnderwritingBase):
    id: int
    uw_details: GetUnderwritingDetails | None = None
    taxes: GetUnderwritingTaxes | None = None
    optimization_list: list[GetUnderwritingOptimizationItem] = Field(
        default_factory=list
    )
    operating_expenses: list[GetUnderwritingOperatingExpense] = Field(
        default_factory=list
    )
    comp_set: list[GetUnderwritingCompSet] = Field(default_factory=list)
