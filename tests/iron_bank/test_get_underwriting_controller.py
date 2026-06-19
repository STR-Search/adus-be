from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)
from app.iron_bank.schemas.get_underwriting import (
    ConstructionAmenityOption,
    GetUnderwritingDetails,
    GetUnderwritingEditContextResult,
    GetUnderwritingResult,
)


class MissingUnderwritingService:
    async def get(self, underwriting_id: int):
        raise LookupError(f"Underwriting {underwriting_id} not found")


class FailingListService:
    async def get_all(self, *, page: int, page_size: int):
        raise RuntimeError("db unavailable")


class StubUnderwritingService:
    async def get(self, underwriting_id: int):
        return GetUnderwritingResult(
            id=underwriting_id, zpid="123", market_id=1, is_automated=True
        )


class StubUnderwritingNoZpidService:
    async def get(self, underwriting_id: int):
        return GetUnderwritingResult(id=underwriting_id)


class StubConstructionAmenitiesService:
    async def get_all(self, **kwargs):
        return []


class StubConstructionRemodelingService:
    async def get_all(self, **kwargs):
        return []


class FailingConstructionService:
    async def get_all(self, **kwargs):
        raise RuntimeError("db unavailable")


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


def _make_controller(
    uw_service=None,
    listings_service=None,
    listing_details_service=None,
    opex_service=None,
):
    return GetUnderwritingController(
        uw_service or StubUnderwritingService(),
        StubConstructionAmenitiesService(),
        StubConstructionRemodelingService(),
        listings_service or StubListingsService(),
        listing_details_service or StubListingDetailsService(),
        opex_service or StubOpexByBedroomsService(),
    )


@pytest.mark.asyncio
async def test_get_underwritings_returns_500_on_failure():
    controller = GetUnderwritingController(FailingListService())

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwritings(page=1, page_size=50)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch underwritings"


@pytest.mark.asyncio
async def test_get_underwriting_returns_404_when_missing():
    controller = GetUnderwritingController(MissingUnderwritingService())

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwriting(999)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Underwriting 999 not found"


@pytest.mark.asyncio
async def test_get_underwriting_includes_furnishings_from_opex():
    controller = _make_controller()

    result = await controller.get_underwriting(1)

    assert isinstance(result, GetUnderwritingEditContextResult)
    assert result.data.underwriting.id == 1
    furnishings = result.data.contextual.construction_amenities[0]
    assert furnishings.amenity_name == "Furnishings"
    assert furnishings.price_tier_1 == Decimal("1000")
    assert furnishings.price_tier_3 == Decimal("2000")
    assert result.data.contextual.construction_remodeling == []


def test_construction_amenity_serializes_decimal_without_exponent_notation():
    amenity = ConstructionAmenityOption(
        id=4,
        amenity_name="Above Ground Pool WITH Deck",
        price_tier_1=Decimal("4E+4"),
        price_tier_2=Decimal("5E+4"),
        price_tier_3=Decimal("52500"),
    )

    assert amenity.model_dump(mode="json")["price_tier_1"] == "40000"
    assert amenity.model_dump(mode="json")["price_tier_2"] == "50000"
    assert amenity.model_dump_json().find("4E+4") == -1


@pytest.mark.asyncio
async def test_get_underwriting_includes_zillow_property():
    controller = _make_controller()

    result = await controller.get_underwriting(1)

    assert result.data.contextual.zillow_property.model_dump() == {
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


@pytest.mark.asyncio
async def test_get_underwriting_zillow_property_allows_missing_listing_details():
    controller = _make_controller(
        listing_details_service=MissingListingDetailsService()
    )

    result = await controller.get_underwriting(1)

    assert result.data.contextual.zillow_property.original_photos is None
    assert result.data.contextual.zillow_property.lot_size_sqft is None


class ExplodingListingsService:
    async def get_by_zpid(self, zpid: str):
        raise AssertionError("non-automated path must not query scheduled_listings")


class StubNonAutomatedUnderwritingService:
    async def get(self, underwriting_id: int):
        return GetUnderwritingResult(
            id=underwriting_id,
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


@pytest.mark.asyncio
async def test_get_underwriting_non_automated_reads_stored_zillow_property():
    controller = _make_controller(
        uw_service=StubNonAutomatedUnderwritingService(),
        listings_service=ExplodingListingsService(),
    )

    result = await controller.get_underwriting(1)

    zillow_property = result.data.contextual.zillow_property
    assert zillow_property.id == "copied-from-browser"
    assert zillow_property.bedrooms == 3
    assert zillow_property.price == Decimal("510000")
    # furnishings prices still resolve from opex via the stored bedrooms count
    furnishings = result.data.contextual.construction_amenities[0]
    assert furnishings.amenity_name == "Furnishings"
    assert furnishings.price_tier_1 == Decimal("1000")


@pytest.mark.asyncio
async def test_get_underwriting_furnishings_none_when_no_zpid():
    controller = _make_controller(uw_service=StubUnderwritingNoZpidService())

    result = await controller.get_underwriting(1)

    assert result.data.contextual.zillow_property is None
    furnishings = result.data.contextual.construction_amenities[0]
    assert furnishings.amenity_name == "Furnishings"
    assert furnishings.price_tier_1 is None
    assert furnishings.price_tier_3 is None


@pytest.mark.asyncio
async def test_get_underwriting_returns_500_on_construction_failure():
    controller = GetUnderwritingController(
        StubUnderwritingService(),
        FailingConstructionService(),
        StubConstructionRemodelingService(),
        StubListingsService(),
        StubListingDetailsService(),
        StubOpexByBedroomsService(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwriting(1)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch underwriting"
