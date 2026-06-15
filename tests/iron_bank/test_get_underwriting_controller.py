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

from app.iron_bank.schemas.get_underwriting import GetUnderwritingResult  # noqa: E402


class StubUnderwritingService:
    async def get(self, underwriting_id: int):
        return GetUnderwritingResult(id=underwriting_id)


class StubConstructionAmenitiesService:
    async def get_all(self, **kwargs):
        return []


class StubConstructionRemodelingService:
    async def get_all(self, **kwargs):
        return []


@pytest.mark.asyncio
async def test_get_underwriting_edit_context_returns_combined_result():
    controller = GetUnderwritingController(
        StubUnderwritingService(),
        StubConstructionAmenitiesService(),
        StubConstructionRemodelingService(),
    )

    result = await controller.get_underwriting_edit_context(1)

    assert isinstance(result, GetUnderwritingEditContextResult)
    assert result.data.underwriting.id == 1
    assert result.data.contextual.construction_amenities == []
    assert result.data.contextual.construction_remodeling == []


@pytest.mark.asyncio
async def test_get_underwriting_edit_context_returns_404_when_missing():
    controller = GetUnderwritingController(
        MissingUnderwritingService(),
        StubConstructionAmenitiesService(),
        StubConstructionRemodelingService(),
    )

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
    )

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_underwriting_edit_context(1)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch underwriting edit context"
