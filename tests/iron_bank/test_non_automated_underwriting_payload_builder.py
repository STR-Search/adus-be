from decimal import Decimal
from types import SimpleNamespace

from app.iron_bank.enums import DealStatus
from app.iron_bank.services.non_automated_underwriting_payload_builder import (
    NonAutomatedUnderwritingPayloadBuilder,
)
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService

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
        "street": "727 N Pine St",
        "city": "San Antonio",
        "state": "TX",
        "original_photos": [{"caption": ""}],
        "lot_size_sqft": 10698.0,
    }
    base.update(overrides)
    return base


class FakeSchema(SimpleNamespace):
    def model_dump(self):
        return dict(vars(self))


def _market_context(market_id=3, **overrides):
    """A realistic MarketContext, assembled the same way production does."""
    kwargs = dict(
        market=SimpleNamespace(
            market_name="Smoky Mountains",
            market_slug="smoky-mountains",
            must_have_amenities=[SimpleNamespace(id=1, amenity_name="Hot Tub")],
        ),
        market_id=market_id,
        opex_by_bedrooms=FakeSchema(
            id=1,
            market_id=market_id,
            market_slug="smoky-mountains",
            bedrooms=5,
            sqft=None,
            cleaning_fee=275,
            num_of_turns=38,
            pool_hot_tub_low=1200,
            pool_hot_tub_high=2400,
            furnishings_low=25000,
            furnishings_mid=40000,
            furnishings_high=60000,
            consolidated_shipping=18225,
            property_taxes=Decimal("0.012"),
            # land_value and appreciation live on the bedrooms row, not by size
            land_value=0.25,
            appreciation=0.045,
        ),
        opex_by_size=FakeSchema(
            id=7,
            market_id=market_id,
            market_slug="smoky-mountains",
            bedrooms=None,
            sqft=4500,
            internet=100,
            utilities=350,
        ),
        construction_amenities=[
            FakeSchema(
                amenity_name="Hot Tub",
                id=1,
                location=None,
                notes=None,
                price_tier_1=8000,
                price_tier_2=12000,
                price_tier_3=15000,
            )
        ],
        construction_remodeling=[FakeSchema(id=1, category="Flooring")],
        fred=SimpleNamespace(value=6.5, date="2026-06-01"),
        str_cribs_fee=SimpleNamespace(fee=9500),
    )
    kwargs.update(overrides)
    return PrepareUwDataService().prepare_market_context(**kwargs)


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


def test_build_from_zillow_property_lifts_address_parts_onto_columns():
    """street/city/state land on the row's columns, not the stored blob."""
    builder = NonAutomatedUnderwritingPayloadBuilder()

    payload = builder.build_from_zillow_property(
        listing_url=REQUEST_URL,
        zillow_property=_zillow_property(),
    )

    assert payload.street == "727 N Pine St"
    assert payload.city == "San Antonio"
    assert payload.state == "TX"
    # popped before persisting, so they never reach uw_details.zillow_property
    stored = payload.details.zillow_property.model_dump()
    assert "street" not in stored
    assert "city" not in stored
    assert "state" not in stored


def test_build_from_zillow_property_does_not_mutate_input():
    builder = NonAutomatedUnderwritingPayloadBuilder()
    zillow_property = _zillow_property()

    builder.build_from_zillow_property(
        listing_url=REQUEST_URL,
        zillow_property=zillow_property,
    )

    assert zillow_property["street"] == "727 N Pine St"


def test_build_from_zillow_property_seeds_default_financing_and_taxes():
    builder = NonAutomatedUnderwritingPayloadBuilder()

    payload = builder.build_from_zillow_property(
        listing_url=REQUEST_URL,
        zillow_property=_zillow_property(),
    )

    purchase_details = payload.details.purchase_details
    assert purchase_details.purchase_price == Decimal("389000.0")
    assert purchase_details.down_payment_pct == Decimal("0.1")
    assert purchase_details.interest_rate == Decimal("0.0688")
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


