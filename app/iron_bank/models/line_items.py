from sqlalchemy import Column, Integer, String, Numeric, Text, ForeignKey, select, func
from sqlalchemy.orm import relationship, column_property
from app.core.database import Base


class UnderwritingOptimizationItem(Base):
    __tablename__ = "uw_optimization_items"
    __table_args__ = {"schema": "iron_bank"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    underwriting_id = Column(
        Integer,
        ForeignKey("iron_bank.underwritings.id", ondelete="CASCADE"),
        nullable=False
    )

    category = Column(String(255), nullable=True)
    total_price = Column(Numeric(12, 2), nullable=True)
    metric = Column(Text, nullable=True)
    base_price = Column(Numeric(12, 2), nullable=True)
    spec = Column(Text, nullable=True)
    tier = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=True)

    underwriting = relationship("Underwriting", back_populates="optimization_items")


class UnderwritingOperatingExpense(Base):
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
    sort_order = Column(Integer, nullable=True)

    underwriting = relationship("Underwriting", back_populates="operating_expenses")


class UnderwritingCompSet(Base):
    __tablename__ = "uw_comp_sets"
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
    sort_order = Column(Integer, nullable=True)

    underwriting = relationship("Underwriting", back_populates="comp_set")


from app.iron_bank.models.underwriting import Underwriting  # noqa: E402

Underwriting.optimization_total = column_property(
    select(func.sum(UnderwritingOptimizationItem.total_price))
    .where(UnderwritingOptimizationItem.underwriting_id == Underwriting.id)
    .correlate_except(UnderwritingOptimizationItem)
    .scalar_subquery()
)

Underwriting.operating_expense_total = column_property(
    select(func.sum(UnderwritingOperatingExpense.monthly_amount))
    .where(UnderwritingOperatingExpense.underwriting_id == Underwriting.id)
    .correlate_except(UnderwritingOperatingExpense)
    .scalar_subquery()
)
