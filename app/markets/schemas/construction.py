from decimal import Decimal

from pydantic import BaseModel

from .common import BaseResponse


class ConstructionCostsAmenitiesSchema(BaseResponse):
    id: int
    location: str | None = None
    amenity_name: str | None = None
    price_tier_1: Decimal | None = None
    price_tier_2: Decimal | None = None
    price_tier_3: Decimal | None = None
    notes: str | None = None


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
