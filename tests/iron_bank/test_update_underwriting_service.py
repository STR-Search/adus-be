from types import SimpleNamespace
from decimal import Decimal

import pytest

from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.schemas.update_underwriting import UpdateUnderwritingPayload
from app.iron_bank.services.update_underwriting_service import UpdateUnderwritingService

_DEFAULT_UNDERWRITING = object()


class FakeUnderwritingRepository:
    def __init__(self, underwriting=_DEFAULT_UNDERWRITING):
        self.underwriting = (
            SimpleNamespace(id=42)
            if underwriting is _DEFAULT_UNDERWRITING
            else underwriting
        )
        self.update_kwargs = None

    async def get_by_id(self, underwriting_id: int):
        return self.underwriting

    async def update(self, underwriting_id: int, **kwargs):
        self.update_kwargs = {"underwriting_id": underwriting_id, **kwargs}
        return self.underwriting


@pytest.mark.asyncio
async def test_reconcile_purchase_price_updates_only_price_dependent_data():
    repository = FakeUnderwritingRepository()
    service = UpdateUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {
            "is_automated": False,
            "details": {
                "purchase_details": {
                    "purchase_price": 525000,
                    "down_payment_pct": Decimal("0.20"),
                    "interest_rate": Decimal("0.06"),
                    "mortgage_years": 30,
                    "closing_costs_pct": Decimal("0.03"),
                },
                "forecasted_revenue": {
                    "co_hosting_fee_pct": Decimal("0.10"),
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
                "bonus_amount_pct": Decimal("1"),
                "tax_rate_pct": Decimal("0.37"),
            },
            "optimization_list": [{"category": "Furniture", "total_price": 20000}],
            "operating_expenses": [{"expense": "Utilities", "monthly": 1000}],
        }
    )

    result = await service.reconcile_purchase_price(42, payload)

    assert result.underwriting_id == 42
    kwargs = repository.update_kwargs
    assert set(kwargs["underwriting_data"]) == {
        "purchase_price",
        "total_oop",
        "prr",
        "budget_to_pp",
        "l_cash_on_cash",
        "m_cash_on_cash",
        "h_cash_on_cash",
    }
    assert set(kwargs["detail_data"]) == {
        "purchase_details",
        "forecasted_revenue",
        "y1_coc_incl_tax_savings",
    }
    assert kwargs["tax_data"] is not None
    assert kwargs["optimization_items"] is None
    assert kwargs["operating_expenses"] is None
    assert kwargs["comp_set"] is None


@pytest.mark.asyncio
async def test_update_leaves_omitted_children_untouched():
    repository = FakeUnderwritingRepository()
    service = UpdateUnderwritingService(repository)
    payload = UpdateUnderwritingPayload.model_validate(
        {
            "purchase_price": 125000,
        }
    )

    result = await service.update(42, payload)

    assert result.underwriting_id == 42
    assert repository.update_kwargs == {
        "underwriting_id": 42,
        "underwriting_data": {
            "purchase_price": 125000,
        },
        "detail_data": None,
        "tax_data": None,
        "optimization_items": None,
        "operating_expenses": None,
        "comp_set": None,
    }


@pytest.mark.asyncio
async def test_update_allows_explicitly_clearing_child_collections():
    repository = FakeUnderwritingRepository()
    service = UpdateUnderwritingService(repository)
    payload = UpdateUnderwritingPayload.model_validate(
        {
            "optimization_list": [],
            "operating_expenses": [],
            "comp_set": [],
        }
    )

    await service.update(42, payload)

    assert repository.update_kwargs["optimization_items"] == []
    assert repository.update_kwargs["operating_expenses"] == []
    assert repository.update_kwargs["comp_set"] == []


@pytest.mark.asyncio
async def test_update_accepts_details_payload():
    repository = FakeUnderwritingRepository()
    service = UpdateUnderwritingService(repository)
    payload = UpdateUnderwritingPayload.model_validate(
        {"details": {"analyst_notes": "Fresh underwriting note"}}
    )

    await service.update(42, payload)

    assert repository.update_kwargs["detail_data"] == {
        "analyst_notes": "Fresh underwriting note"
    }


