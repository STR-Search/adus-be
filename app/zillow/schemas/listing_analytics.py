from pydantic import BaseModel


class HomeStatusCount(BaseModel):
    # Raw Zillow ``home_status`` (e.g. FOR_SALE, PENDING); ``None`` = not yet known.
    home_status: str | None
    count: int


class HomeStatusBreakdown(BaseModel):
    total: int
    statuses: list[HomeStatusCount]
