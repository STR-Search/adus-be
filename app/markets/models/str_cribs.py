from decimal import Decimal

from sqlalchemy import Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StrCribsFeeDetails(Base):
    __tablename__ = "str_cribs_fee_details"
    __table_args__ = {"schema": "markets"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Inclusive upper bound (sqft) of the fee tier. The open-ended top tier
    # uses a max-int32 sentinel so a `sqft >= :area ORDER BY sqft LIMIT 1`
    # lookup always resolves to a row.
    sqft: Mapped[int | None] = mapped_column(Integer)
    fee: Mapped[Decimal | None] = mapped_column(Numeric)
