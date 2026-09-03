from decimal import Decimal
from pydantic import BaseModel


class CompSetBase(BaseModel):
    underwriting_id: int
    listing_url: str | None = None
    revenue: Decimal | None = None
    bedrooms: int | None = None
    sleeps: int | None = None
    is_favourite: bool = False
    has_pool: bool = False
    has_hot_tub: bool = False
    has_sauna: bool = False
    has_mini_golf: bool = False
    has_game_room: bool = False
    has_pickleball: bool = False
    has_movie_theater: bool = False
    has_playground: bool = False
    has_waterfront: bool = False

class CompSetCreate(CompSetBase):
    pass

class CompSetRead(CompSetBase):
    id: int
    model_config = {"from_attributes": True}
