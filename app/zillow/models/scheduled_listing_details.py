from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.zillow.models.scheduled_listings import ScheduledListing
    from app.zillow.models.scheduled_presets import ScheduledPreset


class ScheduledListingDetail(Base):
    __tablename__ = "scheduled_listing_details"
    __table_args__ = {"schema": "zillow", "extend_existing": True}

    zpid: Mapped[str] = mapped_column(
        Text, ForeignKey("zillow.scheduled_listings.zpid"), primary_key=True
    )
    preset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zillow.scheduled_presets.id"), nullable=False
    )
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    home_status: Mapped[str | None] = mapped_column(Text)
    address: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    year_built: Mapped[int | None] = mapped_column(Integer)
    street_address: Mapped[str | None] = mapped_column(Text)
    zipcode: Mapped[str | None] = mapped_column(Text)
    home_type: Mapped[str | None] = mapped_column(Text)
    monthly_hoa_fee: Mapped[float | None] = mapped_column(Float)
    living_area: Mapped[int | None] = mapped_column(Integer)
    living_area_value: Mapped[float | None] = mapped_column(Float)
    zestimate: Mapped[float | None] = mapped_column(Float)
    rent_zestimate: Mapped[float | None] = mapped_column(Float)
    schools: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tax_history: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    price_history: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    broker_name: Mapped[str | None] = mapped_column(Text)
    lot_size_sqft: Mapped[float | None] = mapped_column(Float)
    lot_size_acre: Mapped[float | None] = mapped_column(Float)
    original_photos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    photo_count: Mapped[int | None] = mapped_column(Integer)
    mortgage_rates: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    price_change: Mapped[float | None] = mapped_column(Float)
    price_change_date: Mapped[date | None] = mapped_column(Date)
    last_sold_price: Mapped[float | None] = mapped_column(Float)
    reso_facts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    home_insights: Mapped[str | None] = mapped_column(Text)
    view: Mapped[str | None] = mapped_column(Text)
    sewer: Mapped[str | None] = mapped_column(Text)
    cooling: Mapped[str | None] = mapped_column(Text)
    heating: Mapped[str | None] = mapped_column(Text)
    furnished: Mapped[bool | None] = mapped_column(Boolean)
    parking_capacity: Mapped[float | None] = mapped_column(Float)
    has_garage: Mapped[bool | None] = mapped_column(Boolean)
    fencing: Mapped[str | None] = mapped_column(Text)
    flooring: Mapped[str | None] = mapped_column(Text)
    pool_features: Mapped[str | None] = mapped_column(Text)
    agent_name: Mapped[str | None] = mapped_column(Text)
    agent_contact_info: Mapped[str | None] = mapped_column(Text)
    broker_contact_info: Mapped[str | None] = mapped_column(Text)
    mlsid: Mapped[str | None] = mapped_column(Text)
    mls_name: Mapped[str | None] = mapped_column(Text)
    neighborhood_name: Mapped[str | None] = mapped_column(Text)
    parcel_id: Mapped[str | None] = mapped_column(Text)
    tax_assessed_value: Mapped[float | None] = mapped_column(Float)
    last_updated_in_zillow: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    keep_updated: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    remove_listing: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )

    preset: Mapped["ScheduledPreset"] = relationship(
        "ScheduledPreset", back_populates="listing_details"
    )
    listing: Mapped["ScheduledListing"] = relationship(
        "ScheduledListing", back_populates="detail", uselist=False
    )
