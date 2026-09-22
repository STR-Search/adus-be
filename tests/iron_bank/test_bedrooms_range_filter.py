"""Coverage for the ``min_bedrooms`` / ``max_bedrooms`` range on the list.

Bedrooms used to be the one numeric filter matched with ``==`` via a single
``bedrooms`` param. It now follows the same min/max contract as purchase price
and cash needed. The old param is gone, not aliased — these tests pin that the
new pair reaches the repository on both list paths, that the bounds validate
like the other ranges, and that the SQL helper is inclusive at both ends.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.dependencies import get_current_user
from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)
from app.iron_bank.models.underwriting import Underwriting
from app.iron_bank.repositories.underwriting_repository import (
    _numeric_range_conditions,
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


# --- schema -----------------------------------------------------------------


def test_bedrooms_is_a_min_max_pair_of_optional_ints():
    fields = GetUnderwritingsQuery.model_fields

    assert "bedrooms" not in fields
    for name in ("min_bedrooms", "max_bedrooms"):
        assert fields[name].annotation == int | None
        assert fields[name].default is None


def test_bounds_accept_min_below_max():
    query = GetUnderwritingsQuery(min_bedrooms=2, max_bedrooms=4)

    assert (query.min_bedrooms, query.max_bedrooms) == (2, 4)


def test_bounds_accept_equal_min_and_max():
    """Both ends inclusive, so min == max is "exactly this many"."""
    query = GetUnderwritingsQuery(min_bedrooms=3, max_bedrooms=3)

    assert (query.min_bedrooms, query.max_bedrooms) == (3, 3)


def test_bounds_reject_inverted_range():
    with pytest.raises(ValidationError) as excinfo:
        GetUnderwritingsQuery(min_bedrooms=5, max_bedrooms=2)

    assert "min_bedrooms must be less than or equal to max_bedrooms" in str(
        excinfo.value
    )


def test_one_bound_alone_is_an_open_range():
    assert GetUnderwritingsQuery(min_bedrooms=4).max_bedrooms is None
    assert GetUnderwritingsQuery(max_bedrooms=2).min_bedrooms is None


@pytest.mark.parametrize("name", ["min_bedrooms", "max_bedrooms"])
def test_negative_bound_is_rejected(name):
    with pytest.raises(ValidationError):
        GetUnderwritingsQuery(**{name: -1})


# --- HTTP boundary ----------------------------------------------------------


def test_range_params_reach_the_controller():
    response = build_client().get(
        "/iron-bank/underwritings?min_bedrooms=2&max_bedrooms=4"
    )

    assert response.status_code == 200
    assert captured["min_bedrooms"] == 2
    assert captured["max_bedrooms"] == 4


def test_legacy_single_value_param_is_not_a_filter():
    """Hard swap: ``bedrooms=3`` is an unknown param, ignored rather than aliased."""
    response = build_client().get("/iron-bank/underwritings?bedrooms=3")

    assert response.status_code == 200
    assert "bedrooms" not in captured
    assert captured["min_bedrooms"] is None
    assert captured["max_bedrooms"] is None


@pytest.mark.parametrize(
    "query",
    [
        "min_bedrooms=5&max_bedrooms=2",
        "min_bedrooms=2.5",
        "max_bedrooms=-1",
        "min_bedrooms=three",
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
        page=1, page_size=20, min_bedrooms=2, max_bedrooms=4
    )

    assert service.called_with["min_bedrooms"] == 2
    assert service.called_with["max_bedrooms"] == 4


@pytest.mark.asyncio
async def test_simulated_path_carries_the_pair():
    """Bedrooms is stored, not derived, so an override must not drop the filter."""
    normal, simulation = RecordingService(), RecordingService()
    controller = GetUnderwritingController(normal, simulation)

    await controller.get_underwritings(
        page=1, page_size=20, min_bedrooms=3, interest_rate=0.069
    )

    assert normal.called_with is None
    assert simulation.called_with["min_bedrooms"] == 3
    assert simulation.called_with["max_bedrooms"] is None


# --- repository helper ------------------------------------------------------


def test_numeric_range_is_inclusive_at_both_ends():
    lower, upper = _numeric_range_conditions(Underwriting.bedrooms, 2, 4)

    assert str(lower.compile()) == "iron_bank.underwritings.bedrooms >= :bedrooms_1"
    assert str(upper.compile()) == "iron_bank.underwritings.bedrooms <= :bedrooms_1"


def test_numeric_range_with_one_bound_emits_one_condition():
    (only,) = _numeric_range_conditions(Underwriting.bedrooms, None, 4)

    assert str(only.compile()) == "iron_bank.underwritings.bedrooms <= :bedrooms_1"


def test_numeric_range_with_no_bounds_emits_nothing():
    assert _numeric_range_conditions(Underwriting.bedrooms, None, None) == []
