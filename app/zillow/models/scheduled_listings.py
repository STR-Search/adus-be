from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.zillow.models.scheduled_presets import ScheduledPreset


class ScheduledListing(Base):
    __tablename__ = "scheduled_listings"
    __table_args__ = {"schema": "zillow", "extend_existing": True}

    zpid: Mapped[str] = mapped_column(Text, primary_key=True)
    preset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zillow.scheduled_presets.id"), nullable=False
    )
    img_src: Mapped[str | None] = mapped_column(Text)
    detail_url: Mapped[str | None] = mapped_column(Text)
    price: Mapped[str | None] = mapped_column(Text)
    unformatted_price: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    address_street: Mapped[str | None] = mapped_column(Text)
    address_city: Mapped[str | None] = mapped_column(Text)
    address_state: Mapped[str | None] = mapped_column(Text)
    address_zipcode: Mapped[str | None] = mapped_column(Text)
    beds: Mapped[int | None] = mapped_column(Integer)
    baths: Mapped[float | None] = mapped_column(Float)
    area: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    home_type: Mapped[str | None] = mapped_column(Text)
    home_status: Mapped[str | None] = mapped_column(Text)
    time_on_zillow: Mapped[str | None] = mapped_column(Text)
    flex_text: Mapped[str | None] = mapped_column(Text)
    keep_updated: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    remove_listing: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    passes_preset_filters: Mapped[bool | None] = mapped_column(Boolean)

    preset: Mapped[ScheduledPreset] = relationship(
        "ScheduledPreset", back_populates="listings"
    )
