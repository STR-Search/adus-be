from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.save_underwriting import (
    CompSetInput,
    OperatingExpenseInput,
    OptimizationItemInput,
    UnderwritingDetailsInput,
    UnderwritingTaxInput,
)
from app.iron_bank.schemas.underwriting import (
    CoreValueDriver,
    ExecutionType,
    MarketType,
    OfferCompetitiveness,
    PoolType,
    PrimaryGuestAvatar,
    RegularityClarity,
    Seasonality,
    ViewQuality,
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
    market_type: MarketType | None = None
    execution_type: ExecutionType | None = None
    seasonality: Seasonality | None = None
    regulatory_clarity: RegularityClarity | None = None
    offer_competitiveness: OfferCompetitiveness | None = None
    core_value_driver: CoreValueDriver | None = None
    cash_flow_quality: str | None = None
    view_quality: ViewQuality | None = None
    pool_type: PoolType | None = None
    primary_guest_avatar: PrimaryGuestAvatar | None = None
    listing_url: str | None = None
    loom_vid: str | None = None
    video_walkthrough: str | None = None
    survey: str | None = None
    note: str | None = None
    deal_benefits: str | None = None
    property_uniqueness: str | None = None

    details: UnderwritingDetailsInput | None = None
    taxes: UnderwritingTaxInput | None = None
    optimization_list: list[OptimizationItemInput] = Field(default_factory=list)
    operating_expenses: list[OperatingExpenseInput] = Field(default_factory=list)
    comp_set: list[CompSetInput] = Field(default_factory=list)


class UpdateUnderwritingResult(BaseModel):
    underwriting_id: int
