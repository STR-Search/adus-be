from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.iron_bank.enums import DealStatus
from app.iron_bank.router import get_update_underwriting_controller, router
from app.iron_bank.schemas.deal_status import UpdateDealStatusResult


class FakeUpdateUnderwritingController:
    async def update_deal_status(
        self,
        *,
        underwriting_id: int,
        deal_status: DealStatus,
    ) -> UpdateDealStatusResult:
        return UpdateDealStatusResult(
            underwriting_id=underwriting_id,
            deal_status=deal_status,
        )


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_update_underwriting_controller] = (
        FakeUpdateUnderwritingController
    )
    return TestClient(app)


def test_update_deal_status_endpoint_returns_updated_status():
    response = build_client().patch(
        "/iron-bank/underwritings/42/deal-status",
        json={"deal_status": "analyst_completed"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "underwriting_id": 42,
        "deal_status": "analyst_completed",
    }


def test_update_deal_status_endpoint_rejects_invalid_status():
    response = build_client().patch(
        "/iron-bank/underwritings/42/deal-status",
        json={"deal_status": "not_real"},
    )

    assert response.status_code == 422
