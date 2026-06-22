from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)
from app.iron_bank.schemas.get_underwriting import (
    ConstructionAmenityOption,
    EditContextData,
    EditContextualData,
    GetUnderwritingEditContextResult,
    GetUnderwritingResult,
    GetUnderwritingsResult,
)


class StubService:
    """Thin stand-in for GetUnderwritingService used to test the controller."""

    def __init__(self, *, edit_context=None, get_all_result=None):
        self._edit_context = edit_context
        self._get_all_result = get_all_result

    async def get_edit_context(self, underwriting_id: int):
        if isinstance(self._edit_context, Exception):
            raise self._edit_context
        return self._edit_context

    async def get_all(self, *, page, page_size, zpid=None, market_id=None):
        if isinstance(self._get_all_result, Exception):
            raise self._get_all_result
        return self._get_all_result


def _edit_context_result(underwriting_id: int) -> GetUnderwritingEditContextResult:
    return GetUnderwritingEditContextResult(
        data=EditContextData(
            underwriting=GetUnderwritingResult(id=underwriting_id),
            contextual=EditContextualData(),
        )
    )


@pytest.mark.asyncio
async def test_get_underwritings_returns_500_on_failure():
    controller = GetUnderwritingController(
        StubService(get_all_result=RuntimeError("db unavailable"))
    )

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwritings(page=1, page_size=50)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch underwritings"


@pytest.mark.asyncio
async def test_get_underwritings_returns_service_result():
    expected = GetUnderwritingsResult(data=[], total=0, page=1, page_size=50, pages=0)
    controller = GetUnderwritingController(StubService(get_all_result=expected))

    result = await controller.get_underwritings(page=1, page_size=50)

    assert result is expected


@pytest.mark.asyncio
async def test_get_underwriting_returns_service_result():
    expected = _edit_context_result(1)
    controller = GetUnderwritingController(StubService(edit_context=expected))

    result = await controller.get_underwriting(1)

    assert result is expected


@pytest.mark.asyncio
async def test_get_underwriting_returns_404_when_missing():
    controller = GetUnderwritingController(
        StubService(edit_context=LookupError("Underwriting 999 not found"))
    )

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwriting(999)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Underwriting 999 not found"


@pytest.mark.asyncio
async def test_get_underwriting_returns_500_on_failure():
    controller = GetUnderwritingController(
        StubService(edit_context=RuntimeError("db unavailable"))
    )

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwriting(1)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch underwriting"


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
