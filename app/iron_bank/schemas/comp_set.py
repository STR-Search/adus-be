from decimal import Decimal
from pydantic import BaseModel


class CompSetBase(BaseModel):
    underwriting_id: int
    listing_url: str | None = None
    revenue: Decimal | None = None
    bedrooms: int | None = None
    sleeps: int | None = None

class CompSetCreate(CompSetBase):
    pass

class CompSetRead(CompSetBase):
    id: int
    model_config = {"from_attributes": True}
