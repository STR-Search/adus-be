from pydantic import BaseModel


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
