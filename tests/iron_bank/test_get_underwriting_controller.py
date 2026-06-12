import pytest
from fastapi import HTTPException

from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)


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
