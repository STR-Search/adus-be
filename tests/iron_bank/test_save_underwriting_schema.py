from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload


def _payload() -> dict:
    return {
        "market_id": 3,
        "purchase_price": 485000,
        "details": {
            "purchase_details": {
                "purchase_price": 485000,
                "down_payment_pct": Decimal("0.10"),
                "interest_rate": Decimal("0.0675"),
                "mortgage_years": 30,
                "closing_costs_pct": Decimal("0.03"),
            },
            "forecasted_revenue": {
                "co_hosting_fee_pct": Decimal("0"),
                "annual_re_appreciation_pct": Decimal("0.04"),
                "scenarios": {
                    "low": {"forecasted_revenue": 72000},
                    "mid": {"forecasted_revenue": 98000},
                    "high": {"forecasted_revenue": 127000},
                },
            },
        },
        "taxes": {
            "land_assumptions_pct": Decimal("0.20"),
            "sla_multiplier_pct": Decimal("0.36"),
            "bonus_amount_pct": Decimal("1.00"),
            "tax_rate_pct": Decimal("0.37"),
        },
    }


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("details", "purchase_details", "down_payment_pct"), Decimal("10")),
        (("details", "purchase_details", "interest_rate"), Decimal("6.75")),
        (("details", "purchase_details", "closing_costs_pct"), Decimal("3")),
        (("details", "forecasted_revenue", "co_hosting_fee_pct"), Decimal("12")),
        (
            ("details", "forecasted_revenue", "annual_re_appreciation_pct"),
            Decimal("4"),
        ),
        (("taxes", "land_assumptions_pct"), Decimal("20")),
        (("taxes", "sla_multiplier_pct"), Decimal("36")),
        (("taxes", "bonus_amount_pct"), Decimal("100")),
        (("taxes", "tax_rate_pct"), Decimal("37")),
    ],
)
def test_percentage_inputs_must_be_fractional_values(path, value):
    payload = _payload()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        SaveUnderwritingPayload.model_validate(payload)


def test_percentage_inputs_accept_zero_to_one_fractional_values():
    payload = deepcopy(_payload())

    result = SaveUnderwritingPayload.model_validate(payload)

    assert result.details.purchase_details.down_payment_pct == Decimal("0.10")
    assert result.taxes.tax_rate_pct == Decimal("0.37")


def test_taxes_require_sla_multiplier_pct():
    payload = _payload()
    del payload["taxes"]["sla_multiplier_pct"]

    with pytest.raises(ValidationError):
        SaveUnderwritingPayload.model_validate(payload)


def test_save_payload_rejects_legacy_uw_details_field():
    payload = _payload()
    payload["uw_details"] = payload.pop("details")

    with pytest.raises(ValidationError):
        SaveUnderwritingPayload.model_validate(payload)


def test_save_underwriting_accepts_valid_deal_status():
    payload = {"deal_status": "analyst_started"}

    result = SaveUnderwritingPayload.model_validate(payload)

    assert result.deal_status == DealStatus.ANALYST_STARTED


def test_save_underwriting_rejects_invalid_deal_status():
    with pytest.raises(ValidationError):
        SaveUnderwritingPayload.model_validate({"deal_status": "not_real"})
