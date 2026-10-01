"""Coverage for the ``has_deal_pitch`` filter on the underwritings list.

The AI Overview is free text in ``deal_pitch``, not a flag, so "has one" means
non-blank text. These tests pin the param reaching the repository on both list
paths, and that NULL, empty and whitespace-only values all count as missing.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)
from app.iron_bank.repositories.underwriting_repository import _deal_pitch_condition
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


def test_has_deal_pitch_is_a_query_param_but_not_a_deal_tag():
    field = GetUnderwritingsQuery.model_fields["has_deal_pitch"]

    assert field.annotation == bool | None
    assert field.default is None
    assert "has_deal_pitch" not in BOOLEAN_TAG_FIELDS


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("has_deal_pitch=true", True),
        ("has_deal_pitch=false", False),
        ("", None),
    ],
)
def test_has_deal_pitch_reaches_the_controller(query, expected):
    response = build_client().get(f"/iron-bank/underwritings?{query}")

    assert response.status_code == 200
    assert captured["has_deal_pitch"] is expected


def test_non_boolean_value_is_rejected():
    response = build_client().get("/iron-bank/underwritings?has_deal_pitch=maybe")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_controller_passes_it_through_as_its_own_filter():
    service = RecordingService()
    controller = GetUnderwritingController(service)

    await controller.get_underwritings(page=1, page_size=20, has_deal_pitch=True)

    assert service.called_with["has_deal_pitch"] is True
    assert service.called_with["boolean_tags"] == {}


@pytest.mark.asyncio
async def test_simulated_path_carries_has_deal_pitch():
    """Text no financing override can move, so it must still filter under one."""
    normal, simulation = RecordingService(), RecordingService()
    controller = GetUnderwritingController(normal, simulation)

    await controller.get_underwritings(
        page=1, page_size=20, has_deal_pitch=False, interest_rate=0.069
    )

    assert normal.called_with is None
    assert simulation.called_with["has_deal_pitch"] is False


def test_present_requires_non_blank_text_and_missing_covers_null_and_blank():
    (present,) = _deal_pitch_condition(True)
    (missing,) = _deal_pitch_condition(False)

    assert str(present.compile()) == (
        "trim(iron_bank.underwritings.deal_pitch) != :trim_1"
    )
    assert str(missing.compile()) == (
        "iron_bank.underwritings.deal_pitch IS NULL "
        "OR trim(iron_bank.underwritings.deal_pitch) = :trim_1"
    )


def test_no_filter_produces_no_condition():
    assert _deal_pitch_condition(None) == []
