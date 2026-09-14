"""Coverage for the ``property_pending`` filter on the underwritings list.

``property_pending`` is written by the Zillow listing sync, not by an analyst,
so it is deliberately *not* a member of ``BOOLEAN_TAG_FIELDS`` — it must stay
out of the tag picker that ``GET /boolean-tag-options`` drives. These tests pin
that separation, the param reaching the repository on both list paths, and the
NULL-tolerant meaning of ``false``.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)
from app.iron_bank.repositories.underwriting_repository import (
    _property_pending_condition,
)
from app.iron_bank.router import get_get_underwriting_controller, router
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingsQuery,
    GetUnderwritingsResult,
)
from app.iron_bank.schemas.underwriting import BOOLEAN_TAG_FIELDS

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


def test_property_pending_is_a_query_param_but_not_a_deal_tag():
    field = GetUnderwritingsQuery.model_fields["property_pending"]

    assert field.annotation == bool | None
    assert field.default is None
    # Membership here would put it in the tag picker, which it does not belong in.
    assert "property_pending" not in BOOLEAN_TAG_FIELDS


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("property_pending=true", True),
        ("property_pending=false", False),
        ("property_pending=1", True),
        ("property_pending=0", False),
        ("", None),
    ],
)
def test_property_pending_reaches_the_controller(query, expected):
    response = build_client().get(f"/iron-bank/underwritings?{query}")

    assert response.status_code == 200
    assert captured["property_pending"] is expected


def test_non_boolean_value_is_rejected():
    response = build_client().get("/iron-bank/underwritings?property_pending=maybe")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_controller_passes_it_through_as_its_own_filter():
    """It travels as a scalar, not inside the collapsed ``boolean_tags`` dict."""
    service = RecordingService()
    controller = GetUnderwritingController(service)

    await controller.get_underwritings(page=1, page_size=20, property_pending=True)

    assert service.called_with["property_pending"] is True
    assert service.called_with["boolean_tags"] == {}


@pytest.mark.asyncio
async def test_simulated_path_carries_property_pending():
    """A stored flag no override can move, so it must still filter under one."""
    normal, simulation = RecordingService(), RecordingService()
    controller = GetUnderwritingController(normal, simulation)

    await controller.get_underwritings(
        page=1, page_size=20, property_pending=False, interest_rate=0.069
    )

    assert normal.called_with is None
    assert simulation.called_with["property_pending"] is False


def test_true_matches_strictly_and_false_also_matches_null():
    """Rows predating the flag hold NULL; "not pending" has to include them."""
    (true_condition,) = _property_pending_condition(True)
    (false_condition,) = _property_pending_condition(False)

    assert str(true_condition.compile()) == (
        "iron_bank.underwritings.property_pending IS true"
    )
    assert str(false_condition.compile()) == (
        "iron_bank.underwritings.property_pending IS NOT true"
    )


def test_no_filter_produces_no_condition():
    assert _property_pending_condition(None) == []
