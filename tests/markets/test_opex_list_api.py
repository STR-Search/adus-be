"""Page-size contract and market ordering for the opex list endpoints."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.dependencies import get_current_user
from app.markets.repositories.opex_repository import (
    OpexByBedroomsRepository,
    OpexBySizeRepository,
)
from app.markets.router import get_bedrooms_controller, get_size_controller, router

captured: dict = {}


class FakeOpexController:
    async def get_paginated(self, **kwargs):
        captured.clear()
        captured.update(kwargs)
        return {"items": [], "total": 0, "pages": 0, "page": 1, "page_size": kwargs["page_size"]}


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_bedrooms_controller] = FakeOpexController
    app.dependency_overrides[get_size_controller] = FakeOpexController
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=99)
    return TestClient(app)


ENDPOINTS = ["/opex/bedrooms/", "/opex/size/"]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_page_size_defaults_to_25(path):
    response = build_client().get(path)

    assert response.status_code == 200
    assert captured["page_size"] == 25


@pytest.mark.parametrize("path", ENDPOINTS)
@pytest.mark.parametrize("size", [25, 50, 100])
def test_allowed_page_sizes_pass_through(path, size):
    response = build_client().get(f"{path}?page_size={size}")

    assert response.status_code == 200
    assert captured["page_size"] == size


@pytest.mark.parametrize("path", ENDPOINTS)
@pytest.mark.parametrize("size", [1, 10, 20, 200])
def test_other_page_sizes_are_rejected(path, size):
    response = build_client().get(f"{path}?page_size={size}")

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
    return sql.split("ORDER BY", 1)[1].split("LIMIT", 1)[0].strip()


@pytest.mark.asyncio
async def test_bedrooms_sort_by_market_slug_then_bedrooms():
    session = RecordingSession()
    await OpexByBedroomsRepository(session).get_paginated(page=1, page_size=25)

    assert _order_by_sql(session.statements[-1]) == (
        "markets.market_keys_master.market_slug ASC NULLS LAST, "
        "markets.opex_by_bedrooms.bedrooms ASC NULLS LAST, "
        "markets.opex_by_bedrooms.id"
    )


@pytest.mark.asyncio
async def test_size_sort_by_market_slug_then_sqft():
    session = RecordingSession()
    await OpexBySizeRepository(session).get_paginated(page=1, page_size=25)

    assert _order_by_sql(session.statements[-1]) == (
        "markets.market_keys_master.market_slug ASC NULLS LAST, "
        "markets.opex_by_size.sqft ASC NULLS LAST, "
        "markets.opex_by_size.id"
    )


@pytest.mark.asyncio
async def test_market_join_does_not_change_the_row_count_query():
    """The count wraps the joined query; it must still count opex rows only."""
    session = RecordingSession()
    await OpexByBedroomsRepository(session).get_paginated(page=1, page_size=25, market_id=7)

    count_sql = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "LEFT OUTER JOIN markets.market_keys_master" in count_sql
    assert "markets.opex_by_bedrooms.market_id = %(market_id_1)s" in count_sql
