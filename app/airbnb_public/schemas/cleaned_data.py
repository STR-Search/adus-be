from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CleanedDataSchema(BaseModel):
    id: int
    market_run_execution_id: int
    property_id: str | None = None
    key_market: str | None = None
    listing_title: str | None = None
    listing_url: str | None = None
    exclude_comp: bool | None = None
    include_comp: bool | None = None
    notes: str | None = None
    bedrooms: int | None = None
    sleeps: int | None = None
    bed_count: int | None = None
    baths: float | None = None
    revenue_potential: float | None = None
    prev_revenue_potential: float | None = None
    revenue_potential_pct_change: float | None = None
    revenue_potential_percentile: float | None = None
    adr: float | None = None
    occupancy: float | None = None
    prev_data_date: datetime | None = None
    ratings: float | None = None
    reviews: int | None = None
    review_count_stayed_with_kids: int | None = None
    review_count_group_trip: int | None = None
    review_count_stayed_with_a_pet: int | None = None
    other_reviews: int | None = None
    pct_stayed_with_kids: float | None = None
    pct_group_trip: float | None = None
    pct_stayed_with_a_pet: float | None = None
    pct_other_reviews: float | None = None
    city: str | None = None
    state: str | None = None
    superhost: bool | None = None
    lat: float | None = None
    long: float | None = None
    zipcode: str | None = None
    min_stay: int | None = None
    available_nights: int | None = None
    cleaning_fee: float | None = None
    data_quality_category: str | None = None
    quality_rating_reason: str | None = None
    all_reviews: str | None = None
    listing_status: str | None = None
    has_hot_tub: bool | None = None
    has_pool: bool | None = None
    has_sauna: bool | None = None
    has_mini_golf: bool | None = None
    has_pickleball: bool | None = None
    has_game_room: bool | None = None
    has_movie_theater: bool | None = None
    has_golf_simulator: bool | None = None
    has_fire_pit: bool | None = None
    has_pool_table: bool | None = None
    has_gym: bool | None = None
    has_playground: bool | None = None
    has_outdoor_dining_area: bool | None = None
    has_waterfront: bool | None = None
    has_pool_heater: bool | None = None
    has_pack_n_play_travel_crib: bool | None = None
    has_crib: bool | None = None
    has_lake_access: bool | None = None
    is_guest_favorite: bool | None = None
    potential_revenue_rank: int | None = None
    data_date: datetime | None = None
    created_at: datetime | None = None
    property_type: str

    model_config = ConfigDict(from_attributes=True)


class RevenuePotentialPercentiles(BaseModel):
    low: float
    mid: float
    high: float
