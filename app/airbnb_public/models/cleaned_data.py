from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CleanedData(Base):
    __tablename__ = "cleaned_data"
    __table_args__ = {"schema": "public", "extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_run_execution_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("public.processing_executions.id"),
        nullable=False,
    )
    property_id: Mapped[str | None] = mapped_column(String(100))
    key_market: Mapped[str | None] = mapped_column(String(255))
    listing_title: Mapped[str | None] = mapped_column(Text)
    listing_url: Mapped[str | None] = mapped_column(Text)
    exclude_comp: Mapped[bool | None] = mapped_column(Boolean)
    include_comp: Mapped[bool | None] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    sleeps: Mapped[int | None] = mapped_column(Integer)
    bed_count: Mapped[int | None] = mapped_column(Integer)
    baths: Mapped[float | None] = mapped_column(Float)
    revenue_potential: Mapped[float | None] = mapped_column(Float)
    prev_revenue_potential: Mapped[float | None] = mapped_column(Float)
    revenue_potential_pct_change: Mapped[float | None] = mapped_column(Float)
    revenue_potential_percentile: Mapped[float | None] = mapped_column(Float)
    adr: Mapped[float | None] = mapped_column(Float)
    occupancy: Mapped[float | None] = mapped_column(Float)
    prev_data_date: Mapped[datetime | None] = mapped_column(DateTime)
    ratings: Mapped[float | None] = mapped_column(Float)
    reviews: Mapped[int | None] = mapped_column(Integer)
    review_count_stayed_with_kids: Mapped[int | None] = mapped_column(Integer)
    review_count_group_trip: Mapped[int | None] = mapped_column(Integer)
    review_count_stayed_with_a_pet: Mapped[int | None] = mapped_column(Integer)
    other_reviews: Mapped[int | None] = mapped_column(Integer)
    pct_stayed_with_kids: Mapped[float | None] = mapped_column(Float)
    pct_group_trip: Mapped[float | None] = mapped_column(Float)
    pct_stayed_with_a_pet: Mapped[float | None] = mapped_column(Float)
    pct_other_reviews: Mapped[float | None] = mapped_column(Float)
    city: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str | None] = mapped_column(String(255))
    superhost: Mapped[bool | None] = mapped_column(Boolean)
    lat: Mapped[float | None] = mapped_column(Float)
    long: Mapped[float | None] = mapped_column(Float)
    zipcode: Mapped[str | None] = mapped_column(String(20))
    min_stay: Mapped[int | None] = mapped_column(Integer)
    available_nights: Mapped[int | None] = mapped_column(Integer)
    cleaning_fee: Mapped[float | None] = mapped_column(Float)
    data_quality_category: Mapped[str | None] = mapped_column(String(50))
    quality_rating_reason: Mapped[str | None] = mapped_column(Text)
    all_reviews: Mapped[str | None] = mapped_column(Text)
    listing_status: Mapped[str | None] = mapped_column(String(50))
    has_hot_tub: Mapped[bool | None] = mapped_column(Boolean)
    has_pool: Mapped[bool | None] = mapped_column(Boolean)
    has_sauna: Mapped[bool | None] = mapped_column(Boolean)
    has_mini_golf: Mapped[bool | None] = mapped_column(Boolean)
    has_pickleball: Mapped[bool | None] = mapped_column(Boolean)
    has_game_room: Mapped[bool | None] = mapped_column(Boolean)
    has_movie_theater: Mapped[bool | None] = mapped_column(Boolean)
    has_golf_simulator: Mapped[bool | None] = mapped_column(Boolean)
    has_fire_pit: Mapped[bool | None] = mapped_column(Boolean)
    has_pool_table: Mapped[bool | None] = mapped_column(Boolean)
    has_gym: Mapped[bool | None] = mapped_column(Boolean)
    has_playground: Mapped[bool | None] = mapped_column(Boolean)
    has_outdoor_dining_area: Mapped[bool | None] = mapped_column(Boolean)
    has_waterfront: Mapped[bool | None] = mapped_column(Boolean)
    has_pool_heater: Mapped[bool | None] = mapped_column(Boolean)
    has_pack_n_play_travel_crib: Mapped[bool | None] = mapped_column(Boolean)
    has_crib: Mapped[bool | None] = mapped_column(Boolean)
    has_lake_access: Mapped[bool | None] = mapped_column(Boolean)
    is_guest_favorite: Mapped[bool | None] = mapped_column(Boolean)
    potential_revenue_rank: Mapped[int | None] = mapped_column(Integer)
    data_date: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=text("now()"))
    property_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'single-family home'::text"),
    )
