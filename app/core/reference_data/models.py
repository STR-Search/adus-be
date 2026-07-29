from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EnumOption(Base):
    """A single reference-data option shared across domains.

    Tag columns on domain tables store the ``key`` (a stable slug); the
    human-readable ``label`` lives here only and can be edited in one place.
    ``domain`` namespaces ``set_code`` so two domains can each own a set with
    the same code without colliding.
    """

    __tablename__ = "enum_options"
    __table_args__ = (
        UniqueConstraint(
            "domain", "set_code", "key", name="uq_enum_options_domain_set_key"
        ),
        {"schema": "reference"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    set_code: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # ``metadata`` is reserved by SQLAlchemy's Declarative API, so the attribute
    # is named ``metadata_json`` while the column stays ``metadata``.
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
