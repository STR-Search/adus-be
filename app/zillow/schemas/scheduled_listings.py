from pydantic import BaseModel, ConfigDict


class ListingSummaryByMarket(BaseModel):
    cities: list[str]
    states: list[str]
    beds: list[int]

    model_config = ConfigDict(from_attributes=True)


class ScheduledListingResult(BaseModel):
    zpid: str
    detail_url: str
    address: str | None
    address_city: str
    address_state: str
    beds: int

    model_config = ConfigDict(from_attributes=True)


class PaginatedScheduledListings(BaseModel):
    items: list[ScheduledListingResult]
    total: int
    pages: int
