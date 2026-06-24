from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

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


class EditContextData(BaseModel):
    underwriting: GetUnderwritingResult
    contextual: EditContextualData


class GetUnderwritingEditContextResult(BaseModel):
    data: EditContextData
