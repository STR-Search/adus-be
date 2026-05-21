from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.zillow.models.scheduled_listings import ScheduledListing


class ScheduledPreset(Base):
    __tablename__ = "scheduled_presets"
    __table_args__ = {"schema": "zillow", "extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    search_url: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_type: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_daily_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_full_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cycle_length_days: Mapped[int | None] = mapped_column(Integer, server_default=text("14"))
    force_next_run_full: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    filter_template: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    market_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("markets.market_keys_master.id")
    )

    listings: Mapped[list[ScheduledListing]] = relationship(
        "ScheduledListing", back_populates="preset"
    )
