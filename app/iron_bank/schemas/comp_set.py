from decimal import Decimal
from pydantic import BaseModel


class CompSetBase(BaseModel):
    underwriting_id: int
    listing_url: str | None = None
    revenue: Decimal | None = None
    bedrooms: int | None = None
    sleeps: int | None = None
    is_favourite: bool = False
    # Amenity flags default to None, not False: an omitted flag is unknown, and
    # the column is nullable so it stays that way (see UnderwritingCompSet).
    has_pool: bool | None = None
    has_hot_tub: bool | None = None
    has_sauna: bool | None = None
    has_mini_golf: bool | None = None
    has_game_room: bool | None = None
    has_pickleball: bool | None = None
    has_movie_theater: bool | None = None
    has_playground: bool | None = None
    has_waterfront: bool | None = None

class CompSetCreate(CompSetBase):
    pass

class CompSetRead(CompSetBase):
    id: int
    model_config = {"from_attributes": True}
