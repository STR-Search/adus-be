import pytest
from fastapi import HTTPException

from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)
from app.iron_bank.schemas.get_underwriting import GetUnderwritingEditContextResult


class MissingUnderwritingService:
    async def get(self, underwriting_id: int):
        raise LookupError(f"Underwriting {underwriting_id} not found")


@pytest.mark.asyncio
async def test_get_underwriting_controller_returns_404_when_missing():
    controller = GetUnderwritingController(MissingUnderwritingService())

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwriting(999)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Underwriting 999 not found"


class FailingListService:
    async def get_all(self, *, page: int, page_size: int):
        raise RuntimeError("db unavailable")


@pytest.mark.asyncio
async def test_get_underwritings_controller_returns_500_on_failure():
    controller = GetUnderwritingController(FailingListService())

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwritings(page=1, page_size=50)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch underwritings"


# --- edit context tests ---

from decimal import Decimal  # noqa: E402

from app.iron_bank.schemas.get_underwriting import GetUnderwritingResult  # noqa: E402
from app.markets.schemas.construction import ConstructionCostsAmenitiesSchema  # noqa: E402


class StubUnderwritingService:
    async def get(self, underwriting_id: int):
        return GetUnderwritingResult(id=underwriting_id, zpid="123", market_id=1)


class StubUnderwritingNoZpidService:
    async def get(self, underwriting_id: int):
        return GetUnderwritingResult(id=underwriting_id)


class StubConstructionAmenitiesService:
    async def get_all(self, **kwargs):
        return []


class StubConstructionRemodelingService:
    async def get_all(self, **kwargs):
        return []


class StubListing:
    beds = 3


class StubListingsService:
    async def get_by_zpid(self, zpid: str):
        return StubListing()


class StubOpexByBedrooms:
    furnishings_low = Decimal("1000")
    furnishings_high = Decimal("2000")


class StubOpexByBedroomsService:
    async def get_by_market_and_bedrooms(self, *, bedrooms: int, market_id: int):
        return StubOpexByBedrooms()


def _make_edit_context_controller(uw_service=None, listings_service=None, opex_service=None):
    return GetUnderwritingController(
        uw_service or StubUnderwritingService(),
        StubConstructionAmenitiesService(),
        StubConstructionRemodelingService(),
        listings_service or StubListingsService(),
        opex_service or StubOpexByBedroomsService(),
    )


@pytest.mark.asyncio
async def test_get_underwriting_edit_context_includes_furnishings_from_opex():
    controller = _make_edit_context_controller()

    result = await controller.get_underwriting_edit_context(1)

    assert isinstance(result, GetUnderwritingEditContextResult)
    assert result.data.underwriting.id == 1
    furnishings = result.data.contextual.construction_amenities[0]
    assert furnishings.amenity_name == "Furnishings"
    assert furnishings.price_tier_1 == Decimal("1000")
    assert furnishings.price_tier_3 == Decimal("2000")
    assert result.data.contextual.construction_remodeling == []


@pytest.mark.asyncio
async def test_get_underwriting_edit_context_furnishings_none_when_no_zpid():
    controller = _make_edit_context_controller(uw_service=StubUnderwritingNoZpidService())

    result = await controller.get_underwriting_edit_context(1)

    furnishings = result.data.contextual.construction_amenities[0]
    assert furnishings.amenity_name == "Furnishings"
    assert furnishings.price_tier_1 is None
    assert furnishings.price_tier_3 is None


@pytest.mark.asyncio
async def test_get_underwriting_edit_context_returns_404_when_missing():
    controller = _make_edit_context_controller(uw_service=MissingUnderwritingService())

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwriting_edit_context(999)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Underwriting 999 not found"


class FailingConstructionService:
    async def get_all(self, **kwargs):
        raise RuntimeError("db unavailable")


@pytest.mark.asyncio
async def test_get_underwriting_edit_context_returns_500_on_construction_failure():
    controller = GetUnderwritingController(
        StubUnderwritingService(),
        FailingConstructionService(),
        StubConstructionRemodelingService(),
        StubListingsService(),
        StubOpexByBedroomsService(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwriting_edit_context(1)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch underwriting edit context"
