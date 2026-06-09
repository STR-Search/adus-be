from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.iron_bank.schemas.underwriting import UnderwritingBase


class UnderwritingDetailsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_details: dict[str, Any] | None = None
    y1_coc_incl_tax_savings: dict[str, Any] | None = None
    forecasted_revenue: dict[str, Any] | None = None
    cleaning_cost: dict[str, Any] | None = None
    analyst_notes: str | None = None


class UnderwritingTaxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    land_assumptions_pct: Decimal | None = None
    improvement_basis: Decimal | None = None
    estimated_short_life_assets: Decimal | None = None
    bonus_amount_pct: Decimal | None = None
    tax_rate_pct: Decimal | None = None
    y1_loss_from_depreciation: Decimal | None = None
    tax_savings: Decimal | None = None


class OptimizationItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str | None = None
    total_price: Decimal | None = None
    metric: str | None = None
    base_price: Decimal | None = None
    spec: str | None = None
    tier: str | None = None


class OperatingExpenseInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    expense_name: str | None = Field(default=None, alias="expense")
    monthly_amount: Decimal | None = Field(default=None, alias="monthly")


class CompSetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_url: str | None = None
    revenue: Decimal | None = None
    bedrooms: int | None = None
    sleeps: int | None = None


class SaveUnderwritingPayload(UnderwritingBase):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "market_id": 3,
                "purchase_price": 485000,
                "uw_details": {
                    "purchase_details": {
                        "purchase_price": 485000,
                        "down_payment_pct": 10,
                        "interest_rate": 6.75,
                        "mortgage_years": 30,
                        "closing_costs_pct": 3,
                    },
                    "forecasted_revenue": {
                        "co_hosting_fee_pct": 0,
                        "annual_re_appreciation_pct": 4,
                        "scenarios": {
                            "low": {"forecasted_revenue": 72000},
                            "mid": {"forecasted_revenue": 98000},
                            "high": {"forecasted_revenue": 127000},
                        },
                    },
                    "cleaning_cost": {
                        "cost_per_clean": 220,
                        "turns_per_month": 7,
                        "monthly_cleaning_cost": 1540,
                    },
                    "analyst_notes": "Existing hot tub and cabin aesthetic.",
                },
                "taxes": {
                    "land_assumptions_pct": 0.20,
                    "bonus_amount_pct": 1.00,
                    "tax_rate_pct": 0.37,
                },
                "optimization_list": [],
                "operating_expenses": [],
                "comp_set": [],
            }
        },
    )

    uw_details: UnderwritingDetailsInput | None = None
    taxes: UnderwritingTaxInput | None = None
    optimization_list: list[OptimizationItemInput] = Field(default_factory=list)
    operating_expenses: list[OperatingExpenseInput] = Field(default_factory=list)
    comp_set: list[CompSetInput] = Field(default_factory=list)


class SaveUnderwritingResult(BaseModel):
    underwriting_id: int
