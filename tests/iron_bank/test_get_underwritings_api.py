"""HTTP-level coverage for the underwritings list query contract.

The schema tests exercise Pydantic directly; only a real request proves that
FastAPI collects repeated ``market_id`` params into the aliased ``market_ids``
field and that the router's ``**filters.model_dump()`` splat still lines up
with the controller signature.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.iron_bank.router import get_get_underwriting_controller, router
from app.iron_bank.schemas.get_underwriting import GetUnderwritingsResult

captured: dict = {}


class FakeGetUnderwritingController:
    async def get_underwritings(self, **kwargs) -> GetUnderwritingsResult:
        captured.clear()
        captured.update(kwargs)
        return GetUnderwritingsResult(data=[], total=0, page=1, page_size=20, pages=0)


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_get_underwriting_controller] = (
        FakeGetUnderwritingController
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=99)
    return TestClient(app)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # repeated params — the format the dashboard already sends
        ("market_id=1&market_id=4", [1, 4]),
        ("market_id=1,4", [1, 4]),
        ("market_id=3", [3]),
        ("market_id=", None),
        ("", None),
    ],
)
def test_market_id_reaches_the_controller_as_a_list(query, expected):
    response = build_client().get(f"/iron-bank/underwritings?{query}")

    assert response.status_code == 200
    assert captured["market_ids"] == expected


def test_multi_market_survives_alongside_the_simulation_overrides():
    """Market filtering is SQL-side on both list paths, so the simulated
    request must carry the same market_ids."""
    response = build_client().get(
        "/iron-bank/underwritings?market_id=1&market_id=4&interest_rate=0.069"
    )

    assert response.status_code == 200
    assert captured["market_ids"] == [1, 4]
    assert captured["interest_rate"] is not None


def test_non_numeric_market_id_is_rejected():
    response = build_client().get("/iron-bank/underwritings?market_id=abc")

    assert response.status_code == 422
