from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Boolean,
    CheckConstraint,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Underwriting(Base):
    __tablename__ = "underwritings"
    __table_args__ = (
        CheckConstraint(
            "deal_status IS NULL OR deal_status IN ("
            "'template_generated', "
            "'analyst_started', "
            "'analyst_completed', "
            "'delete_zillow', "
            "'delete_deal', "
            "'maybe', "
            "'re_forecast_revenue', "
            "'awaiting_realtor_details', "
            "'present_to_clients', "
            "'client_under_contract', "
            "'training_deal'"
            ") OR deal_status LIKE 'Previously Underwritten - %'",
            name="ck_underwritings_deal_status",
        ),
        CheckConstraint(
            "deal_score IS NULL OR (deal_score >= 1 AND deal_score <= 100)",
            name="ck_underwritings_deal_score",
        ),
        Index(
            "uq_underwritings_sheet_number",
            "sheet_number",
            unique=True,
            postgresql_where=text("sheet_number IS NOT NULL"),
        ),
        {"schema": "iron_bank"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    zpid = Column(
        Text,
        ForeignKey("zillow.scheduled_listings.zpid", ondelete="SET NULL"),
        nullable=True,
    )

    market_id = Column(
        Integer,
        ForeignKey("markets.market_keys_master.id", ondelete="SET NULL"),
        nullable=True,
    )

    analyst_id = Column(Integer, nullable=True)
    approver_id = Column(Integer, nullable=True)

    # Enum keys for app rows; legacy backfilled rows may hold a dynamic
    # "Previously Underwritten - <sheet status>" string (see CHECK constraint).
    deal_status = Column(String(100), nullable=True)
    deal_added = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    deal_submitted = Column(DateTime(timezone=True), nullable=True)
    deal_approved = Column(DateTime(timezone=True), nullable=True)
    property_pending = Column(Boolean, default=False)
    is_automated = Column(Boolean, nullable=True)

    property_address = Column(String(255), nullable=True)
    street = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    days_on_market = Column(Integer, nullable=True)
    sleep_capacity = Column(Integer, nullable=True)

    purchase_price = Column(Numeric(12, 2), nullable=True)
    total_oop = Column(Numeric(12, 2), nullable=True)
    prr = Column(Numeric(6, 4), nullable=True)
    budget_to_pp = Column(Numeric(6, 4), nullable=True)
    low_gross_revenue = Column(Numeric(12, 2), nullable=True)
    mid_gross_revenue = Column(Numeric(12, 2), nullable=True)
    high_gross_revenue = Column(Numeric(12, 2), nullable=True)
    l_cash_on_cash = Column(Numeric(6, 4), nullable=True)
    m_cash_on_cash = Column(Numeric(6, 4), nullable=True)
    h_cash_on_cash = Column(Numeric(6, 4), nullable=True)

    turnkey = Column(Boolean, default=False)
    furnished = Column(Boolean, default=False)
    luxury = Column(Boolean, default=False)
    tax_efficient = Column(Boolean, default=False)
    new_construction = Column(Boolean, default=False)
    existing_airbnb = Column(Boolean, default=False)
    arv = Column(Boolean, default=False)
    high_cash_on_cash = Column(Boolean, default=False)
    low_cash_on_cash = Column(Boolean, default=False)
    add_inground_pool = Column(Boolean, default=False)
    renovation_level = Column(SmallInteger, nullable=True)
    deal_complexity = Column(SmallInteger, nullable=True)
    waterfront = Column(Boolean, default=False)
    remote = Column(Boolean, default=False)
    can_support_cohost = Column(Boolean, default=False)

    market_type = Column(String(50), nullable=True)
    execution_type = Column(String(50), nullable=True)
    seasonality = Column(String(50), nullable=True)
    regulatory_clarity = Column(String(50), nullable=True)
    offer_competitiveness = Column(String(50), nullable=True)
    core_value_driver = Column(String(50), nullable=True)
    cash_flow_quality = Column(String(50), nullable=True)
    view_quality = Column(String(50), nullable=True)
    pool_type = Column(String(50), nullable=True)
    primary_guest_avatar = Column(String(50), nullable=True)

    listing_url = Column(Text, nullable=True)
    loom_vid = Column(Text, nullable=True)
    video_walkthrough = Column(Text, nullable=True)
    survey = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    deal_benefits = Column(Text, nullable=True)
    property_uniqueness = Column(Text, nullable=True)

    deal_score = Column(Integer, nullable=True)

    # Provenance: 'adus' for rows created through the API/automation,
    # 'legacy_sheet' for rows backfilled from the underwriting Google Sheet.
    source = Column(String(50), nullable=True, server_default="adus")
    # The deal's tab/link number in the legacy Google Sheet (NULL for adus rows).
    sheet_number = Column(Integer, nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    listing = relationship("ScheduledListing", back_populates="underwritings")

    detail = relationship(
        "UnderwritingDetail", back_populates="underwriting", uselist=False
    )
    taxes = relationship(
        "UnderwritingTax", back_populates="underwriting", uselist=False
    )
    optimization_items = relationship(
        "UnderwritingOptimizationItem", back_populates="underwriting"
    )
    operating_expenses = relationship(
        "UnderwritingOperatingExpense", back_populates="underwriting"
    )
    comp_set = relationship("UnderwritingCompSet", back_populates="underwriting")


class UnderwritingDetail(Base):
    __tablename__ = "uw_details"
    __table_args__ = {"schema": "iron_bank"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    underwriting_id = Column(
        Integer,
        ForeignKey("iron_bank.underwritings.id", ondelete="CASCADE"),
        nullable=False,
    )

    purchase_details = Column(JSONB, nullable=True)
    y1_coc_incl_tax_savings = Column(JSONB, nullable=True)
    forecasted_revenue = Column(JSONB, nullable=True)
    cleaning_cost = Column(JSONB, nullable=True)
    property_taxes = Column(JSONB, nullable=True)
    zillow_property = Column(JSONB, nullable=True)
    analyst_notes = Column(Text, nullable=True)

    underwriting = relationship("Underwriting", back_populates="detail")


class UnderwritingTax(Base):
    __tablename__ = "uw_taxes"
    __table_args__ = {"schema": "iron_bank"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    underwriting_id = Column(
        Integer,
        ForeignKey("iron_bank.underwritings.id", ondelete="CASCADE"),
        nullable=False,
    )

    land_assumptions_pct = Column(Numeric(6, 4), nullable=True)
    sla_multiplier_pct = Column(Numeric(6, 4), nullable=True)
    improvement_basis = Column(Numeric(12, 2), nullable=True)
    estimated_short_life_assets = Column(Numeric(12, 2), nullable=True)
    bonus_amount_pct = Column(Numeric(6, 4), nullable=True)
    tax_rate_pct = Column(Numeric(6, 4), nullable=True)
    y1_loss_from_depreciation = Column(Numeric(12, 2), nullable=True)
    tax_savings = Column(Numeric(12, 2), nullable=True)

    underwriting = relationship("Underwriting", back_populates="taxes")
