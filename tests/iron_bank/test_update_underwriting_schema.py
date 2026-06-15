import pytest
from pydantic import ValidationError

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
