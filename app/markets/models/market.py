from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketKeysMaster(Base):
    __tablename__ = "market_keys_master"
    __table_args__ = {"schema": "markets"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    market_name: Mapped[str | None] = mapped_column(String)
    market_name_current: Mapped[str | None] = mapped_column(String)
    market_status: Mapped[str | None] = mapped_column(String)
    analyst_owner: Mapped[str | None] = mapped_column(String)
