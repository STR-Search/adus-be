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
    def __init__(self, beds=4, baths=2.5, home_status=None):
        self.beds = beds
        self.baths = baths
        self.home_status = home_status
        self.zpid = None

    async def get_by_zpid(self, zpid: str):
        self.zpid = zpid
        return SimpleNamespace(
            beds=self.beds, baths=self.baths, home_status=self.home_status
        )


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


class FakeOpexByBedroomsService:
    """Supplies markets.opex_by_bedrooms.appreciation for the forecast."""

    def __init__(self, appreciation=Decimal("0.055"), row_exists=True):
        self.row = SimpleNamespace(appreciation=appreciation) if row_exists else None
        self.request = None

    async def get_by_market_and_bedrooms(self, bedrooms, market_id=None):
        self.request = {"bedrooms": bedrooms, "market_id": market_id}
        return self.row


@pytest.mark.asyncio
async def test_save_persists_is_automated():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate({"is_automated": False})

    await service.save(payload)

    assert repository.underwriting_data["is_automated"] is False


@pytest.mark.asyncio
async def test_save_persists_client_provided_zillow_property():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {
            "is_automated": False,
            "details": {
                "zillow_property": {
                    "id": "copied-from-browser",
                    "url": "https://www.zillow.com/homedetails/999",
                    "bedrooms": 3,
                    "price": 510000,
                    "some_future_field": "kept",
                }
            },
        }
    )

    await service.save(payload)

    stored = repository.detail_data["zillow_property"]
    assert stored["id"] == "copied-from-browser"
    assert stored["bedrooms"] == 3
    # superset fields are tolerated and persisted
    assert stored["some_future_field"] == "kept"


@pytest.mark.parametrize(
    ("home_status", "expected_property_pending"),
    [
        # An unknown home status is treated as pending — we only clear the flag
        # for a listing we positively know is still for sale.
        (None, True),
        ("FOR_SALE", False),
        ("SOLD", True),
        ("OTHER", True),
        ("RECENTLY_SOLD", True),
        ("PENDING", True),
    ],
)
@pytest.mark.asyncio
async def test_save_assigns_property_pending_from_listing_home_status(
    home_status, expected_property_pending
):
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(
        repository,
        listings_service=FakeListingsService(home_status=home_status),
    )
    payload = SaveUnderwritingPayload.model_validate(
        {"is_automated": False, "zpid": "12345"}
    )

    await service.save(payload)

    assert repository.underwriting_data["property_pending"] is expected_property_pending


@pytest.mark.asyncio
async def test_save_enriches_forecasted_revenue_before_persistence():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {
            "is_automated": False,
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
async def test_save_promotes_purchase_price_from_purchase_details():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {
            "is_automated": False,
            "market_id": 3,
            "details": {
                "purchase_details": {
                    "purchase_price": 100000,
                    "down_payment_pct": Decimal("0.20"),
                    "interest_rate": Decimal("0"),
                    "mortgage_years": 10,
                    "closing_costs_pct": Decimal("0.03"),
                },
            },
        }
    )

    await service.save(payload)

    assert repository.underwriting_data["purchase_price"] == Decimal("100000")


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
            "is_automated": False,
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
    assert repository.underwriting_data["prr"] == Decimal("0.2200")
    assert repository.underwriting_data["budget_to_pp"] == Decimal("0.2500")
    assert repository.underwriting_data["l_cash_on_cash"] == Decimal("0.4339")
    assert repository.underwriting_data["m_cash_on_cash"] == Decimal("0.5120")
    assert repository.underwriting_data["h_cash_on_cash"] == Decimal("0.5901")


@pytest.mark.asyncio
async def test_save_rounds_forecasted_revenue_percentiles_to_two_decimals():
    """``percentile_cont`` interpolates, so the raw floats carry full precision."""
    repository = FakeUnderwritingRepository()
    cleaned_data_service = FakeCleanedDataService(
        low=74821.33333333333,
        mid=88450.666666666,
        high=101234.565,
    )
    service = SaveUnderwritingService(
        repository,
        market_service=FakeMarketService(),
        listings_service=FakeListingsService(),
        cleaned_data_service=cleaned_data_service,
    )

    await service.save(_forecast_payload())

    scenarios = repository.detail_data["forecasted_revenue"]["scenarios"]
    assert scenarios["low"]["forecasted_revenue"] == 74821.33
    assert scenarios["mid"]["forecasted_revenue"] == 88450.67
    assert scenarios["high"]["forecasted_revenue"] == 101234.57


def _forecast_payload(market_id=3):
    return SaveUnderwritingPayload.model_validate(
        {
            "is_automated": False,
            "zpid": "12345",
            "market_id": market_id,
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
            "operating_expenses": [{"expense": "Utilities", "monthly": 1000}],
        }
    )


async def _saved_appreciation_pct(opex_service, market_id=3):
    """Save with the Airbnb estimate path and report the appreciation used."""
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(
        repository,
        market_service=FakeMarketService(),
        listings_service=FakeListingsService(),
        cleaned_data_service=FakeCleanedDataService(),
        opex_service=opex_service,
    )
    await service.save(_forecast_payload(market_id))
    return repository.detail_data["forecasted_revenue"]["annual_re_appreciation_pct"]


