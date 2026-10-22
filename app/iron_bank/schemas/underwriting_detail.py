from typing import Any
from pydantic import BaseModel

from app.iron_bank.schemas.get_underwriting import ProjectLoan


class UnderwritingDetailBase(BaseModel):
    underwriting_id: int
    purchase_details: dict[str, Any] | None = None
    y1_coc_incl_tax_savings: dict[str, Any] | None = None
    forecasted_revenue: dict[str, Any] | None = None
    cleaning_cost: dict[str, Any] | None = None
    property_taxes: dict[str, Any] | None = None
    opex_project_loan: ProjectLoan | None = None
    analyst_notes: str | None = None
    construction_and_design_notes: str | None = None


class UnderwritingDetailCreate(UnderwritingDetailBase):
    pass


class UnderwritingDetailRead(UnderwritingDetailBase):
    id: int
    model_config = {"from_attributes": True}