@pytest.mark.asyncio
async def test_update_changes_deal_status_via_payload():
    repository = FakeUnderwritingRepository()
    service = UpdateUnderwritingService(repository)
    payload = UpdateUnderwritingPayload.model_validate(
        {"deal_status": "analyst_completed"}
    )

    result = await service.update(42, payload)

    assert result.underwriting_id == 42
    assert repository.update_kwargs["underwriting_data"] == {
        "deal_status": DealStatus.ANALYST_COMPLETED,
    }


@pytest.mark.asyncio
async def test_update_raises_lookup_error_when_underwriting_does_not_exist():
    repository = FakeUnderwritingRepository(underwriting=None)
    service = UpdateUnderwritingService(repository)
    payload = UpdateUnderwritingPayload.model_validate({"purchase_price": 125000})

    with pytest.raises(LookupError, match="Underwriting 42 not found"):
        await service.update(42, payload)


@pytest.mark.asyncio
async def test_update_deal_status_preserves_existing_analyst():
    repository = FakeUnderwritingRepository(
        underwriting=SimpleNamespace(
            id=42,
            deal_status=DealStatus.ANALYST_COMPLETED,
            analyst_id=7,
            approver_id=None,
        )
    )
    service = UpdateUnderwritingService(repository)

    result = await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.ANALYST_COMPLETED,
        actor_user_id=99,
    )

    assert result.model_dump() == {
        "underwriting_id": 42,
        "deal_status": DealStatus.ANALYST_COMPLETED,
    }
    # analyst_id already set -> not overwritten; status not present_to_clients
    # -> approver untouched.
    assert repository.update_kwargs == {
        "underwriting_id": 42,
        "underwriting_data": {
            "deal_status": DealStatus.ANALYST_COMPLETED,
        },
    }


@pytest.mark.asyncio
async def test_update_deal_status_assigns_analyst_when_unset():
    repository = FakeUnderwritingRepository(
        underwriting=SimpleNamespace(
            id=42,
            deal_status=DealStatus.ANALYST_STARTED,
            analyst_id=None,
            approver_id=None,
        )
    )
    service = UpdateUnderwritingService(repository)

    await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.ANALYST_STARTED,
        actor_user_id=99,
    )

    assert repository.update_kwargs["underwriting_data"] == {
        "deal_status": DealStatus.ANALYST_STARTED,
        "analyst_id": 99,
    }


@pytest.mark.asyncio
async def test_update_deal_status_assigns_approver_on_present_to_clients():
    repository = FakeUnderwritingRepository(
        underwriting=SimpleNamespace(
            id=42,
            deal_status=DealStatus.PRESENT_TO_CLIENTS,
            analyst_id=7,
            approver_id=None,
        )
    )
    service = UpdateUnderwritingService(repository)

    await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.PRESENT_TO_CLIENTS,
        actor_user_id=99,
    )

    # analyst preserved (already set), approver set to the acting user.
    assert repository.update_kwargs["underwriting_data"] == {
        "deal_status": DealStatus.PRESENT_TO_CLIENTS,
        "approver_id": 99,
    }


@pytest.mark.asyncio
async def test_update_deal_status_raises_when_underwriting_does_not_exist():
    service = UpdateUnderwritingService(FakeUnderwritingRepository(underwriting=None))

    with pytest.raises(LookupError, match="Underwriting 42 not found"):
        await service.update_deal_status(
            underwriting_id=42,
            deal_status=DealStatus.ANALYST_COMPLETED,
            actor_user_id=99,
        )


# --- recalc-on-update: forecasted_revenue estimated when a market is assigned -


class FakeRepoWithExisting:
    def __init__(self, existing):
        self.existing = existing
        self.update_kwargs = None

    async def get_by_id(self, underwriting_id: int):
        return self.existing

    async def update(self, underwriting_id: int, **kwargs):
        self.update_kwargs = {"underwriting_id": underwriting_id, **kwargs}
        return SimpleNamespace(id=underwriting_id)


