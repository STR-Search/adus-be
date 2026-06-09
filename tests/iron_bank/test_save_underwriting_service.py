from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService


class FakeUnderwritingRepository:
    def __init__(self):
        self.detail_data = None

    async def create(self, **kwargs):
        self.detail_data = kwargs["detail_data"]
        return SimpleNamespace(id=42)


@pytest.mark.asyncio
async def test_save_enriches_forecasted_revenue_before_persistence():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {
            "market_id": 3,
            "purchase_price": 100000,
            "uw_details": {
                "purchase_details": {
                    "purchase_price": 100000,
                    "down_payment_pct": Decimal("0.20"),
                    "interest_rate": Decimal("0"),
                    "mortgage_years": 10,
                    "closing_costs_pct": Decimal("0.03"),
                },
                "forecasted_revenue": {
                    "co_hosting_fee_pct": Decimal("0.10"),
                    "annual_re_appreciation_pct": Decimal("0.04"),
                    "scenarios": {
                        "low": {"forecasted_revenue": 10000},
                        "mid": {"forecasted_revenue": 12000},
                        "high": {"forecasted_revenue": 15000},
                    },
                },
            },
            "optimization_list": [
                {"category": "Paint", "total_price": 5000},
                {"category": "Furniture", "total_price": 2000},
            ],
            "operating_expenses": [
                {"expense": "Utilities", "monthly": 100},
                {"expense": "Internet", "monthly": 200},
            ],
            "taxes": {
                "land_assumptions_pct": Decimal("0.20"),
                "bonus_amount_pct": Decimal("1"),
                "tax_rate_pct": Decimal("0.37"),
            },
        }
    )

    result = await service.save(payload)

    assert result.underwriting_id == 42
    forecasted_revenue = repository.detail_data["forecasted_revenue"]
    assert forecasted_revenue["scenarios"]["low"]["annual_free_cash_flow"] == -2456.0
    assert forecasted_revenue["scenarios"]["mid"]["principal_pay_down"] == 8000.0
    assert forecasted_revenue["scenarios"]["high"]["annual_total_re_return_pct"] == 0.4585
    assert repository.detail_data["y1_coc_incl_tax_savings"] == {
        "low_pct": 0.304,
        "mid_pct": 0.360,
        "high_pct": 0.445,
    }
