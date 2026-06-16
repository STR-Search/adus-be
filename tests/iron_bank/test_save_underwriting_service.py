from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService


class FakeUnderwritingRepository:
    def __init__(self):
        self.detail_data = None
        self.underwriting_data = None

    async def create(self, **kwargs):
        self.underwriting_data = kwargs["underwriting_data"]
        self.detail_data = kwargs["detail_data"]
        return SimpleNamespace(id=42)


class FakeMarketService:
    def __init__(self, market_name_current="Gatlinburg"):
        self.market_name_current = market_name_current
        self.market_id = None

    async def get_by_id(self, market_id: int):
        self.market_id = market_id
        return SimpleNamespace(market_name_current=self.market_name_current)


class FakeListingsService:
    def __init__(self, beds=4):
        self.beds = beds
        self.zpid = None

    async def get_by_zpid(self, zpid: str):
        self.zpid = zpid
        return SimpleNamespace(beds=self.beds)


class FakeCleanedDataService:
    def __init__(
        self,
        low=Decimal("200000"),
        mid=Decimal("220000"),
        high=Decimal("240000"),
    ):
        self.low = low
        self.mid = mid
        self.high = high
        self.request = None

    async def get_revenue_potential_percentiles(
        self, *, key_market: str, bedrooms: int
    ):
        self.request = {"key_market": key_market, "bedrooms": bedrooms}
        return SimpleNamespace(low=self.low, mid=self.mid, high=self.high)


