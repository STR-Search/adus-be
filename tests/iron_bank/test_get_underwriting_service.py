from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingDetails,
    GetUnderwritingResult,
)
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
        **filters,
    ):
        self.requested_page = {
            "page": page,
            "page_size": page_size,
            **filters,
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

    assert repository.requested_page["page"] == 1
    assert repository.requested_page["page_size"] == 50
    assert repository.requested_page["zpid"] is None
    assert repository.requested_page["market_id"] is None
    assert result.total == 1
    assert result.page == 1
    assert result.page_size == 50
    assert result.pages == 1
    assert len(result.data) == 1
    assert result.data[0].id == 42
    assert result.data[0].taxes.tax_savings == Decimal("60100")


class FakeListRepository:
    def __init__(self, items):
        self.items = items

    async def get_all_paginated(self, *, page, page_size, **filters):
        return self.items, len(self.items), 1


class StubBatchListingsService:
    def __init__(self, listings):
        self.listings = listings
        self.requested_zpids = None

    async def get_by_zpids(self, zpids):
        self.requested_zpids = zpids
        return self.listings


class StubBatchListingDetailsService:
    def __init__(self, details):
        self.details = details

    async def get_by_zpids(self, zpids):
        return self.details


@pytest.mark.asyncio
async def test_get_all_batch_hydrates_automated_zillow_into_details():
    automated = _underwriting()
    automated.id = 7
    automated.is_automated = True
    automated.zpid = "123"
    automated.detail.zillow_property = None  # automated stores nothing

    non_automated = _underwriting()
    non_automated.id = 8
    non_automated.is_automated = False
    non_automated.zpid = "copied"
    non_automated.detail.zillow_property = {"id": "copied", "bedrooms": 9}
    listings_service = StubBatchListingsService({"123": StubListing()})
    details_service = StubBatchListingDetailsService(
        {
            "123": SimpleNamespace(
                original_photos=["https://photos.zillowstatic.com/photo-1.jpg"],
                lot_size_sqft=21780,
            )
        }
    )
    service = GetUnderwritingService(
        FakeListRepository([automated, non_automated]),
        listings_service=listings_service,
        listing_details_service=details_service,
    )

    result = await service.get_all(page=1, page_size=50)

    # only the automated item's zpid is batch-queried
    assert listings_service.requested_zpids == ["123"]
    # automated item hydrated live into details, coerced to the schema
    assert result.data[0].details.zillow_property.model_dump() == {
        "id": "123",
        "url": "https://www.zillow.com/homedetails/123",
        "thumbnail": "https://photos.zillowstatic.com/thumb.jpg",
        "price": Decimal("485000"),
        "address": "123 Pine Ridge Rd",
        "bedrooms": 3,
        "bathrooms": Decimal("2.5"),
        "area": 1800,
        "original_photos": ["https://photos.zillowstatic.com/photo-1.jpg"],
        "lot_size_sqft": Decimal("21780"),
    }
    # non-automated item keeps its stored zillow_property (coerced to schema)
    assert result.data[1].details.zillow_property.id == "copied"
    assert result.data[1].details.zillow_property.bedrooms == 9


@pytest.mark.asyncio
async def test_get_all_passes_filters_to_repository():
    repository = FakeUnderwritingRepository(_underwriting())
    service = GetUnderwritingService(repository)

    await service.get_all(
        page=1,
        page_size=20,
        zpid="12345",
        market_id=3,
        source="legacy_sheet",
        search="fort lauderdale",
    )

    expected = {
        "page": 1,
        "page_size": 20,
        "zpid": "12345",
        "market_id": 3,
        "source": "legacy_sheet",
        "search": "fort lauderdale",
    }
    for key, value in expected.items():
        assert repository.requested_page[key] == value


@pytest.mark.asyncio
async def test_get_all_returns_empty_page_when_no_underwritings():
    service = GetUnderwritingService(FakeUnderwritingRepository(None))

    result = await service.get_all(page=1, page_size=50)

    assert result.data == []
    assert result.total == 0
    assert result.pages == 0


# --- get_edit_context: zillow + furnishings orchestration -------------------


class StubListing:
    zpid = "123"
    detail_url = "https://www.zillow.com/homedetails/123"
    img_src = "https://photos.zillowstatic.com/thumb.jpg"
    price = Decimal("485000")
    address = "123 Pine Ridge Rd"
    beds = 3
    baths = Decimal("2.5")
    area = 1800


class StubListingsService:
    async def get_by_zpid(self, zpid: str):
        return StubListing()


class ExplodingListingsService:
    async def get_by_zpid(self, zpid: str):
        raise AssertionError("non-automated path must not query scheduled_listings")


class StubListingDetailsService:
    async def get_by_zpid(self, zpid: str):
        return SimpleNamespace(
            original_photos=["https://photos.zillowstatic.com/photo-1.jpg"],
            lot_size_sqft=21780,
        )


class MissingListingDetailsService:
    async def get_by_zpid(self, zpid: str):
        return None


class StubOpexByBedrooms:
    furnishings_low = Decimal("1000")
    furnishings_high = Decimal("2000")


class StubOpexByBedroomsService:
    async def get_by_market_and_bedrooms(self, *, bedrooms: int, market_id: int):
        return StubOpexByBedrooms()


class StubConstructionService:
    async def get_all(self, **kwargs):
        return []


def _make_service(
    underwriting: GetUnderwritingResult,
    *,
    listings_service=None,
    listing_details_service=None,
    opex_service=None,
):
    service = GetUnderwritingService(
        repository=None,
        listings_service=listings_service or StubListingsService(),
        listing_details_service=listing_details_service or StubListingDetailsService(),
        opex_by_bedrooms_service=opex_service or StubOpexByBedroomsService(),
        construction_amenities_service=StubConstructionService(),
        construction_remodeling_service=StubConstructionService(),
    )

    async def _get(underwriting_id: int):
        return underwriting

    service.get = _get
    return service


@pytest.mark.asyncio
async def test_get_edit_context_automated_hydrates_zillow_from_listing():
    underwriting = GetUnderwritingResult(
        id=1, zpid="123", market_id=1, is_automated=True
    )
    service = _make_service(underwriting)

    result = await service.get_edit_context(1)

    # zillow_property now lives on details, coerced to the ZillowProperty schema.
    assert result.data.underwriting.details.zillow_property.model_dump() == {
        "id": "123",
        "url": "https://www.zillow.com/homedetails/123",
        "thumbnail": "https://photos.zillowstatic.com/thumb.jpg",
        "price": Decimal("485000"),
        "address": "123 Pine Ridge Rd",
        "bedrooms": 3,
        "bathrooms": Decimal("2.5"),
        "area": 1800,
        "original_photos": ["https://photos.zillowstatic.com/photo-1.jpg"],
        "lot_size_sqft": Decimal("21780"),
    }
    furnishings = result.data.contextual.construction_amenities[0]
    assert furnishings.amenity_name == "Furnishings"
    assert furnishings.price_tier_1 == Decimal("1000")
    assert furnishings.price_tier_3 == Decimal("2000")


@pytest.mark.asyncio
async def test_get_edit_context_automated_allows_missing_listing_details():
    underwriting = GetUnderwritingResult(
        id=1, zpid="123", market_id=1, is_automated=True
    )
    service = _make_service(
        underwriting, listing_details_service=MissingListingDetailsService()
    )

    result = await service.get_edit_context(1)

    assert result.data.underwriting.details.zillow_property.original_photos is None
    assert result.data.underwriting.details.zillow_property.lot_size_sqft is None


@pytest.mark.asyncio
async def test_get_edit_context_non_automated_reads_stored_zillow_property():
    underwriting = GetUnderwritingResult(
        id=1,
        zpid="copied-from-browser",
        market_id=1,
        is_automated=False,
        details=GetUnderwritingDetails(
            zillow_property={
                "id": "copied-from-browser",
                "url": "https://www.zillow.com/homedetails/999",
                "address": "999 Manual Ln",
                "bedrooms": 3,
                "price": Decimal("510000"),
            }
        ),
    )
    # ExplodingListingsService proves the stored path never queries the listings.
    service = _make_service(underwriting, listings_service=ExplodingListingsService())

    result = await service.get_edit_context(1)

    zillow_property = result.data.underwriting.details.zillow_property
    assert zillow_property.id == "copied-from-browser"
    assert zillow_property.bedrooms == 3
    assert zillow_property.price == Decimal("510000")
    # furnishings still resolve from opex via the stored bedrooms count
    furnishings = result.data.contextual.construction_amenities[0]
    assert furnishings.amenity_name == "Furnishings"
    assert furnishings.price_tier_1 == Decimal("1000")


@pytest.mark.asyncio
async def test_get_edit_context_no_zpid_yields_no_zillow_property():
    underwriting = GetUnderwritingResult(id=1, is_automated=True)
    service = _make_service(underwriting)

    result = await service.get_edit_context(1)

    # no zpid → nothing hydrated, details stays absent
    assert result.data.underwriting.details is None
    furnishings = result.data.contextual.construction_amenities[0]
    assert furnishings.amenity_name == "Furnishings"
    assert furnishings.price_tier_1 is None
