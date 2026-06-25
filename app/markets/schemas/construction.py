from decimal import Decimal

from pydantic import BaseModel, field_serializer

from .common import BaseResponse


def _serialize_plain_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


class ConstructionCostsAmenitiesSchema(BaseResponse):
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


class ConstructionCostsAmenitiesCreateSchema(BaseModel):
    location: str | None = None
    amenity_name: str | None = None
    price_tier_1: Decimal | None = None
    price_tier_2: Decimal | None = None
    price_tier_3: Decimal | None = None
    notes: str | None = None


class ConstructionCostsAmenitiesUpdateSchema(BaseModel):
    location: str | None = None
    amenity_name: str | None = None
    price_tier_1: Decimal | None = None
    price_tier_2: Decimal | None = None
    price_tier_3: Decimal | None = None
    notes: str | None = None


class ConstructionCostsRemodelingSchema(BaseResponse):
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


class ConstructionCostsRemodelingCreateSchema(BaseModel):
    location: str | None = None
    rehab_item: str | None = None
    metric: str | None = None
    price_tier_1: Decimal | None = None
    price_tier_2: Decimal | None = None
    price_tier_3: Decimal | None = None
    notes: str | None = None


class ConstructionCostsRemodelingUpdateSchema(BaseModel):
    location: str | None = None
    rehab_item: str | None = None
    metric: str | None = None
    price_tier_1: Decimal | None = None
    price_tier_2: Decimal | None = None
    price_tier_3: Decimal | None = None
    notes: str | None = None