@pytest.mark.asyncio
async def test_save_enriches_forecasted_revenue_before_persistence():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {
            "market_id": 3,
            "purchase_price": 100000,
            "details": {
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
                "sla_multiplier_pct": Decimal("0.36"),
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
    assert (
        forecasted_revenue["scenarios"]["high"]["annual_total_re_return_pct"] == 0.4585
    )
    assert repository.detail_data["y1_coc_incl_tax_savings"] == {
        "low_pct": 0.304,
        "mid_pct": 0.360,
        "high_pct": 0.445,
    }


@pytest.mark.asyncio
async def test_save_builds_missing_forecasted_revenue_from_airbnb_percentiles():
    repository = FakeUnderwritingRepository()
    market_service = FakeMarketService()
    listings_service = FakeListingsService()
    cleaned_data_service = FakeCleanedDataService()
    service = SaveUnderwritingService(
        repository,
        market_service=market_service,
        listings_service=listings_service,
        cleaned_data_service=cleaned_data_service,
    )
    payload = SaveUnderwritingPayload.model_validate(
        {
            "zpid": "12345",
            "market_id": 3,
            "purchase_price": 1000000,
            "details": {
                "purchase_details": {
                    "purchase_price": 1000000,
                    "down_payment_pct": Decimal("0.20"),
                    "interest_rate": Decimal("0"),
                    "mortgage_years": 10,
                    "closing_costs_pct": Decimal("0.03"),
                }
            },
            "optimization_list": [{"category": "Furniture", "total_price": 20000}],
            "operating_expenses": [{"expense": "Utilities", "monthly": 1000}],
            "taxes": {
                "land_assumptions_pct": Decimal("0.20"),
                "sla_multiplier_pct": Decimal("0.36"),
                "bonus_amount_pct": Decimal("1"),
                "tax_rate_pct": Decimal("0.37"),
            },
        }
    )

    await service.save(payload)

    assert market_service.market_id == 3
    assert listings_service.zpid == "12345"
    assert cleaned_data_service.request == {"key_market": "Gatlinburg", "bedrooms": 4}
    forecasted_revenue = repository.detail_data["forecasted_revenue"]
    assert forecasted_revenue["co_hosting_fee_pct"] == 0.0
    assert forecasted_revenue["annual_re_appreciation_pct"] == 0.0425
    assert forecasted_revenue["scenarios"]["low"]["forecasted_revenue"] == 200000.0
    assert forecasted_revenue["scenarios"]["mid"]["forecasted_revenue"] == 220000.0
    assert forecasted_revenue["scenarios"]["high"]["forecasted_revenue"] == 240000.0
    assert repository.underwriting_data["low_gross_revenue"] == Decimal("200000")
    assert repository.underwriting_data["mid_gross_revenue"] == Decimal("220000")
    assert repository.underwriting_data["high_gross_revenue"] == Decimal("240000")
    assert repository.underwriting_data["total_oop"] == Decimal("250000.00")
    assert repository.underwriting_data["prr"] == Decimal("4.5455")
    assert repository.underwriting_data["budget_to_pp"] == Decimal("0.2500")
    assert repository.underwriting_data["l_cash_on_cash"] == Decimal("0.4339")
    assert repository.underwriting_data["m_cash_on_cash"] == Decimal("0.5120")
    assert repository.underwriting_data["h_cash_on_cash"] == Decimal("0.5901")


@pytest.mark.asyncio
async def test_save_uses_explicit_forecasted_revenue_without_airbnb_lookup():
    repository = FakeUnderwritingRepository()
    cleaned_data_service = FakeCleanedDataService()
    service = SaveUnderwritingService(
        repository,
        market_service=FakeMarketService(),
        listings_service=FakeListingsService(),
        cleaned_data_service=cleaned_data_service,
    )
    payload = SaveUnderwritingPayload.model_validate(
        {
            "zpid": "12345",
            "market_id": 3,
            "purchase_price": 100000,
            "details": {
                "purchase_details": {
                    "purchase_price": 100000,
                    "down_payment_pct": Decimal("0.20"),
                    "interest_rate": Decimal("0"),
                    "mortgage_years": 10,
                    "closing_costs_pct": Decimal("0.03"),
                },
                "forecasted_revenue": {
                    "co_hosting_fee_pct": Decimal("0"),
                    "annual_re_appreciation_pct": Decimal("0.0425"),
                    "scenarios": {
                        "low": {"forecasted_revenue": 200000},
                        "mid": {"forecasted_revenue": 220000},
                        "high": {"forecasted_revenue": 240000},
                    },
                },
            },
            "optimization_list": [],
            "operating_expenses": [],
            "taxes": {
                "land_assumptions_pct": Decimal("0.20"),
                "sla_multiplier_pct": Decimal("0.36"),
                "bonus_amount_pct": Decimal("1"),
                "tax_rate_pct": Decimal("0.37"),
            },
        }
    )

    await service.save(payload)

    assert cleaned_data_service.request is None
    assert repository.underwriting_data["low_gross_revenue"] == Decimal("200000")
    assert repository.underwriting_data["mid_gross_revenue"] == Decimal("220000")
    assert repository.underwriting_data["high_gross_revenue"] == Decimal("240000")
    assert repository.underwriting_data["total_oop"] == Decimal("23000.00")
    assert repository.underwriting_data["prr"] == Decimal("0.4545")
    assert repository.underwriting_data["budget_to_pp"] == Decimal("0.2300")
    assert repository.underwriting_data["l_cash_on_cash"] == Decimal("8.3478")
    assert repository.underwriting_data["m_cash_on_cash"] == Decimal("9.2174")
    assert repository.underwriting_data["h_cash_on_cash"] == Decimal("10.0870")


@pytest.mark.asyncio
async def test_save_skips_airbnb_forecast_when_purchase_details_are_missing():
    repository = FakeUnderwritingRepository()
    cleaned_data_service = FakeCleanedDataService()
    service = SaveUnderwritingService(
        repository,
        market_service=FakeMarketService(),
        listings_service=FakeListingsService(),
        cleaned_data_service=cleaned_data_service,
    )
    payload = SaveUnderwritingPayload.model_validate(
        {
            "zpid": "12345",
            "market_id": 3,
            "details": {
                "cleaning_cost": {
                    "cost_per_clean": 100,
                    "turns_per_year": 10,
                }
            },
        }
    )

    await service.save(payload)

    assert cleaned_data_service.request is None
    assert repository.detail_data == {
        "cleaning_cost": {
            "cost_per_clean": 100,
            "turns_per_year": 10,
        }
    }
    assert "forecasted_revenue" not in repository.detail_data
    assert "low_gross_revenue" not in repository.underwriting_data


def test_forecasted_revenue_requires_all_three_scenarios_when_provided():
    with pytest.raises(ValidationError):
        SaveUnderwritingPayload.model_validate(
            {
                "market_id": 3,
                "details": {
                    "forecasted_revenue": {
                        "co_hosting_fee_pct": Decimal("0"),
                        "annual_re_appreciation_pct": Decimal("0.0425"),
                        "scenarios": {
                            "low": {"forecasted_revenue": 200000},
                            "mid": {"forecasted_revenue": 220000},
                        },
                    }
                },
            }
        )
