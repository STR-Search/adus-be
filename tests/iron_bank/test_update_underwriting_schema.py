import pytest
from pydantic import ValidationError

from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.deal_status import UpdateDealStatusPayload
from app.iron_bank.schemas.update_underwriting import UpdateUnderwritingPayload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 123),
        ("zpid", "123456"),
        ("uw_details", {}),
    ],
)
def test_update_underwriting_payload_rejects_non_updatable_fields(field, value):
    with pytest.raises(ValidationError):
        UpdateUnderwritingPayload.model_validate({field: value})


def test_update_underwriting_payload_accepts_market_id():
    # market_id is updatable so an analyst can assign a non-automated draft to a
    # market, which unlocks the Airbnb forecasted-revenue estimate.
    payload = UpdateUnderwritingPayload.model_validate({"market_id": 3})

    assert payload.market_id == 3


def test_update_deal_status_accepts_valid_deal_status():
    result = UpdateDealStatusPayload.model_validate(
        {"deal_status": "client_under_contract"}
    )

    assert result.deal_status == DealStatus.CLIENT_UNDER_CONTRACT


def test_update_deal_status_rejects_invalid_deal_status():
    with pytest.raises(ValidationError):
        UpdateDealStatusPayload.model_validate({"deal_status": "not_real"})


def test_update_deal_status_rejects_unrelated_fields():
    with pytest.raises(ValidationError):
        UpdateDealStatusPayload.model_validate(
            {
                "deal_status": "client_under_contract",
                "purchase_price": 125000,
            }
        )


_PURCHASE_DETAILS = {
    "purchase_price": 485000,
    "down_payment_pct": "0.10",
    "interest_rate": "0.0675",
    "mortgage_years": 30,
    "closing_costs_pct": "0.03",
}


@pytest.mark.parametrize(
    "omitted",
    [
        ["optimization_list", "operating_expenses"],
        ["optimization_list"],
        ["operating_expenses"],
    ],
)
def test_purchase_details_requires_explicit_collections(omitted):
    # Without explicit collections, the update path would calculate OOP/CoC
    # from empty defaults while preserving stored rows — reject instead.
    payload = {
        "details": {"purchase_details": _PURCHASE_DETAILS},
        "optimization_list": [{"category": "Flooring", "total_price": 1000}],
        "operating_expenses": [{"expense": "Internet", "monthly": 100}],
    }
    for field in omitted:
        del payload[field]

    with pytest.raises(ValidationError, match="must be sent explicitly"):
        UpdateUnderwritingPayload.model_validate(payload)


def test_purchase_details_accepts_explicit_collections_even_empty():
    # Explicit empty lists are a deliberate "there are none".
    payload = UpdateUnderwritingPayload.model_validate(
        {
            "details": {"purchase_details": _PURCHASE_DETAILS},
            "optimization_list": [],
            "operating_expenses": [],
        }
    )

    assert payload.details.purchase_details is not None


def test_details_without_purchase_details_needs_no_collections():
    # Only purchase_details triggers recalculation; other detail-only updates
    # stay valid without the collections.
    payload = UpdateUnderwritingPayload.model_validate(
        {"details": {"analyst_notes": "note"}}
    )

    assert payload.details.analyst_notes == "note"


def test_generic_update_accepts_deal_status():
    # deal_status is editable from the generic update payload so the FE can
    # change it alongside other fields, not only via the dedicated endpoint.
    payload = UpdateUnderwritingPayload.model_validate(
        {"deal_status": "client_under_contract"}
    )

    assert payload.deal_status == DealStatus.CLIENT_UNDER_CONTRACT


def test_generic_update_rejects_invalid_deal_status():
    with pytest.raises(ValidationError):
        UpdateUnderwritingPayload.model_validate({"deal_status": "not_real"})
