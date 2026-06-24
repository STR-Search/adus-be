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


def test_generic_update_rejects_deal_status():
    with pytest.raises(ValidationError):
        UpdateUnderwritingPayload.model_validate(
            {"deal_status": "client_under_contract"}
        )
