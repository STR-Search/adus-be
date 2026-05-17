from decimal import Decimal
from pydantic import BaseModel


class OptimizationItemBase(BaseModel):
    underwriting_id: int
    category: str | None = None
    amount: Decimal | None = None

class OptimizationItemCreate(OptimizationItemBase):
    pass

class OptimizationItemRead(OptimizationItemBase):
    id: int
    model_config = {"from_attributes": True}
