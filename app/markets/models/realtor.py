from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Realtor(Base):
    """An external realtor contact. Realtors are not users of this system —
    there is no auth or account behind a row; this is a lookup table so the
    same person can be referenced from many markets without duplicating their
    contact details."""

    __tablename__ = "realtors"
    __table_args__ = (
        # Email uniqueness is case-insensitive and enforced only among active
        # (non-soft-deleted) rows, so a deleted contact can be re-created.
        Index(
            "uq_realtors_email_active",
            func.lower(func.trim(text("email"))),
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND email IS NOT NULL"),
        ),
        {"schema": "markets"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    brokerage: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    # updated_at is stamped on INSERT by the default and kept fresh on UPDATE by a
    # DB trigger (see migration) — the ORM does not maintain it.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
