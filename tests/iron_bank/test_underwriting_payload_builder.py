from decimal import Decimal

from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.prepare_uw import PrepareUwDataResult
from app.iron_bank.services.underwriting_payload_builder import (
    UnderwritingPayloadBuilder,
)


def test_builds_save_payload_from_prepared_uw_data():
    prepared = {
        "market_id": 3,
        "zillow_property": {
            "id": "12345",
            "url": "https://www.zillow.com/homedetails/12345",
            "price": "$485,000",
            "address": "123 Pine Ridge Rd",
            "bedrooms": 4,
        },
        "opex": {
            "cleaning": {"fee": 275, "num_of_turns": 38},
            "ranged": {"pool_hot_tub": {"low": 125, "high": 275}},
            "absolute": {
                "internet": 100,
                "utilities": 350,
                "pest_control": 60,
            },
            "property_tax_pct": 0.012,
        },
        "config": {
            "interest_rate": 0.065,
            "loan_term_years": 30,
            "down_payment": 0.1,
            "closing_costs": 0.03,
            "land_assumptions": 0.2,
            "tax_rate": 0.37,
        },
    }

    payload = UnderwritingPayloadBuilder().build(prepared)

    assert payload.zpid == "12345"
    assert payload.market_id == 3
    assert payload.listing_url == "https://www.zillow.com/homedetails/12345"
    assert payload.property_address == "123 Pine Ridge Rd"
    # absent from `prepared` here — the address-part columns stay null
    assert payload.street is None
    assert payload.purchase_price is None
    assert payload.deal_status == DealStatus.TEMPLATE_GENERATED
    assert payload.details.purchase_details.purchase_price == Decimal("485000")
    assert payload.details.purchase_details.interest_rate == Decimal("0.065")
    assert payload.details.cleaning_cost == {
        "cost_per_clean": 275,
        "turns_per_month": 38,
        "monthly_cleaning_cost": 10450,
    }
    assert payload.details.property_taxes == {
        "source": "opex_property_tax_pct",
        "annual_amount": Decimal("5820"),
        "monthly_amount": Decimal("485"),
        "inputs": {
            "opex_property_tax_pct": Decimal("0.012"),
            "purchase_price": Decimal("485000"),
        },
    }
    assert payload.taxes.land_assumptions_pct == Decimal("0.2")
    assert payload.taxes.tax_rate_pct == Decimal("0.37")
    assert [
        expense.model_dump(by_alias=True, exclude_none=True)
        for expense in payload.operating_expenses
    ] == [
        {"expense": "Cleaning", "monthly": Decimal("10450")},
        {"expense": "Property Taxes", "monthly": Decimal("485")},
        {"expense": "Pool/Hot Tub Maintenance", "monthly": Decimal("125")},
        {"expense": "Internet", "monthly": Decimal("100")},
        {"expense": "Utilities", "monthly": Decimal("350")},
        {"expense": "Pest Control", "monthly": Decimal("60")},
    ]


def test_maps_prepared_address_parts_onto_columns():
    """street/city/state ride alongside zillow_property, not inside it."""
    prepared = {
        "zillow_property": {"id": "12345", "address": "123 Pine Ridge Rd"},
        "street": "123 Pine Ridge Rd",
        "city": "Gatlinburg",
        "state": "TN",
    }

    payload = UnderwritingPayloadBuilder().build(prepared)

    assert payload.street == "123 Pine Ridge Rd"
    assert payload.city == "Gatlinburg"
    assert payload.state == "TN"


def test_builds_draft_payload_when_optional_prepared_fields_are_missing():
    prepared = {
        "market_id": None,
        "zillow_property": {
            "id": "12345",
            "url": None,
            "price": None,
            "address": None,
        },
        "opex": {"cleaning": {}, "absolute": {}},
        "config": {},
    }

    payload = UnderwritingPayloadBuilder().build(prepared)

    assert payload.zpid == "12345"
    assert payload.market_id is None
    assert payload.purchase_price is None
    assert payload.details is None
    assert payload.taxes is None
    assert [
        expense.model_dump(by_alias=True, exclude={"id"})
        for expense in payload.operating_expenses
    ] == [{"expense": "Property Taxes", "monthly": None}]


