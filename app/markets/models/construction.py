from decimal import Decimal

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConstructionCostsAmenities(Base):
    __tablename__ = "construction_costs_amenities"
    __table_args__ = {"schema": "markets"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location: Mapped[str | None] = mapped_column(String)
    amenity_name: Mapped[str | None] = mapped_column(String)
    price_tier_1: Mapped[Decimal | None] = mapped_column(Numeric)
    price_tier_2: Mapped[Decimal | None] = mapped_column(Numeric)
    price_tier_3: Mapped[Decimal | None] = mapped_column(Numeric)
    notes: Mapped[str | None] = mapped_column(String)


class ConstructionCostsRemodeling(Base):
    __tablename__ = "construction_costs_remodeling"
    __table_args__ = {"schema": "markets"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location: Mapped[str | None] = mapped_column(String)
    rehab_item: Mapped[str | None] = mapped_column(String)
    metric: Mapped[str | None] = mapped_column(String)
    price_tier_1: Mapped[Decimal | None] = mapped_column(Numeric)
    price_tier_2: Mapped[Decimal | None] = mapped_column(Numeric)
    price_tier_3: Mapped[Decimal | None] = mapped_column(Numeric)
    notes: Mapped[str | None] = mapped_column(String)