class FakeMarketService:
    async def get_by_id(self, market_id: int):
        return SimpleNamespace(market_name_current="Gatlinburg")


class FakeListingsService:
    def __init__(self, beds=4):
        self.beds = beds
        self.requested_zpid = None

    async def get_by_zpid(self, zpid: str):
        self.requested_zpid = zpid
        return SimpleNamespace(beds=self.beds, home_status="FOR_SALE")


class FakeCleanedDataService:
    async def get_revenue_potential_percentiles(self, *, key_market, bedrooms):
        return SimpleNamespace(
            low=Decimal("72000"), mid=Decimal("98000"), high=Decimal("127000")
        )


def _details_with_purchase_only():
    return {
        "market_id": 3,
        "details": {
            "purchase_details": {
                "purchase_price": 485000,
                "down_payment_pct": Decimal("0.10"),
                "interest_rate": Decimal("0"),
                "mortgage_years": 30,
                "closing_costs_pct": Decimal("0.03"),
            }
        },
    }


@pytest.mark.asyncio
async def test_update_estimates_revenue_for_automated_beds_from_scheduled_listings():
    # automated row: no stored zillow_property, beds come from scheduled_listings
    repository = FakeRepoWithExisting(
        SimpleNamespace(id=42, zpid="123", market_id=None, detail=None)
    )
    listings_service = FakeListingsService()
    service = UpdateUnderwritingService(
        repository,
        market_service=FakeMarketService(),
        listings_service=listings_service,
        cleaned_data_service=FakeCleanedDataService(),
    )
    payload = UpdateUnderwritingPayload.model_validate(_details_with_purchase_only())

    await service.update(42, payload)

    # beds were looked up from scheduled_listings via the row's zpid
    assert listings_service.requested_zpid == "123"
    # revenue + downstream metrics are now computed and persisted
    underwriting_data = repository.update_kwargs["underwriting_data"]
    assert underwriting_data["mid_gross_revenue"] == Decimal("98000")
    assert "total_oop" in underwriting_data
    assert "prr" in underwriting_data
    assert "forecasted_revenue" in repository.update_kwargs["detail_data"]


@pytest.mark.asyncio
async def test_update_estimates_revenue_for_non_automated_beds_from_stored_zillow():
    # non-automated row: zpid is null, beds come from the stored zillow_property
    repository = FakeRepoWithExisting(
        SimpleNamespace(
            id=42,
            zpid=None,
            market_id=None,
            detail=SimpleNamespace(zillow_property={"bedrooms": 4}),
        )
    )
    listings_service = FakeListingsService()
    service = UpdateUnderwritingService(
        repository,
        market_service=FakeMarketService(),
        listings_service=listings_service,
        cleaned_data_service=FakeCleanedDataService(),
    )
    payload = UpdateUnderwritingPayload.model_validate(_details_with_purchase_only())

    await service.update(42, payload)

    # no scheduled_listings lookup needed — beds came from stored zillow_property
    assert listings_service.requested_zpid is None
    underwriting_data = repository.update_kwargs["underwriting_data"]
    assert underwriting_data["mid_gross_revenue"] == Decimal("98000")
    assert "forecasted_revenue" in repository.update_kwargs["detail_data"]


@pytest.mark.asyncio
async def test_update_skips_revenue_when_no_bedrooms_source():
    # neither stored zillow_property nor a resolvable zpid → graceful skip
    repository = FakeRepoWithExisting(
        SimpleNamespace(id=42, zpid=None, market_id=None, detail=None)
    )
    service = UpdateUnderwritingService(
        repository,
        market_service=FakeMarketService(),
        listings_service=FakeListingsService(),
        cleaned_data_service=FakeCleanedDataService(),
    )
    payload = UpdateUnderwritingPayload.model_validate(_details_with_purchase_only())

    await service.update(42, payload)

    underwriting_data = repository.update_kwargs["underwriting_data"]
    assert "mid_gross_revenue" not in underwriting_data
    assert "forecasted_revenue" not in repository.update_kwargs["detail_data"]
