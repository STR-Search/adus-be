"""Coverage for the ``min_year_built`` / ``max_year_built`` range on the list.

Unlike the other numeric ranges, year built is not a column on
``underwritings``: it is read off the live listing in
``zillow.scheduled_listing_details`` through a correlated EXISTS on ``zpid``.
These tests pin that the pair validates like the other ranges, reaches the
repository on both list paths, and compiles to a single semi-join.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.dependencies import get_current_user
from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)
from app.iron_bank.models.underwriting import Underwriting
from app.iron_bank.repositories.underwriting_repository import (
    _listing_detail_conditions,
)
from app.iron_bank.router import get_get_underwriting_controller, router
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingsQuery,
    GetUnderwritingsResult,
)

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


class RecordingService:
    """Stands in for either list service and records the kwargs it received."""

    def __init__(self):
        self.called_with = None

    async def _record(self, **kwargs):
        self.called_with = kwargs
        return GetUnderwritingsResult(data=[], total=0, page=1, page_size=20, pages=0)

    get_all = _record
    get_all_simulated = _record


def _compile(condition) -> str:
    return str(
        select(Underwriting.id)
        .where(condition)
        .compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


# --- schema -----------------------------------------------------------------


def test_bounds_reject_inverted_range():
    with pytest.raises(ValidationError) as excinfo:
        GetUnderwritingsQuery(min_year_built=2000, max_year_built=1990)

    assert "min_year_built must be less than or equal to max_year_built" in str(
        excinfo.value
    )


def test_bounds_accept_equal_min_and_max():
    query = GetUnderwritingsQuery(min_year_built=1978, max_year_built=1978)

    assert (query.min_year_built, query.max_year_built) == (1978, 1978)


# --- HTTP boundary ----------------------------------------------------------


def test_range_params_reach_the_controller():
    response = build_client().get(
        "/iron-bank/underwritings?min_year_built=1990&max_year_built=2010"
    )

    assert response.status_code == 200
    assert captured["min_year_built"] == 1990
    assert captured["max_year_built"] == 2010


@pytest.mark.parametrize(
    "query",
    [
        "min_year_built=2010&max_year_built=1990",
        "min_year_built=19.5",
        "max_year_built=-1",
        "min_year_built=old",
    ],
)
def test_bad_bounds_are_a_422(query):
    response = build_client().get(f"/iron-bank/underwritings?{query}")

    assert response.status_code == 422


# --- controller -------------------------------------------------------------


@pytest.mark.asyncio
async def test_controller_passes_the_pair_through():
    service = RecordingService()
    controller = GetUnderwritingController(service)

    await controller.get_underwritings(
        page=1, page_size=20, min_year_built=1990, max_year_built=2010
    )

    assert service.called_with["min_year_built"] == 1990
    assert service.called_with["max_year_built"] == 2010


@pytest.mark.asyncio
async def test_simulated_path_carries_the_pair():
    """Year built is a listing fact no override moves, so it must survive."""
    normal, simulation = RecordingService(), RecordingService()
    controller = GetUnderwritingController(normal, simulation)

    await controller.get_underwritings(
        page=1, page_size=20, min_year_built=1990, interest_rate=0.069
    )

    assert normal.called_with is None
    assert simulation.called_with["min_year_built"] == 1990
    assert simulation.called_with["max_year_built"] is None


# --- repository helper ------------------------------------------------------


def test_no_bounds_emits_nothing():
    assert _listing_detail_conditions(None, None) == []


def test_bounds_compile_to_one_correlated_exists_on_zpid():
    (condition,) = _listing_detail_conditions(1990, 2010)

    sql = _compile(condition)

    assert sql.count("EXISTS") == 1
    assert "zillow.scheduled_listing_details" in sql
    assert (
        "zillow.scheduled_listing_details.zpid = iron_bank.underwritings.zpid" in sql
    )
    assert "zillow.scheduled_listing_details.year_built >= 1990" in sql
    assert "zillow.scheduled_listing_details.year_built <= 2010" in sql


def test_one_bound_alone_is_an_open_range():
    (condition,) = _listing_detail_conditions(None, 2010)

    sql = _compile(condition)

    assert "year_built <= 2010" in sql
    assert ">=" not in sql
