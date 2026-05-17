from decimal import Decimal
from pydantic import BaseModel


class UWOperatingExpenseBase(BaseModel):
    underwriting_id: int
    expense_name: str | None = None
    monthly_amount: Decimal | None = None

class UWOperatingExpenseCreate(UWOperatingExpenseBase):
    pass

class UWOperatingExpenseRead(UWOperatingExpenseBase):
    id: int
    model_config = {"from_attributes": True}
