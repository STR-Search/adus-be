from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .common import BaseResponse


class AmenityRefSchema(BaseResponse):
    """A construction_costs_amenities row referenced from a market's amenity lists."""

    id: int
    amenity_name: str | None = None


class RealtorRefSchema(BaseResponse):
    """A realtors row referenced from a market's realtor list."""

    id: int
    name: str | None = None
    email: str | None = None


class MarketKeysMasterSchema(BaseResponse):
    id: int
    market_slug: str | None = None
    market_name: str | None = None
    market_name_current: str | None = None
    market_status: str | None = None
    analyst_owner: str | None = None
    map_config: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None
    must_have_amenities: list[AmenityRefSchema] | None = None
    nice_to_have_amenities: list[AmenityRefSchema] | None = None
    realtors: list[RealtorRefSchema] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MarketCreateSchema(BaseModel):
    market_slug: str
    market_name: str | None = None
    market_name_current: str | None = None
    market_status: str | None = None
    analyst_owner: str | None = None
    map_config: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None
    must_have_amenities: list[int] | None = None
    nice_to_have_amenities: list[int] | None = None
    realtor_ids: list[int] | None = None


class MarketUpdateSchema(BaseModel):
    market_status: str | None = None
    analyst_owner: str | None = None
    map_config: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None
    must_have_amenities: list[int] | None = None
    nice_to_have_amenities: list[int] | None = None
    realtor_ids: list[int] | None = None


class MarketSummarySchema(BaseResponse):
    id: int
    market_slug: str | None = None
    market_name: str | None = None
