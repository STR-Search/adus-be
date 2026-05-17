from sqlalchemy import Column, Integer, String, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class OptimizationItem(Base):
    __tablename__ = "optimization_items"
    __table_args__ = {"schema": "iron_bank"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    underwriting_id = Column(
        Integer,
        ForeignKey("iron_bank.underwritings.id", ondelete="CASCADE"),
        nullable=False
    )

    category = Column(String(255), nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)

    underwriting = relationship("Underwriting", back_populates="optimization_items")


class UWOperatingExpense(Base):
    __tablename__ = "uw_operating_expenses"
    __table_args__ = {"schema": "iron_bank"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    underwriting_id = Column(
        Integer,
        ForeignKey("iron_bank.underwritings.id", ondelete="CASCADE"),
        nullable=False
    )

    expense_name = Column(String(255), nullable=True)
    monthly_amount = Column(Numeric(12, 2), nullable=True)

    underwriting = relationship("Underwriting", back_populates="operating_expenses")


class CompSet(Base):
    __tablename__ = "comp_set"
    __table_args__ = {"schema": "iron_bank"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    underwriting_id = Column(
        Integer,
        ForeignKey("iron_bank.underwritings.id", ondelete="CASCADE"),
        nullable=False
    )

    listing_url = Column(Text, nullable=True)
    revenue = Column(Numeric(12, 2), nullable=True)
    bedrooms = Column(Integer, nullable=True)
    sleeps = Column(Integer, nullable=True)

    underwriting = relationship("Underwriting", back_populates="comp_set")
