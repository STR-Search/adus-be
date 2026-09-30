"""Page-size contract and name ordering for the markets list endpoints."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.dependencies import get_current_user
from app.markets.repositories.market_repository import MarketRepository
from app.markets.router import get_market_controller, router

captured: dict = {}


class FakeMarketController:
    async def get_paginated(self, **kwargs):
        captured.clear()
        captured.update(kwargs)
        return {"items": [], "total": 0, "pages": 0, "page": 1, "page_size": kwargs["page_size"]}


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_market_controller] = FakeMarketController
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=99)
    return TestClient(app)


def test_page_size_defaults_to_25():
    response = build_client().get("/markets/")

    assert response.status_code == 200
    assert captured["page_size"] == 25


@pytest.mark.parametrize("size", [25, 50, 100])
def test_allowed_page_sizes_pass_through(size):
    response = build_client().get(f"/markets/?page_size={size}")

    assert response.status_code == 200
    assert captured["page_size"] == size


@pytest.mark.parametrize("size", [1, 10, 20, 200])
def test_other_page_sizes_are_rejected(size):
    response = build_client().get(f"/markets/?page_size={size}")

    assert response.status_code == 422


class RecordingSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(
            scalar_one=lambda: 0,
            scalars=lambda: SimpleNamespace(all=lambda: []),
        )


def _order_by_sql(statement) -> str:
    sql = str(statement.compile(dialect=postgresql.dialect()))
    return sql.split("ORDER BY", 1)[1]


EXPECTED_ORDER = "lower(markets.market_keys_master.market_name) ASC NULLS LAST, markets.market_keys_master.id"


@pytest.mark.asyncio
async def test_paginated_markets_sort_by_name():
    session = RecordingSession()
    await MarketRepository(session).get_paginated(page=1, page_size=25)

    assert _order_by_sql(session.statements[-1]).strip().startswith(EXPECTED_ORDER)


@pytest.mark.asyncio
async def test_all_markets_sort_by_name():
    session = RecordingSession()
    await MarketRepository(session).get_all_summary()

    assert _order_by_sql(session.statements[-1]).strip().startswith(EXPECTED_ORDER)