def _amenity_option(amenity_id, name, price_tier_2):
    return {
        "id": amenity_id,
        "amenity_name": name,
        "location": None,
        "notes": "catalog note",
        "price_tier_1": 1,
        "price_tier_2": price_tier_2,
        "price_tier_3": 3,
    }


def _prepared_with_amenities(*, amenities, must_have_amenity_ids):
    return {
        "market_id": 3,
        "zillow_property": {"id": "12345", "price": "485000"},
        "opex": {"cleaning": {}, "absolute": {}},
        "config": {},
        "construction_amenities": amenities,
        "must_have_amenity_ids": must_have_amenity_ids,
    }


def test_seeds_optimization_items_from_base_options_and_must_haves():
    prepared = _prepared_with_amenities(
        amenities=[
            _amenity_option(0, "Furnishings", 45000),
            _amenity_option(-1, "Consolidated Shipping", 18225),
            _amenity_option(-2, "STR Cribs - Project Management", 12000),
            _amenity_option(1, "Hot Tub", 9500),
            _amenity_option(2, "Fire Pit", 2200),
            _amenity_option(3, "Not A Must Have", 1000),
        ],
        must_have_amenity_ids=[2, 1],
    )

    payload = UnderwritingPayloadBuilder().build(prepared)

    assert [
        item.model_dump(exclude_unset=True) for item in payload.optimization_list
    ] == [
        {
            "category": "Furnishings",
            "total_price": Decimal("45000"),
            "base_price": Decimal("45000"),
            "metric": "flat",
            "tier": "Mid",
        },
        {
            "category": "Consolidated Shipping",
            "total_price": Decimal("18225"),
            "base_price": Decimal("18225"),
            "metric": "flat",
            "tier": "Mid",
        },
        {
            "category": "STR Cribs - Project Management",
            "total_price": Decimal("12000"),
            "base_price": Decimal("12000"),
            "metric": "flat",
            "tier": "Mid",
        },
        {
            "category": "Fire Pit",
            "total_price": Decimal("2200"),
            "base_price": Decimal("2200"),
            "metric": "flat",
            "tier": "Mid",
        },
        {
            "category": "Hot Tub",
            "total_price": Decimal("9500"),
            "base_price": Decimal("9500"),
            "metric": "flat",
            "tier": "Mid",
        },
    ]
    # spec and notes are left for the analyst.
    assert all(
        item.spec is None and item.notes is None for item in payload.optimization_list
    )


def test_seeds_blank_optimization_item_when_tier_price_is_missing():
    prepared = _prepared_with_amenities(
        amenities=[_amenity_option(0, "Furnishings", None)],
        must_have_amenity_ids=[],
    )

    payload = UnderwritingPayloadBuilder().build(prepared)

    assert [item.category for item in payload.optimization_list] == ["Furnishings"]
    assert payload.optimization_list[0].total_price is None
    assert payload.optimization_list[0].base_price is None


def test_skips_must_have_ids_absent_from_the_amenity_catalog():
    prepared = _prepared_with_amenities(
        amenities=[_amenity_option(0, "Furnishings", 45000)],
        must_have_amenity_ids=[99],
    )

    payload = UnderwritingPayloadBuilder().build(prepared)

    assert [item.category for item in payload.optimization_list] == ["Furnishings"]


def test_deduplicates_must_have_ids_overlapping_base_options():
    prepared = _prepared_with_amenities(
        amenities=[
            _amenity_option(0, "Furnishings", 45000),
            _amenity_option(1, "Hot Tub", 9500),
        ],
        must_have_amenity_ids=[0, 1, 1],
    )

    payload = UnderwritingPayloadBuilder().build(prepared)

    assert [item.category for item in payload.optimization_list] == [
        "Furnishings",
        "Hot Tub",
    ]


def test_optimization_list_is_empty_without_prepared_amenities():
    prepared = {
        "market_id": None,
        "zillow_property": {"id": "12345", "price": None},
        "opex": {"cleaning": {}, "absolute": {}},
        "config": {},
    }

    assert UnderwritingPayloadBuilder().build(prepared).optimization_list == []


