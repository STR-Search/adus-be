"""Coverage for the single-select deal-tag filters on the underwritings list.

The frontend sends reference-data *keys* (the slug stored on the column), so
these are plain equality/IN comparisons. What needs pinning: keys survive the
trip as a list, several values for one tag OR together, the literal ``none``
key of ``pool_type`` is never mistaken for "no filter", and the simulated path
filters on them too.
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
    _single_select_tag_conditions,
)
from app.iron_bank.router import get_get_underwriting_controller, router
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingsQuery,
    GetUnderwritingsResult,
)
from app.iron_bank.schemas.underwriting import SINGLE_SELECT_TAG_FIELDS

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
    def __init__(self):
        self.called_with = None

    async def _record(self, **kwargs):
        self.called_with = kwargs
        return GetUnderwritingsResult(data=[], total=0, page=1, page_size=20, pages=0)

    get_all = _record
    get_all_simulated = _record


def test_every_single_select_tag_is_exposed_as_a_query_param():
    fields = GetUnderwritingsQuery.model_fields
    missing = [field for field in SINGLE_SELECT_TAG_FIELDS if field not in fields]

    assert missing == []
    for field in SINGLE_SELECT_TAG_FIELDS:
        assert fields[field].annotation == list[str] | None
        assert fields[field].default is None


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # repeated and comma-separated, same as market_id already accepts
        ("pool_type=in_ground", ["in_ground"]),
        ("pool_type=in_ground&pool_type=above_ground", ["in_ground", "above_ground"]),
        ("pool_type=in_ground,above_ground", ["in_ground", "above_ground"]),
        ("pool_type=", None),
        ("", None),
        # 'none' is a real pool_type key meaning "no pool", not an absent filter
        ("pool_type=none", ["none"]),
    ],
)
def test_tag_keys_reach_the_controller_as_a_list(query, expected):
    response = build_client().get(f"/iron-bank/underwritings?{query}")

    assert response.status_code == 200
    assert captured["pool_type"] == expected


@pytest.mark.asyncio
async def test_controller_collapses_only_the_supplied_tags():
    service = RecordingService()
    controller = GetUnderwritingController(service)

    await controller.get_underwritings(
        page=1,
        page_size=20,
        execution_type=["light"],
        cash_flow_quality=["mid", "high"],
    )

    assert service.called_with["single_select_tags"] == {
        "execution_type": ["light"],
        "cash_flow_quality": ["mid", "high"],
    }


@pytest.mark.asyncio
async def test_simulated_path_carries_the_single_select_tags():
    normal, simulation = RecordingService(), RecordingService()
    controller = GetUnderwritingController(normal, simulation)

    await controller.get_underwritings(
        page=1, page_size=20, view_quality=["ocean"], interest_rate=0.069
    )

    assert normal.called_with is None
    assert simulation.called_with["single_select_tags"] == {"view_quality": ["ocean"]}


def test_one_value_compiles_to_equality_and_several_to_in():
    (single,) = _single_select_tag_conditions({"pool_type": ["in_ground"]})
    (multiple,) = _single_select_tag_conditions(
        {"pool_type": ["in_ground", "above_ground"]}
    )

    assert str(single.compile()) == "iron_bank.underwritings.pool_type = :pool_type_1"
    assert "IN " in str(multiple.compile())


def test_values_are_bound_not_interpolated():
    """Tag keys are caller-supplied strings, so they must travel as bind params."""
    (condition,) = _single_select_tag_conditions({"pool_type": ["'; drop table x --"]})
    compiled = condition.compile()

    assert "drop table" not in str(compiled)
    assert list(compiled.params.values()) == ["'; drop table x --"]


def test_no_tags_produces_no_conditions():
    assert _single_select_tag_conditions(None) == []
    assert _single_select_tag_conditions({}) == []
    assert _single_select_tag_conditions({"pool_type": []}) == []
    assert _single_select_tag_conditions({"pool_type": None}) == []


def test_unknown_tag_name_raises():
    with pytest.raises(
        ValueError, match="Unknown single-select deal tag filter: bogus"
    ):
        _single_select_tag_conditions({"bogus": ["x"]})


def test_every_single_select_tag_builds_a_condition():
    """Guards against a name in the tuple that is not actually a column."""
    conditions = _single_select_tag_conditions(
        {field: ["x"] for field in SINGLE_SELECT_TAG_FIELDS}
    )

    assert len(conditions) == len(SINGLE_SELECT_TAG_FIELDS)


def test_multi_select_tags_are_not_filterable_yet():
    """market_type/seasonality/core_value_driver are text[] columns needing
    overlap semantics, deliberately out of scope here — fail loudly if one is
    wired in without the array handling."""
    with pytest.raises(ValueError):
        _single_select_tag_conditions({"market_type": ["lake"]})
