from decimal import Decimal
from pydantic import BaseModel


class UnderwritingTaxBase(BaseModel):
    underwriting_id: int
    land_assumptions_pct: Decimal | None = None
    sla_multiplier_pct: Decimal | None = None
    improvement_basis: Decimal | None = None
    estimated_short_life_assets: Decimal | None = None
    bonus_amount_pct: Decimal | None = None
    tax_rate_pct: Decimal | None = None
    y1_loss_from_depreciation: Decimal | None = None
    tax_savings: Decimal | None = None

class UnderwritingTaxCreate(UnderwritingTaxBase):
    pass

class UnderwritingTaxRead(UnderwritingTaxBase):
    id: int
    model_config = {"from_attributes": True}