def test_property_taxes_hierarchy():
    builder = UnderwritingPayloadBuilder()

    from_pct = builder.build_opex_property_taxes(
        property_tax_pct=Decimal("0.012"),
        purchase_price=Decimal("485000"),
        zillow_annual_tax=Decimal("9000"),
    )
    assert from_pct["source"] == "opex_property_tax_pct"
    assert from_pct["annual_amount"] == Decimal("5820")
    assert from_pct["monthly_amount"] == Decimal("485")
    assert from_pct["inputs"] == {
        "opex_property_tax_pct": Decimal("0.012"),
        "purchase_price": Decimal("485000"),
    }

    from_zillow = builder.build_opex_property_taxes(
        property_tax_pct=None,
        purchase_price=Decimal("485000"),
        zillow_annual_tax=Decimal("9000"),
    )
    assert from_zillow == {
        "source": "zillow_annual_tax",
        "annual_amount": Decimal("9000"),
        "monthly_amount": Decimal("750"),
        "inputs": {},
    }

    assert (
        builder.build_opex_property_taxes(
            property_tax_pct=Decimal("0.012"), purchase_price=None
        )
        is None
    )
    assert (
        builder.build_opex_property_taxes(
            property_tax_pct=None, purchase_price=Decimal("485000")
        )
        is None
    )


def test_treats_zero_purchase_price_as_missing():
    prepared = {
        "market_id": 3,
        "zillow_property": {
            "id": "12345",
            "url": "https://www.zillow.com/homedetails/12345",
            "price": "0",
            "address": "123 Pine Ridge Rd",
        },
        "opex": {"cleaning": {}, "absolute": {}},
        "config": {},
    }

    payload = UnderwritingPayloadBuilder().build(prepared)

    assert payload.purchase_price is None
    assert payload.details is None
    assert payload.taxes is None


def test_builds_save_payload_from_prepared_schema():
    prepared = PrepareUwDataResult.model_validate(
        {
            "market_id": 3,
            "zillow_property": {
                "id": "12345",
                "url": "https://www.zillow.com/homedetails/12345",
                "price": "485000",
                "address": "123 Pine Ridge Rd",
            },
            "opex": {
                "cleaning": {"fee": 275, "num_of_turns": 38},
                "ranged": {"pool_hot_tub": {"low": 125, "high": 275}},
                "absolute": {"internet": 100},
            },
            "construction_amenities": [],
            "construction_remodeling": [],
            "config": {
                "interest_rate": 0.065,
                "loan_term_years": 30,
                "down_payment": 0.1,
                "closing_costs": 0.03,
                "fred": {"value": 0.065, "date": "2024-06-01"},
                "land_assumptions": 0.2,
                "annual_re_appreciation_pct": 0.04,
                "tax_rate": 0.37,
                "co_hosting_pct": 0,
            },
        }
    )

    payload = UnderwritingPayloadBuilder().build(prepared)

    assert payload.zpid == "12345"
    assert payload.market_id == 3
    assert payload.purchase_price is None


def test_owner_is_the_market_analyst_owner():
    """Automated deals inherit ownership from their market's analyst."""
    prepared = {
        "market_id": 3,
        "analyst_owner_id": 7,
        "zillow_property": {"id": "12345", "price": "485000"},
        "opex": {"cleaning": {}, "absolute": {}},
        "config": {},
    }

    assert UnderwritingPayloadBuilder().build(prepared).owner_id == 7


def test_owner_is_null_when_the_market_has_no_analyst_owner():
    prepared = {
        "market_id": 3,
        "zillow_property": {"id": "12345", "price": "485000"},
        "opex": {"cleaning": {}, "absolute": {}},
        "config": {},
    }

    assert UnderwritingPayloadBuilder().build(prepared).owner_id is None


def test_build_seeds_bedrooms_and_bathrooms_from_the_listing():
    # The automated flow's zillow_property is built from scheduled_listings, so
    # the columns are seeded without a second lookup.
    payload = UnderwritingPayloadBuilder().build(
        {"zillow_property": {"id": "123", "bedrooms": 4, "bathrooms": "2.5"}}
    )

    assert payload.bedrooms == 4
    assert payload.bathrooms == Decimal("2.5")
