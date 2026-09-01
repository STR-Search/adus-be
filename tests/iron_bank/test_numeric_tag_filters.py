"""Coverage for the graded (1-5) deal-tag filters on the underwritings list.

``renovation_level`` and ``deal_complexity`` are smallint columns with no CHECK
constraint, so the 1-5 bound exists only at the API boundary — these tests pin
that it rejects out-of-range levels with a 422 rather than passing them to SQL,
and that the filter behaves like the other tag filters otherwise.
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
from app.iron_bank.repositories.underwriting_repository import (
    _numeric_tag_conditions,
)
from app.iron_bank.router import get_get_underwriting_controller, router
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingsQuery,
    GetUnderwritingsResult,
)
from app.iron_bank.schemas.underwriting import (
    NUMERIC_TAG_FIELDS,
    NUMERIC_TAG_MAX,
    NUMERIC_TAG_MIN,
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
    def __init__(self):
        self.called_with = None

    async def _record(self, **kwargs):
        self.called_with = kwargs
        return GetUnderwritingsResult(data=[], total=0, page=1, page_size=20, pages=0)

    get_all = _record
    get_all_simulated = _record


def test_every_numeric_tag_is_exposed_as_a_query_param():
    fields = GetUnderwritingsQuery.model_fields
    missing = [field for field in NUMERIC_TAG_FIELDS if field not in fields]

    assert missing == []
    for field in NUMERIC_TAG_FIELDS:
        assert fields[field].default is None


@pytest.mark.parametrize("field", NUMERIC_TAG_FIELDS)
@pytest.mark.parametrize("level", range(NUMERIC_TAG_MIN, NUMERIC_TAG_MAX + 1))
def test_every_in_range_level_is_accepted(field, level):
    response = build_client().get(f"/iron-bank/underwritings?{field}={level}")

    assert response.status_code == 200
    assert captured[field] == [level]


@pytest.mark.parametrize("field", NUMERIC_TAG_FIELDS)
@pytest.mark.parametrize("level", ["0", "6", "-1", "99", "2.5", "high"])
def test_out_of_range_or_non_integer_levels_are_rejected(field, level):
    response = build_client().get(f"/iron-bank/underwritings?{field}={level}")

    assert response.status_code == 422


@pytest.mark.parametrize("field", NUMERIC_TAG_FIELDS)
def test_one_bad_level_rejects_the_whole_list(field):
    """A partially valid list must 422, not silently filter on the good half."""
    response = build_client().get(f"/iron-bank/underwritings?{field}=2,9")

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("deal_complexity=3", [3]),
        ("deal_complexity=1&deal_complexity=2", [1, 2]),
        ("deal_complexity=1,2,3", [1, 2, 3]),
        ("deal_complexity=", None),
        ("", None),
    ],
)
def test_levels_reach_the_controller_as_a_list_of_ints(query, expected):
    response = build_client().get(f"/iron-bank/underwritings?{query}")

    assert response.status_code == 200
    assert captured["deal_complexity"] == expected


def test_bounds_are_enforced_on_the_schema_itself():
    with pytest.raises(ValidationError):
        GetUnderwritingsQuery(page=1, page_size=20, renovation_level=[6])

    query = GetUnderwritingsQuery(page=1, page_size=20, renovation_level=[1, 5])
    assert query.renovation_level == [1, 5]


@pytest.mark.asyncio
async def test_controller_collapses_only_the_supplied_tags():
    service = RecordingService()
    controller = GetUnderwritingController(service)

    await controller.get_underwritings(
        page=1, page_size=20, renovation_level=[4], deal_complexity=[1, 2]
    )

    assert service.called_with["numeric_tags"] == {
        "renovation_level": [4],
        "deal_complexity": [1, 2],
    }


@pytest.mark.asyncio
async def test_simulated_path_carries_the_numeric_tags():
    normal, simulation = RecordingService(), RecordingService()
    controller = GetUnderwritingController(normal, simulation)

    await controller.get_underwritings(
        page=1, page_size=20, deal_complexity=[2], interest_rate=0.069
    )

    assert normal.called_with is None
    assert simulation.called_with["numeric_tags"] == {"deal_complexity": [2]}


def test_one_level_compiles_to_equality_and_several_to_in():
    (single,) = _numeric_tag_conditions({"deal_complexity": [3]})
    (multiple,) = _numeric_tag_conditions({"deal_complexity": [1, 2]})

    assert str(single.compile()) == (
        "iron_bank.underwritings.deal_complexity = :deal_complexity_1"
    )
    assert "IN " in str(multiple.compile())


def test_no_tags_produces_no_conditions():
    assert _numeric_tag_conditions(None) == []
    assert _numeric_tag_conditions({}) == []
    assert _numeric_tag_conditions({"deal_complexity": []}) == []
    assert _numeric_tag_conditions({"deal_complexity": None}) == []


def test_unknown_tag_name_raises():
    with pytest.raises(ValueError, match="Unknown numeric deal tag filter: bogus"):
        _numeric_tag_conditions({"bogus": [1]})


def test_boolean_and_single_select_tags_are_not_accepted_here():
    """Each tag family has its own allowed-field tuple; crossing them raises."""
    with pytest.raises(ValueError):
        _numeric_tag_conditions({"turnkey": [1]})
    with pytest.raises(ValueError):
        _numeric_tag_conditions({"pool_type": [1]})


def test_every_numeric_tag_builds_a_condition():
    conditions = _numeric_tag_conditions(
        {field: [1] for field in NUMERIC_TAG_FIELDS}
    )

    assert len(conditions) == len(NUMERIC_TAG_FIELDS)
