from enum import Enum
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel

from app.iron_bank.enums import DealStatus


class MarketType(str, Enum):
    mountain = "Mountain"
    beach = "Beach"
    urban = "Urban"


class ExecutionType(str, Enum):
    turnkey = "Turnkey"


class Seasonality(str, Enum):
    year_round = "Year Round"


class RegularityClarity(str, Enum):
    clear = "Clear"


class OfferCompetitiveness(str, Enum):
    moderate = "Moderate"


class CoreValueDriver(str, Enum):
    cash_flow = "Cash Flow"


class ViewQuality(str, Enum):
    excellent = "Excellent"


class PoolType(str, Enum):
    none = "None"
    inground = "Inground"


class PrimaryGuestAvatar(str, Enum):
    families = "Families"


class UnderwritingBase(BaseModel):
    zpid: str | None = None
    market_id: int | None = None
    analyst_id: int | None = None
    approver_id: int | None = None
    deal_status: DealStatus | None = None
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


class UnderwritingCreate(UnderwritingBase):
    pass


class UnderwritingRead(UnderwritingBase):
    id: int
    display_id: str | None = None  # e.g. "UW-001" — generated at API layer
    optimization_total: Decimal | None = None
    operating_expense_total: Decimal | None = None

    model_config = {"from_attributes": True}
