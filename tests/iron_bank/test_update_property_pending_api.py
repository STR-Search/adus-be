from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.iron_bank.router import get_update_underwriting_controller, router
from app.iron_bank.schemas.property_pending import UpdatePropertyPendingResult


class FakeUpdateUnderwritingController:
    async def update_property_pending(
        self,
        *,
        underwriting_id: int,
        property_pending: bool,
    ) -> UpdatePropertyPendingResult:
        return UpdatePropertyPendingResult(
            underwriting_id=underwriting_id,
            property_pending=property_pending,
        )


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_update_underwriting_controller] = (
        FakeUpdateUnderwritingController
    )
    return TestClient(app)


def test_update_property_pending_endpoint_returns_updated_flag():
    response = build_client().patch(
        "/iron-bank/underwritings/42/property-pending",
        json={"property_pending": True},
    )

    assert response.status_code == 200
    assert response.json() == {"underwriting_id": 42, "property_pending": True}


def test_update_property_pending_endpoint_accepts_false():
    response = build_client().patch(
        "/iron-bank/underwritings/42/property-pending",
        json={"property_pending": False},
    )

    assert response.status_code == 200
    assert response.json() == {"underwriting_id": 42, "property_pending": False}


def test_update_property_pending_endpoint_requires_the_flag():
    response = build_client().patch(
        "/iron-bank/underwritings/42/property-pending",
        json={},
    )

    assert response.status_code == 422


def test_update_property_pending_endpoint_rejects_extra_fields():
    response = build_client().patch(
        "/iron-bank/underwritings/42/property-pending",
        json={"property_pending": True, "deal_status": "maybe"},
    )

    assert response.status_code == 422
