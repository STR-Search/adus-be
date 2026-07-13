from datetime import datetime

from datetime import datetime

from sqlalchemy import DateTime, Index, DateTime, Integer, String, text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketKeysMaster(Base):
    __tablename__ = "market_keys_master"
    __table_args__ = (
        # Slug uniqueness only among active (non-soft-deleted) rows.
        Index(
            "uq_market_keys_master_market_slug_active",
            "market_slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "markets"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_slug: Mapped[str] = mapped_column(String, nullable=False)
    market_name: Mapped[str | None] = mapped_column(String)
    market_name_current: Mapped[str | None] = mapped_column(String)
    market_status: Mapped[str | None] = mapped_column(String)
    analyst_owner: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    map_config: Mapped[dict | None] = mapped_column(JSONB)
    filters: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    # updated_at is stamped on INSERT by the default and kept fresh on UPDATE by a
    # DB trigger (see migration) — the ORM does not maintain it.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
