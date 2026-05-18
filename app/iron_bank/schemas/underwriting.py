from enum import Enum
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class MarketType(str, Enum):
    mountain = "Mountain"
    beach = "Beach"
    urban = "Urban"

class ExecutionType(str, Enum):
    turnkey = "Turnkey"

class PrimaryStrategy(str, Enum):
    short_term_rental = "Short-Term Rental"

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
    market_id: int | None = None
    analyst_id: int | None = None
    approver_id: int | None = None
    deal_status: str | None = None
    date_added: date | None = None
    approved_time: datetime | None = None
    property_pending: bool = False
    property_address: str | None = None
    city: str | None = None
    state: str | None = None
    days_on_market: int | None = None
    sleep_capacity: int | None = None
    purchase_price: Decimal | None = None
    cash_needed: Decimal | None = None
    all_in_cost: Decimal | None = None
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
    wow_factor: bool = False
    tax_efficient: bool = False
    new_build: bool = False
    new_construction: bool = False
    existing_airbnb: bool = False
    existing_airbnb_sold_furnished: bool = False
    arv: bool = False
    high_cash_on_cash: bool = False
    low_cash_on_cash: bool = False
    add_inground_pool: bool = False
    renovation_level: bool = False
    complex_deal: bool = False
    funky: bool = False
    remote: bool = False
    secluded: bool = False
    friendly_1031: bool = False
    can_support_cohost: bool = False
    market_type: MarketType | None = None
    execution_type: ExecutionType | None = None
    primary_strategy: PrimaryStrategy | None = None
    seasonality: Seasonality | None = None
    regulatory_clarity: RegularityClarity | None = None
    offer_competitiveness: OfferCompetitiveness | None = None
    core_value_driver: CoreValueDriver | None = None
    view_quality: ViewQuality | None = None
    pool_type: PoolType | None = None
    primary_guest_avatar: PrimaryGuestAvatar | None = None
    listing_url: str | None = None
    loom_vid: str | None = None
    video_walkthrough: str | None = None
    survey: str | None = None
    note: str | None = None

class UnderwritingCreate(UnderwritingBase):
    pass

class UnderwritingRead(UnderwritingBase):
    id: int
    display_id: str | None = None  # e.g. "UW-001" — generated at API layer
    optimization_total: Decimal | None = None
    operating_expense_total: Decimal | None = None

    model_config = {"from_attributes": True}


