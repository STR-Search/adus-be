from pydantic import BaseModel

from .common import BaseResponse


class MarketKeysMasterSchema(BaseResponse):
    id: int
    market_slug: str | None = None
    market_name: str | None = None
    market_name_current: str | None = None
    market_status: str | None = None
    analyst_owner: str | None = None


class MarketCreateSchema(BaseModel):
    market_slug: str
    market_name: str | None = None
    market_name_current: str | None = None
    market_status: str | None = None
    analyst_owner: str | None = None


class MarketUpdateSchema(BaseModel):
    market_slug: str | None = None
    market_name: str | None = None
    market_name_current: str | None = None
    market_status: str | None = None
    analyst_owner: str | None = None


class MarketSummarySchema(BaseResponse):
    id: int
    market_slug: str | None = None
    market_name: str | None = None