class TestWithMarketContext:
    """With a market picked, the non-automated flow seeds the same line items
    the automated flow does — via the shared base-class builders."""

    def _build(self, context=None, **property_overrides):
        return NonAutomatedUnderwritingPayloadBuilder().build_from_zillow_property(
            listing_url=REQUEST_URL,
            zillow_property=_zillow_property(**property_overrides),
            market_context=context if context is not None else _market_context(),
        )

    def test_sets_market_id_from_the_context(self):
        assert self._build().market_id == 3

    def test_seeds_operating_expenses_from_market_opex(self):
        payload = self._build()
        by_expense = {item.expense_name: item.monthly_amount for item in payload.operating_expenses}

        assert by_expense["Cleaning"] == Decimal("10450")  # 275 x 38 turns
        assert by_expense["Pool/Hot Tub Maintenance"] == Decimal("1200")
        assert by_expense["Internet"] == Decimal("100")
        assert by_expense["Utilities"] == Decimal("350")
        # 0.012 x 389000 / 12
        assert by_expense["Property Taxes"] == Decimal("389")

    def test_records_the_property_tax_derivation_on_details(self):
        property_taxes = self._build().details.property_taxes

        assert property_taxes["source"] == "opex_property_tax_pct"
        assert property_taxes["annual_amount"] == Decimal("4668")
        assert property_taxes["inputs"]["purchase_price"] == Decimal("389000.0")

    def test_records_the_cleaning_cost_derivation_on_details(self):
        cleaning_cost = self._build().details.cleaning_cost

        assert cleaning_cost["cost_per_clean"] == Decimal("275")
        assert cleaning_cost["turns_per_month"] == Decimal("38")
        assert cleaning_cost["monthly_cleaning_cost"] == Decimal("10450")

    def test_seeds_optimization_items_for_the_three_defaults_then_must_haves(self):
        payload = self._build()

        assert [item.category for item in payload.optimization_list] == [
            "Furnishings",
            "Consolidated Shipping",
            "STR Cribs - Project Management",
            "Hot Tub",
        ]
        by_category = {item.category: item for item in payload.optimization_list}
        # tier-2 pricing, matching the automated flow
        assert by_category["Furnishings"].total_price == Decimal("40000")
        assert by_category["Consolidated Shipping"].total_price == Decimal("18225")
        assert by_category["STR Cribs - Project Management"].total_price == Decimal(
            "9500"
        )
        assert by_category["Hot Tub"].total_price == Decimal("12000")
        assert by_category["Hot Tub"].tier == "Mid"
        assert by_category["Hot Tub"].metric == "flat"

    def test_uses_market_derived_financing_and_tax_terms(self):
        payload = self._build()

        # the live FRED rate (6.5%) plus the 0.35% underwriting spread
        assert payload.details.purchase_details.interest_rate == Decimal("0.0685")
        # land_value off the market's opex row, not the 0.2 default
        assert payload.taxes.land_assumptions_pct == Decimal("0.25")

    def test_still_lifts_address_parts_and_stores_zillow_data(self):
        payload = self._build()

        assert payload.street == "727 N Pine St"
        assert payload.details.zillow_property.id == "26110417"
        assert "street" not in payload.details.zillow_property.model_dump()


class TestWithTemplateMarketContext:
    """No market picked: every row is present so the analyst has the full
    template, and every amount is zero."""

    def _build(self):
        context = PrepareUwDataService.to_template_market_context(
            _market_context(market_id=PrepareUwDataService.TEMPLATE_MARKET_ID)
        )
        return NonAutomatedUnderwritingPayloadBuilder().build_from_zillow_property(
            listing_url=REQUEST_URL,
            zillow_property=_zillow_property(),
            market_context=context,
        )

    def test_leaves_the_underwriting_market_less(self):
        assert self._build().market_id is None

    def test_seeds_every_opex_row_at_zero(self):
        payload = self._build()
        by_expense = {item.expense_name: item.monthly_amount for item in payload.operating_expenses}

        # same row set as a real market...
        assert set(by_expense) == {
            "Cleaning",
            "Property Taxes",
            "Pool/Hot Tub Maintenance",
            "Internet",
            "Utilities",
        }
        # ...at zero
        assert all(monthly == Decimal("0") for monthly in by_expense.values())

    def test_seeds_only_the_three_default_items_at_zero(self):
        payload = self._build()

        # must-have amenities belong to a market, so a market-less deal has none
        assert [item.category for item in payload.optimization_list] == [
            "Furnishings",
            "Consolidated Shipping",
            "STR Cribs - Project Management",
        ]
        for item in payload.optimization_list:
            assert item.total_price == Decimal("0")
            assert item.base_price == Decimal("0")
            # everything else about the row is unchanged
            assert item.tier == "Mid"
            assert item.metric == "flat"

    def test_uses_default_tax_terms_not_the_template_market_s(self):
        payload = self._build()

        # 0.25 came from template market's opex row and must not leak through
        assert payload.taxes.land_assumptions_pct == Decimal("0.2")
        # the live FRED rate is not market-specific, so it still applies
        assert payload.details.purchase_details.interest_rate == Decimal("0.0685")