@pytest.mark.asyncio
async def test_forecast_uses_the_market_appreciation_rate():
    opex_service = FakeOpexByBedroomsService(appreciation=Decimal("0.055"))

    pct = await _saved_appreciation_pct(opex_service)

    # keyed the same way the Airbnb comps are: (market, bedrooms)
    assert opex_service.request == {"bedrooms": 4, "market_id": 3}
    # the market's own rate, not the 0.0425 fallback
    assert pct == 0.055


@pytest.mark.asyncio
async def test_forecast_falls_back_when_the_market_has_no_appreciation_rate():
    pct = await _saved_appreciation_pct(FakeOpexByBedroomsService(appreciation=None))

    assert pct == 0.0425


@pytest.mark.asyncio
async def test_forecast_falls_back_when_there_is_no_opex_row():
    pct = await _saved_appreciation_pct(FakeOpexByBedroomsService(row_exists=False))

    assert pct == 0.0425


@pytest.mark.asyncio
async def test_forecast_falls_back_when_no_opex_service_is_wired():
    # the fallback keeps machine-driven flows that skip the dep working
    assert await _saved_appreciation_pct(None) == 0.0425


@pytest.mark.asyncio
async def test_forecast_skips_the_appreciation_lookup_without_a_market():
    opex_service = FakeOpexByBedroomsService()

    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(
        repository,
        market_service=FakeMarketService(),
        listings_service=FakeListingsService(),
        cleaned_data_service=FakeCleanedDataService(),
        opex_service=opex_service,
    )
    await service.save(_forecast_payload(market_id=None))

    # a market-less deal gets no forecast at all, so nothing to look up
    assert opex_service.request is None
    assert "forecasted_revenue" not in repository.detail_data


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
            "is_automated": False,
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
    assert repository.underwriting_data["prr"] == Decimal("2.2000")
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
            "is_automated": False,
            "zpid": "12345",
            "market_id": 3,
            "details": {
                "cleaning_cost": {
                    "cost_per_clean": 100,
                    "turns_per_month": 10,
                }
            },
        }
    )

    await service.save(payload)

    assert cleaned_data_service.request is None
    assert repository.detail_data == {
        "cleaning_cost": {
            "cost_per_clean": 100,
            "turns_per_month": 10,
        }
    }
    assert "forecasted_revenue" not in repository.detail_data
    assert "low_gross_revenue" not in repository.underwriting_data


def test_forecasted_revenue_requires_all_three_scenarios_when_provided():
    with pytest.raises(ValidationError):
        SaveUnderwritingPayload.model_validate(
            {
                "is_automated": False,
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


# --- bedrooms/bathrooms are persisted on every creation path ----------------
#
# The columns are the source of truth from creation onwards, so save() resolves
# them centrally rather than trusting the payload builders alone -- a direct
# POST /iron-bank/underwritings must not leave them NULL.


@pytest.mark.asyncio
async def test_save_persists_bedrooms_and_bathrooms_from_the_payload():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {"is_automated": False, "bedrooms": 5, "bathrooms": "3.5"}
    )

    await service.save(payload)

    assert repository.underwriting_data["bedrooms"] == 5
    assert repository.underwriting_data["bathrooms"] == Decimal("3.5")


@pytest.mark.asyncio
async def test_save_falls_back_to_the_stored_zillow_property():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {
            "is_automated": False,
            "details": {"zillow_property": {"bedrooms": 3, "bathrooms": "2.5"}},
        }
    )

    await service.save(payload)

    assert repository.underwriting_data["bedrooms"] == 3
    assert repository.underwriting_data["bathrooms"] == Decimal("2.5")


@pytest.mark.asyncio
async def test_save_falls_back_to_the_scheduled_listing():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(
        repository, listings_service=FakeListingsService(beds=6, baths=4.5)
    )
    payload = SaveUnderwritingPayload.model_validate(
        {"is_automated": True, "zpid": "12345"}
    )

    await service.save(payload)

    assert repository.underwriting_data["bedrooms"] == 6
    # scheduled_listings.baths is a float; the column is Numeric.
    assert repository.underwriting_data["bathrooms"] == Decimal("4.5")


@pytest.mark.asyncio
async def test_save_prefers_the_payload_over_every_zillow_source():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(
        repository, listings_service=FakeListingsService(beds=6, baths=4.5)
    )
    payload = SaveUnderwritingPayload.model_validate(
        {
            "is_automated": True,
            "zpid": "12345",
            "bedrooms": 5,
            "bathrooms": "3.5",
            "details": {"zillow_property": {"bedrooms": 3, "bathrooms": "2.5"}},
        }
    )

    await service.save(payload)

    assert repository.underwriting_data["bedrooms"] == 5
    assert repository.underwriting_data["bathrooms"] == Decimal("3.5")
    # Zillow's own observation is still persisted, unchanged.
    assert repository.detail_data["zillow_property"]["bedrooms"] == 3


@pytest.mark.asyncio
async def test_save_leaves_the_columns_null_when_nothing_can_resolve_them():
    repository = FakeUnderwritingRepository()
    service = SaveUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate({"is_automated": False})

    await service.save(payload)

    assert repository.underwriting_data["bedrooms"] is None
    assert repository.underwriting_data["bathrooms"] is None
