"""Coverage for the multi-select (``text[]``) deal-tag filters.

These use ANY/overlap semantics: a deal matches if it carries at least one of
the requested keys. The chosen operator is the whole product decision here, so
it is pinned at the SQL level and end-to-end.
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
    _multi_select_tag_conditions,
)
from app.iron_bank.router import get_get_underwriting_controller, router
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingsQuery,
    GetUnderwritingsResult,
)
from app.iron_bank.schemas.underwriting import MULTI_SELECT_TAG_FIELDS

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


def test_every_multi_select_tag_is_exposed_as_a_query_param():
    fields = GetUnderwritingsQuery.model_fields
    missing = [field for field in MULTI_SELECT_TAG_FIELDS if field not in fields]

    assert missing == []
    for field in MULTI_SELECT_TAG_FIELDS:
        assert fields[field].annotation == list[str] | None
        assert fields[field].default is None


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("seasonality=feb", ["feb"]),
        ("seasonality=feb&seasonality=jun", ["feb", "jun"]),
        ("seasonality=feb,jun", ["feb", "jun"]),
        ("seasonality=", None),
        ("", None),
    ],
)
def test_keys_reach_the_controller_as_a_list(query, expected):
    response = build_client().get(f"/iron-bank/underwritings?{query}")

    assert response.status_code == 200
    assert captured["seasonality"] == expected


@pytest.mark.asyncio
async def test_controller_collapses_only_the_supplied_tags():
    service = RecordingService()
    controller = GetUnderwritingController(service)

    await controller.get_underwritings(
        page=1,
        page_size=20,
        seasonality=["feb", "jun"],
        market_type=["lake"],
    )

    assert service.called_with["multi_select_tags"] == {
        "seasonality": ["feb", "jun"],
        "market_type": ["lake"],
    }


@pytest.mark.asyncio
async def test_simulated_path_carries_the_multi_select_tags():
    normal, simulation = RecordingService(), RecordingService()
    controller = GetUnderwritingController(normal, simulation)

    await controller.get_underwritings(
        page=1, page_size=20, core_value_driver=["views"], interest_rate=0.069
    )

    assert normal.called_with is None
    assert simulation.called_with["multi_select_tags"] == {
        "core_value_driver": ["views"]
    }


def test_any_semantics_compile_to_the_overlap_operator():
    """`&&` is the product decision: at least one shared key. `@>` ("all of")
    or `<@` ("only these") would be a different filter entirely."""
    (condition,) = _multi_select_tag_conditions({"seasonality": ["feb", "jun"]})
    compiled = condition.compile()

    assert str(compiled) == "iron_bank.underwritings.seasonality && :seasonality_1"
    assert list(compiled.params.values()) == [["feb", "jun"]]


def test_a_single_key_still_uses_overlap():
    """One key must not degrade into array equality — a deal tagged
    [jan, feb, mar] has to match seasonality=feb."""
    (condition,) = _multi_select_tag_conditions({"seasonality": ["feb"]})

    assert "&&" in str(condition.compile())
    assert " = " not in str(condition.compile())


def test_no_tags_produces_no_conditions():
    assert _multi_select_tag_conditions(None) == []
    assert _multi_select_tag_conditions({}) == []
    assert _multi_select_tag_conditions({"seasonality": []}) == []
    assert _multi_select_tag_conditions({"seasonality": None}) == []


def test_unknown_tag_name_raises():
    with pytest.raises(
        ValueError, match="Unknown multi-select deal tag filter: bogus"
    ):
        _multi_select_tag_conditions({"bogus": ["x"]})


def test_single_select_tags_are_rejected_here():
    """pool_type is a scalar varchar; `&&` against it would be invalid SQL."""
    with pytest.raises(ValueError):
        _multi_select_tag_conditions({"pool_type": ["in_ground"]})


def test_every_multi_select_tag_builds_a_condition():
    conditions = _multi_select_tag_conditions(
        {field: ["x"] for field in MULTI_SELECT_TAG_FIELDS}
    )

    assert len(conditions) == len(MULTI_SELECT_TAG_FIELDS)


def test_columns_expose_the_array_operators():
    """The model must use the postgresql ARRAY type, not the generic one —
    only the former carries .overlap(). Same DDL, so nothing to migrate."""
    from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY

    from app.iron_bank.models import Underwriting

    for field in MULTI_SELECT_TAG_FIELDS:
        column = getattr(Underwriting, field)
        assert isinstance(column.type, PG_ARRAY)
