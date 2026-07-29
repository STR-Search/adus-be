from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.save_underwriting import (
    CompSetInput,
    OperatingExpenseInput,
    OptimizationItemInput,
    UnderwritingDetailsInput,
    UnderwritingTaxInput,
)


class UpdateUnderwritingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_id: int | None = None
    deal_status: DealStatus | None = None
    analyst_id: int | None = None
    approver_id: int | None = None
    deal_added: datetime | None = None
    deal_submitted: datetime | None = None
    deal_approved: datetime | None = None
    property_pending: bool = False
    property_address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    days_on_market: int | None = None
    sleep_capacity: int | None = None
    purchase_price: Decimal | None = None
    total_oop: Decimal | None = None
    prr: Decimal | None = None
    budget_to_pp: Decimal | None = None
    low_gross_revenue: Decimal | None = None
    mid_gross_revenue: Decimal | None = None
    high_gross_revenue: Decimal | None = None
    l_cash_on_cash: Decimal | None = None
    m_cash_on_cash: Decimal | None = None
    h_cash_on_cash: Decimal | None = None
    turnkey: bool = False
    furnished: bool = False
    luxury: bool = False
    tax_efficient: bool = False
    new_construction: bool = False
    existing_airbnb: bool = False
    arv: bool = False
    high_cash_on_cash: bool = False
    low_cash_on_cash: bool = False
    add_inground_pool: bool = False
    renovation_level: int | None = None
    deal_complexity: int | None = None
    waterfront: bool = False
    remote: bool = False
    can_support_cohost: bool = False
    market_type: list[str] | None = None
    execution_type: str | None = None
    seasonality: list[str] | None = None
    regulatory_clarity: str | None = None
    offer_competitiveness: str | None = None
    core_value_driver: list[str] | None = None
    cash_flow_quality: str | None = None
    view_quality: str | None = None
    pool_type: str | None = None
    primary_guest_avatar: str | None = None
    listing_url: str | None = None
    loom_vid: str | None = None
    video_walkthrough: str | None = None
    survey: str | None = None
    note: str | None = None
    deal_benefits: str | None = None
    property_uniqueness: str | None = None
    deal_score: int | None = Field(default=None, ge=1, le=100)

    details: UnderwritingDetailsInput | None = None
    taxes: UnderwritingTaxInput | None = None
    optimization_list: list[OptimizationItemInput] = Field(default_factory=list)
    operating_expenses: list[OperatingExpenseInput] = Field(default_factory=list)
    comp_set: list[CompSetInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_collections_with_purchase_details(self):
        """Guard against recalculating economics from empty default lists.

        The update path calculates from the request payload only (stored rows
        are never merged in), so sending ``details.purchase_details`` without
        the collections would compute OOP/CoC as if the underwriting had no
        optimization items or operating expenses — while the stored rows are
        silently preserved. Require both keys to be explicit (empty lists are
        fine: that's a deliberate "there are none").
        """
        if self.details is None or self.details.purchase_details is None:
            return self
        missing = [
            field
            for field in ("optimization_list", "operating_expenses")
            if field not in self.model_fields_set
        ]
        if missing:
            raise ValueError(
                f"{' and '.join(missing)} must be sent explicitly when "
                "details.purchase_details is provided; otherwise calculations "
                "would run against empty collections while stored rows are "
                "preserved"
            )
        return self


class UpdateUnderwritingResult(BaseModel):
    underwriting_id: int
