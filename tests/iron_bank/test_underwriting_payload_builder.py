from decimal import Decimal

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
                "property_taxes": None,
                "consolidated_shipping": 18225,
            },
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
    assert payload.purchase_price == Decimal("485000")
    assert payload.deal_status == "Draft"
    assert payload.details.purchase_details.purchase_price == Decimal("485000")
    assert payload.details.purchase_details.interest_rate == Decimal("0.065")
    assert payload.details.cleaning_cost == {
        "cost_per_clean": 275,
        "turns_per_year": 38,
        "annual_cleaning_cost": 10450,
    }
    assert payload.taxes.land_assumptions_pct == Decimal("0.2")
    assert payload.taxes.tax_rate_pct == Decimal("0.37")
    assert [
        expense.model_dump(by_alias=True, exclude_none=True)
        for expense in payload.operating_expenses
    ] == [
        {"expense": "Cleaning", "monthly": Decimal("10450")},
        {"expense": "Pool/Hot Tub Maintenance", "monthly": Decimal("125")},
        {"expense": "Internet", "monthly": Decimal("100")},
        {"expense": "Utilities", "monthly": Decimal("350")},
        {"expense": "Pest Control", "monthly": Decimal("60")},
    ]


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
    assert payload.operating_expenses == []
