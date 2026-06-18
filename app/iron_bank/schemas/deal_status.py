from pydantic import BaseModel, ConfigDict

from app.iron_bank.enums import DealStatus


class DealStatusOption(BaseModel):
    key: str
    label: str
    sort_order: int


class DealStatusOptionsResult(BaseModel):
    statuses: list[DealStatusOption]


class DealStatusTransitionsResult(BaseModel):
    current_status: str
    actor_role: str
    allowed_transitions: list[DealStatusOption]


class UpdateDealStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deal_status: DealStatus


class UpdateDealStatusResult(BaseModel):
    underwriting_id: int
    deal_status: DealStatus
