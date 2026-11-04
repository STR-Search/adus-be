from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.iron_bank.router import get_update_underwriting_controller, router
from app.iron_bank.schemas.off_market import UpdateOffMarketResult


class FakeUpdateUnderwritingController:
    async def update_off_market(
        self,
        *,
        underwriting_id: int,
        off_market: bool,
    ) -> UpdateOffMarketResult:
        return UpdateOffMarketResult(
            underwriting_id=underwriting_id,
            off_market=off_market,
        )


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_update_underwriting_controller] = (
        FakeUpdateUnderwritingController
    )
    return TestClient(app)


def test_update_off_market_endpoint_returns_updated_flag():
    response = build_client().patch(
        "/iron-bank/underwritings/42/off-market",
        json={"off_market": True},
    )

    assert response.status_code == 200
    assert response.json() == {"underwriting_id": 42, "off_market": True}


def test_update_off_market_endpoint_accepts_false():
    response = build_client().patch(
        "/iron-bank/underwritings/42/off-market",
        json={"off_market": False},
    )

    assert response.status_code == 200
    assert response.json() == {"underwriting_id": 42, "off_market": False}


def test_update_off_market_endpoint_requires_the_flag():
    response = build_client().patch(
        "/iron-bank/underwritings/42/off-market",
        json={},
    )

    assert response.status_code == 422


def test_update_off_market_endpoint_rejects_extra_fields():
    response = build_client().patch(
        "/iron-bank/underwritings/42/off-market",
        json={"off_market": True, "property_pending": True},
    )

    assert response.status_code == 422
