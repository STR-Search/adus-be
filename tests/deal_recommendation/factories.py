"""Shared test builders for deal_recommendation tests."""

from datetime import datetime
from decimal import Decimal

from app.iron_bank.services.deal_catalog_service import CatalogDeal


def make_deal(id: int, **overrides) -> CatalogDeal:
    fields = dict(
        id=id,
        property_address=f"{id} Main St, Largo, FL 33770",
        street=f"{id} Main St",
        city="Largo",
        state="FL",
        bedrooms=3,
        bathrooms=Decimal("2"),
        market_id=1,
        deal_status="present_to_clients",
        deal_approved=None,
        purchase_price=Decimal("500000"),
        total_oop=Decimal("200000"),
        l_cash_on_cash=Decimal("0.05"),
        m_cash_on_cash=Decimal("0.08"),
        h_cash_on_cash=Decimal("0.10"),
        y1_coc_incl_tax_savings_mid=Decimal("0.40"),
        tax_savings=Decimal("80000"),
        mid_gross_revenue=Decimal("60000"),
        down_payment_pct=Decimal("0.1"),
        interest_rate=Decimal("0.07"),
        boolean_tags={"turnkey": False},
        category_tags={},
    )
    fields.update(overrides)
    return CatalogDeal(**fields)


def approved(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day)
