"""Coverage for the boolean deal-tag filters on the underwritings list.

The tags are plain stored flags, so they filter in SQL on *both* list paths.
These tests pin the three things that could silently rot: the query params
reaching the controller, the collapsed ``boolean_tags`` dict reaching the
repository on the normal and the simulated path alike, and the NULL-tolerant
meaning of ``false``.
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
    _boolean_tag_conditions,
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


def test_every_boolean_tag_is_exposed_as_a_query_param():
    """The canonical tuple and the endpoint contract must not drift."""
    fields = GetUnderwritingsQuery.model_fields
    missing = [field for field in BOOLEAN_TAG_FIELDS if field not in fields]

    assert missing == []
    for field in BOOLEAN_TAG_FIELDS:
        assert fields[field].annotation == bool | None
        assert fields[field].default is None


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("turnkey=true", True),
        ("turnkey=false", False),
        ("turnkey=1", True),
        ("", None),
    ],
)
def test_boolean_tag_reaches_the_controller(query, expected):
    response = build_client().get(f"/iron-bank/underwritings?{query}")

    assert response.status_code == 200
    assert captured["turnkey"] is expected


def test_non_boolean_tag_value_is_rejected():
    response = build_client().get("/iron-bank/underwritings?waterfront=maybe")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_controller_collapses_only_the_supplied_tags():
    """Omitted tags must not appear at all — an absent tag is not ``false``."""
    service = RecordingService()
    controller = GetUnderwritingController(service)

    await controller.get_underwritings(
        page=1, page_size=20, turnkey=True, furnished=False
    )

    assert service.called_with["boolean_tags"] == {
        "turnkey": True,
        "furnished": False,
    }


@pytest.mark.asyncio
async def test_simulated_path_carries_the_boolean_tags():
    """Stored flags survive simulation, so the simulated request filters on
    them too — otherwise a tag silently stopped applying under an override."""
    normal, simulation = RecordingService(), RecordingService()
    controller = GetUnderwritingController(normal, simulation)

    await controller.get_underwritings(
        page=1, page_size=20, luxury=True, interest_rate=0.069
    )

    assert normal.called_with is None
    assert simulation.called_with["boolean_tags"] == {"luxury": True}


def test_true_matches_strictly_and_false_also_matches_null():
    """The columns are nullable with a Python-side default, so pre-existing and
    backfilled rows hold NULL; "unflagged" has to include them."""
    (true_condition,) = _boolean_tag_conditions({"turnkey": True})
    (false_condition,) = _boolean_tag_conditions({"turnkey": False})

    assert str(true_condition.compile()) == (
        "iron_bank.underwritings.turnkey IS true"
    )
    assert str(false_condition.compile()) == (
        "iron_bank.underwritings.turnkey IS NOT true"
    )


def test_no_tags_produces_no_conditions():
    assert _boolean_tag_conditions(None) == []
    assert _boolean_tag_conditions({}) == []
    assert _boolean_tag_conditions({"turnkey": None}) == []


def test_unknown_tag_name_raises():
    with pytest.raises(ValueError, match="Unknown boolean deal tag filter: bogus"):
        _boolean_tag_conditions({"bogus": True})


def test_every_boolean_tag_builds_a_condition():
    """Guards against a name in the tuple that is not actually a column."""
    conditions = _boolean_tag_conditions(dict.fromkeys(BOOLEAN_TAG_FIELDS, True))

    assert len(conditions) == len(BOOLEAN_TAG_FIELDS)
