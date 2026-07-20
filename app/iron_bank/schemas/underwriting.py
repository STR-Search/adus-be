from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, computed_field

from app.iron_bank.enums import DealStatus
from app.iron_bank.services.deal_status_service import STATUS_OPTIONS

_STATUS_LABEL: dict[str, str] = {s.value: label for s, label, _ in STATUS_OPTIONS}

# The categorical "deal tag" columns backed by the shared reference-data system.
# Each name is both the underwriting field and the reference ``set_code``; values
# are stored as slugs and validated/enriched against ``domain = "iron_bank"``.
#
# Multi-select tags store a list of slugs (``text[]`` column, ``list[str]``
# field); single-select tags store one slug (``varchar`` column, ``str`` field).
MULTI_SELECT_TAG_FIELDS: tuple[str, ...] = (
    "market_type",
    "seasonality",
    "core_value_driver",
)
SINGLE_SELECT_TAG_FIELDS: tuple[str, ...] = (
    "execution_type",
    "regulatory_clarity",
    "offer_competitiveness",
    "cash_flow_quality",
    "view_quality",
    "pool_type",
    "primary_guest_avatar",
)
REFERENCE_TAG_FIELDS: tuple[str, ...] = (
    *MULTI_SELECT_TAG_FIELDS,
    *SINGLE_SELECT_TAG_FIELDS,
)


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


class UnderwritingCreate(UnderwritingBase):
    pass


class DealStatusLabelMixin(BaseModel):
    """Adds a translated ``deal_status_label`` derived from ``deal_status``."""

    @computed_field
    @property
    def deal_status_label(self) -> str | None:
        deal_status: DealStatus | None = getattr(self, "deal_status", None)
        if deal_status is None:
            return None
        return _STATUS_LABEL.get(deal_status.value)


class UnderwritingRead(UnderwritingBase, DealStatusLabelMixin):
    id: int
    display_id: str | None = None  # e.g. "UW-001" — generated at API layer
    optimization_total: Decimal | None = None
    operating_expense_total: Decimal | None = None

    # Resolved reference-data labels for each tag slug. Populated by the read
    # service from ``ReferenceDataService.get_label_map`` — NOT computed, since
    # labels live in the DB (reference.enum_options), not in code.
    market_type_label: list[str] | None = None
    execution_type_label: str | None = None
    seasonality_label: list[str] | None = None
    regulatory_clarity_label: str | None = None
    offer_competitiveness_label: str | None = None
    core_value_driver_label: list[str] | None = None
    cash_flow_quality_label: str | None = None
    view_quality_label: str | None = None
    pool_type_label: str | None = None
    primary_guest_avatar_label: str | None = None

    model_config = {"from_attributes": True}
