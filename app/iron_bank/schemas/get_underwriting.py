from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.core.reference_data.schemas import ReferenceDataOption
from app.iron_bank.enums import DealStatus, SortOrder, UnderwritingSortBy
from app.iron_bank.schemas.underwriting import UnderwritingRead


def _serialize_plain_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


class ZillowProperty(BaseModel):
    id: str | None = None
    url: str | None = None
    thumbnail: str | None = None
    price: Decimal | None = None
    address: str | None = None
    bedrooms: int | None = None
    bathrooms: Decimal | None = None
    area: int | None = None
    original_photos: list | None = None
    lot_size_sqft: Decimal | None = None


class GetUnderwritingDetails(BaseModel):
    purchase_details: dict[str, Any] | None = None
    y1_coc_incl_tax_savings: dict[str, Any] | None = None
    forecasted_revenue: dict[str, Any] | None = None
    cleaning_cost: dict[str, Any] | None = None
    property_taxes: dict[str, Any] | None = None
    zillow_property: ZillowProperty | None = None
    analyst_notes: str | None = None


class GetUnderwritingTaxes(BaseModel):
    land_assumptions_pct: Decimal | None = None
    sla_multiplier_pct: Decimal | None = None
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
    notes: str | None = None


class GetUnderwritingOperatingExpense(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    expense_name: str | None = Field(default=None, alias="expense")
    monthly_amount: Decimal | None = Field(default=None, alias="monthly")


class GetUnderwritingCompSet(BaseModel):
    listing_url: str | None = None
    revenue: Decimal | None = None
    bedrooms: int | None = None
    sleeps: int | None = None


class GetUnderwritingResult(UnderwritingRead):
    details: GetUnderwritingDetails | None = None
    taxes: GetUnderwritingTaxes | None = None
    optimization_list: list[GetUnderwritingOptimizationItem] = Field(
        default_factory=list
    )
    operating_expenses: list[GetUnderwritingOperatingExpense] = Field(
        default_factory=list
    )
    comp_set: list[GetUnderwritingCompSet] = Field(default_factory=list)


class GetUnderwritingsQuery(BaseModel):
    """Query params for the underwritings list endpoint.

    Field names, types, and defaults mirror the previous inline ``Query(...)``
    params exactly, so the URL contract is unchanged. The added value is the
    cross-field ``min <= max`` validation that inline params can't express.
    """

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=20)
    zpid: str | None = None
    market_id: int | None = None
    deal_status: DealStatus | None = None
    analyst_id: int | None = None
    min_purchase_price: Decimal | None = Field(None, ge=0)
    max_purchase_price: Decimal | None = Field(None, ge=0)
    min_total_oop: Decimal | None = Field(None, ge=0)
    max_total_oop: Decimal | None = Field(None, ge=0)
    min_l_cash_on_cash: Decimal | None = None
    max_l_cash_on_cash: Decimal | None = None
    sort_by: UnderwritingSortBy = UnderwritingSortBy.ID
    sort_order: SortOrder = SortOrder.DESC

    @model_validator(mode="after")
    def check_ranges(self):
        if (
            self.min_purchase_price is not None
            and self.max_purchase_price is not None
            and self.min_purchase_price > self.max_purchase_price
        ):
            raise ValueError(
                "min_purchase_price must be less than or equal to max_purchase_price"
            )
        if (
            self.min_total_oop is not None
            and self.max_total_oop is not None
            and self.min_total_oop > self.max_total_oop
        ):
            raise ValueError(
                "min_total_oop must be less than or equal to max_total_oop"
            )
        if (
            self.min_l_cash_on_cash is not None
            and self.max_l_cash_on_cash is not None
            and self.min_l_cash_on_cash > self.max_l_cash_on_cash
        ):
            raise ValueError(
                "min_l_cash_on_cash must be less than or equal to max_l_cash_on_cash"
            )
        return self


class GetUnderwritingsResult(BaseModel):
    data: list[GetUnderwritingResult]
    total: int
    page: int
    page_size: int
    pages: int


class ConstructionAmenityOption(BaseModel):
    id: int
    location: str | None = None
    amenity_name: str | None = None
    price_tier_1: Decimal | None = None
    price_tier_2: Decimal | None = None
    price_tier_3: Decimal | None = None
    notes: str | None = None

    @field_serializer(
        "price_tier_1",
        "price_tier_2",
        "price_tier_3",
        when_used="json",
    )
    def serialize_price_tier(self, value: Decimal | None) -> str | None:
        return _serialize_plain_decimal(value)


class ConstructionRemodelingOption(BaseModel):
    id: int
    location: str | None = None
    rehab_item: str | None = None
    metric: str | None = None
    price_tier_1: Decimal | None = None
    price_tier_2: Decimal | None = None
    price_tier_3: Decimal | None = None
    notes: str | None = None

    @field_serializer(
        "price_tier_1",
        "price_tier_2",
        "price_tier_3",
        when_used="json",
    )
    def serialize_price_tier(self, value: Decimal | None) -> str | None:
        return _serialize_plain_decimal(value)


class StoredZillowProperty(ZillowProperty):
    """Persisted shape for non-automated underwritings.

    A permissive superset of ``ZillowProperty``: extra fields are tolerated so
    the stored JSON can grow without breaking validation, while the response
    contract stays the ``ZillowProperty`` subset.
    """

    model_config = ConfigDict(extra="allow")


class EditContextualData(BaseModel):
    construction_amenities: list[ConstructionAmenityOption] = Field(
        default_factory=list
    )
    construction_remodeling: list[ConstructionRemodelingOption] = Field(
        default_factory=list
    )
    # iron_bank domain reference data, grouped by set_code — the same payload
    # served by GET /reference-data?domain=iron_bank.
    deal_tag_options: dict[str, list[ReferenceDataOption]] = Field(
        default_factory=dict
    )


class EditContextData(BaseModel):
    underwriting: GetUnderwritingResult
    contextual: EditContextualData


class GetUnderwritingEditContextResult(BaseModel):
    data: EditContextData
