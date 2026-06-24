from decimal import Decimal

from app.iron_bank.enums import DealStatus
from app.iron_bank.services.non_automated_underwriting_payload_builder import (
    NonAutomatedUnderwritingPayloadBuilder,
)

REQUEST_URL = (
    "https://www.zillow.com/homedetails/"
    "727-N-Pine-St-San-Antonio-TX-78202/26110417_zpid/"
)


def _zillow_property(**overrides):
    base = {
        "id": "26110417",
        "url": "https://www.zillow.com/homedetails/mapped",
        "thumbnail": "https://photos.zillowstatic.com/a-d_d.jpg",
        "price": 389000.0,
        "address": "727 N Pine St, San Antonio, TX 78202",
        "bedrooms": 5,
        "bathrooms": 4.0,
        "area": 4608,
        "original_photos": [{"caption": ""}],
        "lot_size_sqft": 10698.0,
    }
    base.update(overrides)
    return base


def test_build_from_zillow_property_sets_non_automated_core_fields():
    builder = NonAutomatedUnderwritingPayloadBuilder()

    payload = builder.build_from_zillow_property(
        listing_url=REQUEST_URL,
        zillow_property=_zillow_property(),
    )

    assert payload.is_automated is False
    # listing_url is the request URL, not the mapped url on the property
    assert payload.listing_url == REQUEST_URL
    # zpid stays null on the column (FK to scheduled_listings); it's preserved
    # only inside details.zillow_property
    assert payload.zpid is None
    assert payload.details.zillow_property.id == "26110417"
    assert payload.property_address == "727 N Pine St, San Antonio, TX 78202"
    assert payload.market_id is None
    assert payload.operating_expenses == []
    assert payload.deal_status == DealStatus.TEMPLATE_GENERATED
    assert payload.purchase_price == Decimal("389000.0")


def test_build_from_zillow_property_seeds_default_financing_and_taxes():
    builder = NonAutomatedUnderwritingPayloadBuilder()

    payload = builder.build_from_zillow_property(
        listing_url=REQUEST_URL,
        zillow_property=_zillow_property(),
    )

    purchase_details = payload.details.purchase_details
    assert purchase_details.purchase_price == Decimal("389000.0")
    assert purchase_details.down_payment_pct == Decimal("0.1")
    assert purchase_details.interest_rate == Decimal("0.07")
    assert purchase_details.mortgage_years == 30
    assert purchase_details.closing_costs_pct == Decimal("0.03")

    assert payload.taxes.land_assumptions_pct == Decimal("0.2")
    assert payload.taxes.sla_multiplier_pct == Decimal("0.36")
    assert payload.taxes.bonus_amount_pct == Decimal("1")
    assert payload.taxes.tax_rate_pct == Decimal("0.37")


def test_build_from_zillow_property_stores_zillow_data_on_details():
    builder = NonAutomatedUnderwritingPayloadBuilder()

    payload = builder.build_from_zillow_property(
        listing_url=REQUEST_URL,
        zillow_property=_zillow_property(),
    )

    stored = payload.details.zillow_property
    assert stored.id == "26110417"
    assert stored.bedrooms == 5
    assert stored.lot_size_sqft == Decimal("10698.0")


def test_build_from_zillow_property_without_price_skips_purchase_and_taxes():
    builder = NonAutomatedUnderwritingPayloadBuilder()

    payload = builder.build_from_zillow_property(
        listing_url=REQUEST_URL,
        zillow_property=_zillow_property(price=None),
    )

    assert payload.purchase_price is None
    assert payload.details.purchase_details is None
    assert payload.taxes is None
    # zillow data is still stored even without a price
    assert payload.details.zillow_property.id == "26110417"
