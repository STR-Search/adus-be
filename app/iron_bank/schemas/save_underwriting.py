from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.iron_bank.schemas.underwriting import UnderwritingBase

FractionalPercentage = Annotated[Decimal, Field(ge=0, le=1)]


class PurchaseDetailsInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    purchase_price: Decimal
    down_payment_pct: FractionalPercentage
    interest_rate: FractionalPercentage
    mortgage_years: int
    closing_costs_pct: FractionalPercentage


class ForecastedRevenueScenarioInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    forecasted_revenue: Decimal


class ForecastedRevenueScenariosInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: ForecastedRevenueScenarioInput
    mid: ForecastedRevenueScenarioInput
    high: ForecastedRevenueScenarioInput


class ForecastedRevenueInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    co_hosting_fee_pct: FractionalPercentage
    annual_re_appreciation_pct: FractionalPercentage
    scenarios: ForecastedRevenueScenariosInput


class UnderwritingDetailsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_details: PurchaseDetailsInput | None = None
    y1_coc_incl_tax_savings: dict[str, Any] | None = None
    forecasted_revenue: ForecastedRevenueInput | None = None
    cleaning_cost: dict[str, Any] | None = None
    analyst_notes: str | None = None


class UnderwritingTaxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    land_assumptions_pct: FractionalPercentage
    sla_multiplier_pct: FractionalPercentage
    improvement_basis: Decimal | None = None
    estimated_short_life_assets: Decimal | None = None
    bonus_amount_pct: FractionalPercentage
    tax_rate_pct: FractionalPercentage
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
                "analyst_id": 2,
                "approver_id": 1,
                "deal_status": "analyst_started",
                "deal_added": "2025-03-10T08:00:00Z",
                "deal_submitted": "2025-03-13T16:30:00Z",
                "deal_approved": "2025-03-14T10:22:00Z",
                "property_pending": False,
                "listing_url": "https://www.zillow.com/homedetails/123-pine-ridge-rd",
                "property_address": "123 Pine Ridge Rd",
                "street": "Pine Ridge Rd",
                "city": "Gatlinburg",
                "state": "TN",
                "days_on_market": 12,
                "sleep_capacity": 10,
                "purchase_price": 485000,
                "total_oop": 145000,
                "prr": 0.18,
                "budget_to_pp": 0.32,
                "low_gross_revenue": 72000,
                "mid_gross_revenue": 98000,
                "high_gross_revenue": 127000,
                "l_cash_on_cash": 0.11,
                "m_cash_on_cash": 0.17,
                "h_cash_on_cash": 0.24,
                "turnkey": True,
                "furnished": True,
                "luxury": False,
                "tax_efficient": True,
                "new_construction": False,
                "existing_airbnb": True,
                "arv": False,
                "high_cash_on_cash": False,
                "low_cash_on_cash": False,
                "add_inground_pool": False,
                "waterfront": False,
                "remote": False,
                "can_support_cohost": True,
                "renovation_level": 2,
                "deal_complexity": 3,
                "market_type": "Mountain",
                "execution_type": "Turnkey",
                "seasonality": "Year Round",
                "regulatory_clarity": "Clear",
                "offer_competitiveness": "Moderate",
                "core_value_driver": "Cash Flow",
                "cash_flow_quality": None,
                "view_quality": "Excellent",
                "pool_type": "None",
                "primary_guest_avatar": "Families",
                "loom_vid": "https://loom.com/share/abc123",
                "video_walkthrough": "https://youtube.com/watch?v=xwalk001",
                "survey": "https://typeform.com/survey/deal-001",
                "note": (
                    "Log cabin with hot tub already installed. "
                    "Seller motivated - estate sale."
                ),
                "deal_benefits": None,
                "property_uniqueness": None,
                "details": {
                    "purchase_details": {
                        "purchase_price": 485000,
                        "down_payment_pct": 0.10,
                        "interest_rate": 0.0675,
                        "mortgage_years": 30,
                        "closing_costs_pct": 0.03,
                    },
                    "forecasted_revenue": {
                        "co_hosting_fee_pct": 0,
                        "annual_re_appreciation_pct": 0.04,
                        "scenarios": {
                            "low": {"forecasted_revenue": 72000},
                            "mid": {"forecasted_revenue": 98000},
                            "high": {"forecasted_revenue": 127000},
                        },
                    },
                    "analyst_notes": "asdkasdaksdalsdlala",
                    "cleaning_cost": {
                        "cost_per_clean": 220,
                        "turns_per_month": 7,
                        "monthly_cleaning_cost": 1540,
                    },
                },
                "optimization_list": [
                    {
                        "category": "Flooring",
                        "total_price": 27000,
                        "metric": "sqft",
                        "base_price": 15,
                        "spec": "@$15/sqft x 1,800 sqft",
                        "tier": "Mid",
                    },
                    {
                        "category": "Interior Painting",
                        "total_price": 12000,
                        "metric": "sqft",
                        "base_price": 5,
                        "spec": "@$5/sqft x 2,400 sqft",
                        "tier": "Mid",
                    },
                    {
                        "category": "Exterior Painting",
                        "total_price": 13200,
                        "metric": "sqft",
                        "base_price": 6,
                        "spec": "@$6/sqft x 2,200 sqft",
                        "tier": "Mid",
                    },
                    {
                        "category": "Accent Wall Paint",
                        "total_price": 1800,
                        "metric": "number of",
                        "base_price": 600,
                        "spec": "@$600 x 3 walls",
                        "tier": "Mid",
                    },
                    {
                        "category": "Furniture / Decor / Essentials",
                        "total_price": 12000,
                        "metric": "flat",
                        "base_price": 12000,
                        "spec": "Full furnishing package - living, dining, all bedrooms",
                        "tier": "Mid",
                    },
                    {
                        "category": "Hot Tub Refurbishment",
                        "total_price": 3500,
                        "metric": "flat",
                        "base_price": 3500,
                        "spec": "Jets, cover, and chemical system replacement",
                        "tier": "Mid",
                    },
                    {
                        "category": "Outdoor Lighting & Fire Pit",
                        "total_price": 2200,
                        "metric": "flat",
                        "base_price": 2200,
                        "spec": "String lights + gas fire pit install",
                        "tier": "Mid",
                    },
                ],
                "operating_expenses": [
                    {"expense": "Internet", "monthly": 100},
                    {"expense": "Utilities", "monthly": 520},
                    {"expense": "Pest Control", "monthly": 50},
                    {"expense": "Pool/Hot Tub Maintenance", "monthly": 175},
                    {"expense": "Outdoor/Landscaping", "monthly": 150},
                    {"expense": "Software", "monthly": 50},
                    {"expense": "Household Supplies", "monthly": 180},
                ],
                "taxes": {
                    "land_assumptions_pct": 0.2,
                    "sla_multiplier_pct": 0.36,
                    "bonus_amount_pct": 1.0,
                    "tax_rate_pct": 0.37,
                },
                "comp_set": [
                    {
                        "listing_url": (
                            "https://www.airbnb.com/rooms/1140067927241599056"
                        ),
                        "revenue": 112400,
                        "bedrooms": 4,
                        "sleeps": 10,
                    },
                    {
                        "listing_url": (
                            "https://www.airbnb.com/rooms/843508020823884501"
                        ),
                        "revenue": 98700,
                        "bedrooms": 4,
                        "sleeps": 8,
                    },
                    {
                        "listing_url": (
                            "https://www.airbnb.com/rooms/1385147324053316626"
                        ),
                        "revenue": 87300,
                        "bedrooms": 3,
                        "sleeps": 8,
                    },
                    {
                        "listing_url": (
                            "https://www.airbnb.com/rooms/1263921128519313481"
                        ),
                        "revenue": 103200,
                        "bedrooms": 4,
                        "sleeps": 10,
                    },
                    {
                        "listing_url": "https://www.airbnb.com/rooms/41934636",
                        "revenue": 91500,
                        "bedrooms": 4,
                        "sleeps": 10,
                    },
                ],
            }
        },
    )

    details: UnderwritingDetailsInput | None = None
    taxes: UnderwritingTaxInput | None = None
    optimization_list: list[OptimizationItemInput] = Field(default_factory=list)
    operating_expenses: list[OperatingExpenseInput] = Field(default_factory=list)
    comp_set: list[CompSetInput] = Field(default_factory=list)


class SaveUnderwritingResult(BaseModel):
    underwriting_id: int
