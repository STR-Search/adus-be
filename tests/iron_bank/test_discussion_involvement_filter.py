"""Coverage for the ``involved_in_discussion`` filter on the underwritings list.

"Involved" means the current user wrote, or is mentioned in, a non-deleted
comment on the underwriting. The thread ids come from ``DiscussionService``
before the list query, so iron_bank only matches them against its link table.
These tests pin the param and the current user reaching the service on both
list paths, the resolved ids reaching the repository, and the SQL shapes.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.discussions.models import Comment, CommentMention
from app.core.discussions.repository import DiscussionRepository
from app.dependencies import get_current_user
from app.iron_bank.controllers.get_underwriting_controller import (
    GetUnderwritingController,
)
from app.iron_bank.repositories.underwriting_repository import (
    _discussion_involvement_condition,
)
from app.iron_bank.router import get_get_underwriting_controller, router
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingsQuery,
    GetUnderwritingsResult,
)
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService
from app.iron_bank.services.simulate_underwritings_service import (
    SimulateUnderwritingsService,
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


class RecordingRepository:
    def __init__(self):
        self.called_with = None

    async def get_all_paginated(self, **kwargs):
        self.called_with = kwargs
        return [], 0, 0

    async def get_simulation_inputs(self, **kwargs):
        self.called_with = kwargs
        return []

    async def get_by_ids(self, ids):
        return []


class FakeDiscussionService:
    def __init__(self, thread_ids: set[int]):
        self.thread_ids = thread_ids
        self.called_with = None

    async def get_involved_thread_ids(self, user_id: int) -> set[int]:
        self.called_with = user_id
        return self.thread_ids


def test_involved_in_discussion_is_an_optional_bool():
    field = GetUnderwritingsQuery.model_fields["involved_in_discussion"]

    assert field.annotation == bool | None
    assert field.default is None


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("involved_in_discussion=true", True),
        ("involved_in_discussion=false", False),
        ("", None),
    ],
)
def test_param_and_current_user_reach_the_controller(query, expected):
    response = build_client().get(f"/iron-bank/underwritings?{query}")

    assert response.status_code == 200
    assert captured["involved_in_discussion"] is expected
    assert captured["current_user_id"] == 99


def test_a_user_id_cannot_be_passed_in():
    """Always the authenticated user: a ``current_user_id`` param is ignored."""
    build_client().get(
        "/iron-bank/underwritings?involved_in_discussion=true&current_user_id=1"
    )

    assert captured["current_user_id"] == 99


@pytest.mark.asyncio
@pytest.mark.parametrize("simulating", [False, True])
async def test_controller_passes_it_through_on_both_paths(simulating):
    normal, simulation = RecordingService(), RecordingService()
    controller = GetUnderwritingController(normal, simulation)
    overrides = {"interest_rate": 0.069} if simulating else {}

    await controller.get_underwritings(
        page=1,
        page_size=20,
        involved_in_discussion=True,
        current_user_id=7,
        **overrides,
    )

    called = (simulation if simulating else normal).called_with
    assert called["involved_in_discussion"] is True
    assert called["current_user_id"] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_cls", "method"),
    [
        (GetUnderwritingService, "get_all"),
        (SimulateUnderwritingsService, "get_all_simulated"),
    ],
)
async def test_service_resolves_thread_ids_for_the_repository(service_cls, method):
    repository = RecordingRepository()
    discussions = FakeDiscussionService({3, 5})
    service = service_cls(repository, discussion_service=discussions)

    await getattr(service, method)(
        page=1, page_size=20, involved_in_discussion=False, current_user_id=7
    )

    assert discussions.called_with == 7
    assert repository.called_with["involved_in_discussion"] is False
    assert repository.called_with["involved_thread_ids"] == {3, 5}


@pytest.mark.asyncio
async def test_no_lookup_when_the_filter_is_omitted():
    repository = RecordingRepository()
    discussions = FakeDiscussionService({3})
    service = GetUnderwritingService(repository, discussion_service=discussions)

    await service.get_all(page=1, page_size=20, current_user_id=7)

    assert discussions.called_with is None
    assert repository.called_with["involved_thread_ids"] is None


@pytest.mark.asyncio
async def test_filter_without_a_user_is_an_error():
    service = GetUnderwritingService(
        RecordingRepository(), discussion_service=FakeDiscussionService(set())
    )

    with pytest.raises(ValueError):
        await service.get_all(page=1, page_size=20, involved_in_discussion=True)


def _sql(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_involved_matches_any_linked_thread():
    (condition,) = _discussion_involvement_condition(True, {3, 5})
    sql = _sql(condition)

    assert sql.startswith("EXISTS (SELECT")
    assert "iron_bank.underwriting_threads.underwriting_id = iron_bank.underwritings.id" in sql
    assert "iron_bank.underwriting_threads.thread_id IN (3, 5)" in sql


def test_not_involved_is_the_negation():
    (condition,) = _discussion_involvement_condition(False, {3})

    assert _sql(condition).startswith("NOT (EXISTS (SELECT")


def test_no_filter_produces_no_condition():
    assert _discussion_involvement_condition(None, {3}) == []


class CapturingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [4, 4, 9]))


@pytest.mark.asyncio
async def test_involvement_query_unions_authored_and_mentioned_live_comments():
    session = CapturingSession()

    thread_ids = await DiscussionRepository(session).get_involved_thread_ids(7)

    assert thread_ids == {4, 9}
    sql = _sql(session.statement)
    assert " UNION " in sql
    assert f"{Comment.__table__.fullname}.author_user_id = 7" in sql
    assert f"{CommentMention.__table__.fullname}.user_id = 7" in sql
    # Both branches ignore soft-deleted comments (mention rows survive a delete).
    assert sql.count("discussions.comments.deleted_at IS NULL") == 2
