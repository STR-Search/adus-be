from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.iron_bank.schemas.get_underwriting import (
    ConstructionAmenityOption,
    ConstructionRemodelingOption,
    ZillowProperty,
)
from app.iron_bank.schemas.uw_config import UwConfigSchema


class PreparedOpexCleaning(BaseModel):
    fee: Decimal | None = None
    num_of_turns: Decimal | None = None


class PreparedOpexRange(BaseModel):
    low: Decimal | None = None
    high: Decimal | None = None


class PreparedOpexRanged(BaseModel):
    pool_hot_tub: PreparedOpexRange = Field(default_factory=PreparedOpexRange)


class PreparedOpex(BaseModel):
    cleaning: PreparedOpexCleaning = Field(default_factory=PreparedOpexCleaning)
    ranged: PreparedOpexRanged = Field(default_factory=PreparedOpexRanged)
    absolute: dict[str, Any] = Field(default_factory=dict)


class PrepareUwDataResult(BaseModel):
    market_name: str | None = None
    market_id: int | None = None
    market_slug: str | None = None
    zillow_property: ZillowProperty
    opex: PreparedOpex
    construction_amenities: list[ConstructionAmenityOption]
    construction_remodeling: list[ConstructionRemodelingOption]
    config: UwConfigSchema
