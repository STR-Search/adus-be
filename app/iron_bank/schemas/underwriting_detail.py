from typing import Any
from pydantic import BaseModel


class UnderwritingDetailBase(BaseModel):
    underwriting_id: int
    purchase_details: dict[str, Any] | None = None
    y1_coc_incl_tax_savings: dict[str, Any] | None = None
    forecasted_revenue: dict[str, Any] | None = None
    cleaning_cost: dict[str, Any] | None = None
    analyst_notes: str | None = None


class UnderwritingDetailCreate(UnderwritingDetailBase):
    pass


class UnderwritingDetailRead(UnderwritingDetailBase):
    id: int
    model_config = {"from_attributes": True}
