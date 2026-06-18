from types import SimpleNamespace

import pytest

from app.iron_bank.enums import DealStatus
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

    async def update(self, underwriting_id: int, **kwargs):
        self.update_kwargs = {"underwriting_id": underwriting_id, **kwargs}
        return self.underwriting


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
async def test_update_raises_lookup_error_when_underwriting_does_not_exist():
    repository = FakeUnderwritingRepository(underwriting=None)
    service = UpdateUnderwritingService(repository)
    payload = UpdateUnderwritingPayload.model_validate(
        {"purchase_price": 125000}
    )

    with pytest.raises(LookupError, match="Underwriting 42 not found"):
        await service.update(42, payload)


@pytest.mark.asyncio
async def test_update_deal_status_updates_only_deal_status():
    repository = FakeUnderwritingRepository(
        underwriting=SimpleNamespace(
            id=42,
            deal_status=DealStatus.ANALYST_COMPLETED,
        )
    )
    service = UpdateUnderwritingService(repository)

    result = await service.update_deal_status(
        underwriting_id=42,
        deal_status=DealStatus.ANALYST_COMPLETED,
    )

    assert result.model_dump() == {
        "underwriting_id": 42,
        "deal_status": DealStatus.ANALYST_COMPLETED,
    }
    assert repository.update_kwargs == {
        "underwriting_id": 42,
        "underwriting_data": {
            "deal_status": DealStatus.ANALYST_COMPLETED,
        },
    }


@pytest.mark.asyncio
async def test_update_deal_status_raises_when_underwriting_does_not_exist():
    service = UpdateUnderwritingService(FakeUnderwritingRepository(underwriting=None))

    with pytest.raises(LookupError, match="Underwriting 42 not found"):
        await service.update_deal_status(
            underwriting_id=42,
            deal_status=DealStatus.ANALYST_COMPLETED,
        )
