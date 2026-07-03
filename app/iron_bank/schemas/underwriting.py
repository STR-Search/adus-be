from enum import Enum
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, computed_field, field_validator

from app.iron_bank.enums import DealStatus
from app.iron_bank.services.deal_status_service import STATUS_OPTIONS

_STATUS_LABEL: dict[str, str] = {s.value: label for s, label, _ in STATUS_OPTIONS}


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
    # DealStatus keys for app rows; legacy sheet imports may carry a dynamic
    # "Previously Underwritten - <sheet status>" string instead.
    deal_status: DealStatus | str | None = None

    @field_validator("deal_status")
    @classmethod
    def check_deal_status(cls, value):
        if isinstance(value, str) and not isinstance(value, DealStatus):
            try:
                return DealStatus(value)
            except ValueError:
                if not value.startswith("Previously Underwritten - "):
                    raise ValueError(
                        "deal_status must be a DealStatus key or a "
                        "'Previously Underwritten - ...' legacy value"
                    )
        return value
    deal_added: datetime | None = None
    deal_submitted: datetime | None = None
    deal_approved: datetime | None = None
    property_pending: bool = False
    is_automated: bool | None = None
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
    deal_score: int | None = Field(default=None, ge=1, le=100)


class UnderwritingCreate(UnderwritingBase):
    pass


class DealStatusLabelMixin(BaseModel):
    """Adds a translated ``deal_status_label`` derived from ``deal_status``."""

    @computed_field
    @property
    def deal_status_label(self) -> str | None:
        deal_status: DealStatus | str | None = getattr(self, "deal_status", None)
        if deal_status is None:
            return None
        value = (
            deal_status.value
            if isinstance(deal_status, DealStatus)
            else deal_status
        )
        # Dynamic legacy statuses ("Previously Underwritten - ...") are already
        # display-formatted, so they fall through as their own label.
        return _STATUS_LABEL.get(value, value)


class UnderwritingRead(UnderwritingBase, DealStatusLabelMixin):
    id: int
    display_id: str | None = None  # e.g. "UW-001" — generated at API layer
    source: str | None = None  # 'adus' | 'legacy_sheet'
    sheet_number: int | None = None  # legacy Google Sheet tab/link number
    # Display names resolved from users.users at read time (not stored columns)
    analyst_name: str | None = None
    approver_name: str | None = None
    optimization_total: Decimal | None = None
    operating_expense_total: Decimal | None = None

    model_config = {"from_attributes": True}
