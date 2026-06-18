import pytest
from fastapi import HTTPException

from app.iron_bank.controllers.update_underwriting_controller import (
    UpdateUnderwritingController,
)
from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.deal_status import UpdateDealStatusResult


class FakeUpdateUnderwritingService:
    async def update_deal_status(self, *, underwriting_id: int, deal_status: DealStatus):
        return UpdateDealStatusResult(
            underwriting_id=underwriting_id,
            deal_status=deal_status,
        )


class MissingUnderwritingService:
    async def update_deal_status(self, *, underwriting_id: int, deal_status: DealStatus):
        raise LookupError(f"Underwriting {underwriting_id} not found")


@pytest.mark.asyncio
async def test_update_deal_status_returns_updated_status():
    controller = UpdateUnderwritingController(FakeUpdateUnderwritingService())

    result = await controller.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.ANALYST_COMPLETED,
    )

    assert result.model_dump() == {
        "underwriting_id": 42,
        "deal_status": DealStatus.ANALYST_COMPLETED,
    }


@pytest.mark.asyncio
async def test_update_deal_status_returns_404_when_underwriting_is_missing():
    controller = UpdateUnderwritingController(MissingUnderwritingService())

    with pytest.raises(HTTPException) as exc_info:
        await controller.update_deal_status(
            underwriting_id=42,
            deal_status=DealStatus.ANALYST_COMPLETED,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Underwriting 42 not found"
