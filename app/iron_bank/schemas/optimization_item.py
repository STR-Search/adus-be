from decimal import Decimal
from pydantic import BaseModel


class OptimizationItemBase(BaseModel):
    underwriting_id: int
    category: str | None = None
    total_price: Decimal | None = None
    metric: str | None = None
    base_price: Decimal | None = None
    spec: str | None = None
    tier: str | None = None

class OptimizationItemCreate(OptimizationItemBase):
    pass

class OptimizationItemRead(OptimizationItemBase):
    id: int
    model_config = {"from_attributes": True}
