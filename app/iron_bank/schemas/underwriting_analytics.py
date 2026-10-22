from pydantic import BaseModel


class DealStatusCount(BaseModel):
    # ``None`` key = underwritings with no deal_status set.
    key: str | None
    label: str
    count: int


class DealStatusBreakdown(BaseModel):
    total: int
    statuses: list[DealStatusCount]
