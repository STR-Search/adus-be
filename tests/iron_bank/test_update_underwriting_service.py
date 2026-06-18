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

    async def update(self, underwriting_id: int, **kwargs):
        self.update_kwargs = {"underwriting_id": underwriting_id, **kwargs}
        return self.underwriting


@pytest.mark.asyncio
async def test_reconcile_purchase_price_updates_only_price_dependent_data():
    repository = FakeUnderwritingRepository()
    service = UpdateUnderwritingService(repository)
    payload = SaveUnderwritingPayload.model_validate(
        {
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
async def test_update_raises_lookup_error_when_underwriting_does_not_exist():
    repository = FakeUnderwritingRepository(underwriting=None)
    service = UpdateUnderwritingService(repository)
    payload = UpdateUnderwritingPayload.model_validate({"purchase_price": 125000})

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
