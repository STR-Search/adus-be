import pytest
from pydantic import ValidationError

from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.update_underwriting import UpdateUnderwritingPayload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 123),
        ("zpid", "123456"),
        ("market_id", 3),
        ("uw_details", {}),
    ],
)
def test_update_underwriting_payload_rejects_non_updatable_fields(field, value):
    with pytest.raises(ValidationError):
        UpdateUnderwritingPayload.model_validate({field: value})


def test_update_underwriting_accepts_valid_deal_status():
    result = UpdateUnderwritingPayload.model_validate(
        {"deal_status": "client_under_contract"}
    )

    assert result.deal_status == DealStatus.CLIENT_UNDER_CONTRACT


def test_update_underwriting_rejects_invalid_deal_status():
    with pytest.raises(ValidationError):
        UpdateUnderwritingPayload.model_validate({"deal_status": "not_real"})
