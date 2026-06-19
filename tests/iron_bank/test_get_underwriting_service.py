from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.iron_bank.services.get_underwriting_service import GetUnderwritingService


class FakeUnderwritingRepository:
    def __init__(self, underwriting):
        self.underwriting = underwriting
        self.requested_id = None
        self.requested_page = None

    async def get_by_id(self, underwriting_id: int):
        self.requested_id = underwriting_id
        return self.underwriting

    async def get_all_paginated(
        self,
        *,
        page: int,
        page_size: int,
        zpid: str | None = None,
        market_id: int | None = None,
    ):
        self.requested_page = {
            "page": page,
            "page_size": page_size,
            "zpid": zpid,
            "market_id": market_id,
        }
        items = [self.underwriting] if self.underwriting is not None else []
        return items, len(items), 1 if items else 0


def _underwriting():
    return SimpleNamespace(
        id=42,
        market_id=3,
        purchase_price=Decimal("485000"),
        property_address="123 Pine Ridge Rd",
        property_pending=False,
        turnkey=True,
        furnished=True,
        luxury=False,
        tax_efficient=True,
        new_construction=False,
        existing_airbnb=True,
        arv=False,
        high_cash_on_cash=False,
        low_cash_on_cash=False,
        add_inground_pool=False,
        waterfront=False,
        remote=False,
        can_support_cohost=True,
        detail=SimpleNamespace(
            purchase_details={"purchase_price": 485000},
            y1_coc_incl_tax_savings={
                "low_pct": Decimal("0.632"),
                "mid_pct": Decimal("0.820"),
                "high_pct": Decimal("1.031"),
            },
            forecasted_revenue={
                "co_hosting_fee_pct": Decimal("0"),
                "annual_re_appreciation_pct": Decimal("0.04"),
                "scenarios": {
                    "low": {"forecasted_revenue": Decimal("72000")},
                    "mid": {"forecasted_revenue": Decimal("98000")},
                    "high": {"forecasted_revenue": Decimal("127000")},
                },
            },
            cleaning_cost={"monthly_cleaning_cost": 1540},
            zillow_property=None,
            analyst_notes="Existing hot tub and cabin aesthetic.",
        ),
        taxes=SimpleNamespace(
            land_assumptions_pct=Decimal("0.2"),
            sla_multiplier_pct=Decimal("0.36"),
            improvement_basis=Decimal("451200"),
            estimated_short_life_assets=Decimal("162432"),
            bonus_amount_pct=Decimal("1"),
            tax_rate_pct=Decimal("0.37"),
            y1_loss_from_depreciation=Decimal("162432"),
            tax_savings=Decimal("60100"),
        ),
        optimization_items=[
            SimpleNamespace(
                category="Flooring",
                total_price=Decimal("27000"),
                metric="sqft",
                base_price=Decimal("15"),
                spec="@$15/sqft x 1,800 sqft",
                tier="Mid",
            )
        ],
        operating_expenses=[
            SimpleNamespace(expense_name="Internet", monthly_amount=Decimal("100"))
        ],
        comp_set=[
            SimpleNamespace(
                listing_url="https://www.airbnb.com/rooms/1",
                revenue=Decimal("112400"),
                bedrooms=4,
                sleeps=10,
            )
        ],
    )


@pytest.mark.asyncio
async def test_get_underwriting_returns_save_shaped_aggregate():
    repository = FakeUnderwritingRepository(_underwriting())
    service = GetUnderwritingService(repository)

    result = await service.get(42)

    assert repository.requested_id == 42
    data = result.model_dump(by_alias=True)
    assert data["id"] == 42
    assert data["market_id"] == 3
    assert data["details"]["analyst_notes"] == ("Existing hot tub and cabin aesthetic.")
    assert data["details"]["y1_coc_incl_tax_savings"]["mid_pct"] == Decimal("0.820")
    assert data["taxes"]["tax_savings"] == Decimal("60100")
    assert data["taxes"]["sla_multiplier_pct"] == Decimal("0.36")
    assert data["optimization_list"] == [
        {
            "category": "Flooring",
            "total_price": Decimal("27000"),
            "metric": "sqft",
            "base_price": Decimal("15"),
            "spec": "@$15/sqft x 1,800 sqft",
            "tier": "Mid",
        }
    ]
    assert data["operating_expenses"] == [
        {"expense": "Internet", "monthly": Decimal("100")}
    ]
    assert data["comp_set"][0]["listing_url"] == "https://www.airbnb.com/rooms/1"


@pytest.mark.asyncio
async def test_get_underwriting_raises_lookup_error_when_missing():
    service = GetUnderwritingService(FakeUnderwritingRepository(None))

    with pytest.raises(LookupError):
        await service.get(999)


@pytest.mark.asyncio
async def test_get_all_returns_paginated_results():
    repository = FakeUnderwritingRepository(_underwriting())
    service = GetUnderwritingService(repository)

    result = await service.get_all(page=1, page_size=50)

    assert repository.requested_page == {
        "page": 1,
        "page_size": 50,
        "zpid": None,
        "market_id": None,
    }
    assert result.total == 1
    assert result.page == 1
    assert result.page_size == 50
    assert result.pages == 1
    assert len(result.data) == 1
    assert result.data[0].id == 42
    assert result.data[0].taxes.tax_savings == Decimal("60100")


@pytest.mark.asyncio
async def test_get_all_passes_filters_to_repository():
    repository = FakeUnderwritingRepository(_underwriting())
    service = GetUnderwritingService(repository)

    await service.get_all(page=1, page_size=20, zpid="12345", market_id=3)

    assert repository.requested_page == {
        "page": 1,
        "page_size": 20,
        "zpid": "12345",
        "market_id": 3,
    }


@pytest.mark.asyncio
async def test_get_all_returns_empty_page_when_no_underwritings():
    service = GetUnderwritingService(FakeUnderwritingRepository(None))

    result = await service.get_all(page=1, page_size=50)

    assert result.data == []
    assert result.total == 0
    assert result.pages == 0
