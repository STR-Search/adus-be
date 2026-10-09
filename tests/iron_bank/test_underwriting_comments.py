"""Underwriting comments: lazy thread creation, routes, and error mapping.

Runs the real iron_bank service/controller and the real DiscussionService
over in-memory repositories.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.discussions.body.errors import InvalidBodyError
from app.core.discussions.enums import SubjectType
from app.core.discussions.exceptions import RepliesNotSupportedError
from app.core.discussions.schemas import CreateCommentRequest
from app.core.discussions.service import DiscussionService
from app.dependencies import get_current_user
from app.iron_bank.controllers.underwriting_comment_controller import (
    UnderwritingCommentController,
)
from app.iron_bank.router import get_underwriting_comment_controller, router
from app.iron_bank.services.underwriting_discussion_service import (
    UnderwritingDiscussionService,
    UnderwritingNotFoundError,
)
from tests.core.discussions.conftest import (
    GONE,
    JANE,
    SAM,
    FakeDiscussionRepository,
    FakeUserLookup,
    doc,
    mention,
    para,
    text,
)

UW = 501


class FakeUnderwritingRepository:
    def __init__(self, ids):
        self.ids = set(ids)

    async def exists(self, underwriting_id):
        return underwriting_id in self.ids


class FakeThreadRepository:
    def __init__(self):
        self.links: dict[tuple[int, str], int] = {}
        # Runs inside insert_link, before the conflict check: simulates a
        # concurrent transaction that links its thread first.
        self.before_insert = None

    async def get_thread_id(self, underwriting_id, kind):
        return self.links.get((underwriting_id, kind))

    async def get_thread_ids(self, underwriting_ids, kind):
        return {
            u: t
            for (u, k), t in self.links.items()
            if k == kind and u in underwriting_ids
        }

    async def insert_link(self, underwriting_id, kind, thread_id):
        if self.before_insert is not None:
            hook, self.before_insert = self.before_insert, None
            if await hook() is False:
                return None
        if (underwriting_id, kind) in self.links:
            return None
        self.links[(underwriting_id, kind)] = thread_id
        return thread_id


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class World:
    def __init__(self):
        self.discussion_repo = FakeDiscussionRepository()
        self.thread_repo = FakeThreadRepository()
        self.discussions = DiscussionService(
            self.discussion_repo, FakeUserLookup([SAM, JANE, GONE])
        )
        self.service = UnderwritingDiscussionService(
            FakeUnderwritingRepository({UW, UW + 1}), self.thread_repo, self.discussions
        )
        self.session = FakeSession()
        self.current_user = SimpleNamespace(id=SAM.id)

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_underwriting_comment_controller] = lambda: (
            UnderwritingCommentController(self.service, self.session)
        )
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app)

    async def post(self, underwriting_id=UW, author=SAM.id, inline=None):
        return await self.service.create_comment(
            underwriting_id,
            author_user_id=author,
            payload=CreateCommentRequest(body=doc(para(*(inline or [text("hi")])))),
        )


@pytest.fixture
def world():
    return World()


def url(underwriting_id=UW):
    return f"/iron-bank/underwritings/{underwriting_id}/comments"


# ── Service: lazy thread creation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_without_thread_creates_nothing(world):
    page = await world.service.list_comments(UW)
    assert page.items == [] and page.total == 0
    assert world.discussion_repo.threads == {}
    assert world.thread_repo.links == {}


@pytest.mark.asyncio
async def test_first_comment_creates_thread_and_link(world):
    comment = await world.post()
    assert world.thread_repo.links == {(UW, "general"): comment.thread_id}
    thread = world.discussion_repo.threads[comment.thread_id]
    assert thread.subject_type == "underwriting"
    assert thread.created_by_user_id == SAM.id
    assert thread.comment_count == 1


@pytest.mark.asyncio
async def test_later_comments_reuse_thread(world):
    first = await world.post()
    second = await world.post(author=JANE.id)
    assert second.thread_id == first.thread_id
    assert len(world.discussion_repo.threads) == 1
    assert world.discussion_repo.threads[first.thread_id].comment_count == 2


@pytest.mark.asyncio
async def test_each_underwriting_gets_its_own_thread(world):
    a = await world.post(UW)
    b = await world.post(UW + 1)
    assert a.thread_id != b.thread_id
    assert (await world.service.list_comments(UW + 1)).items[0].id == b.id


@pytest.mark.asyncio
async def test_losing_the_link_race_uses_winner_and_discards_own_thread(world):
    async def concurrent_winner():
        winner = await world.discussions.create_thread(
            SubjectType.UNDERWRITING, JANE.id
        )
        world.thread_repo.links[(UW, "general")] = winner
        world.winner = winner

    world.thread_repo.before_insert = concurrent_winner
    comment = await world.post()

    assert comment.thread_id == world.winner
    assert world.thread_repo.links == {(UW, "general"): world.winner}
    # Only the winner's thread remains; ours was discarded.
    assert set(world.discussion_repo.threads) == {world.winner}
    assert world.discussion_repo.threads[world.winner].comment_count == 1


@pytest.mark.asyncio
async def test_conflict_with_vanished_link_is_not_found(world):
    async def conflict_then_gone():
        return False  # insert reports a conflict, but no link remains

    world.thread_repo.before_insert = conflict_then_gone
    with pytest.raises(UnderwritingNotFoundError):
        await world.post()


@pytest.mark.asyncio
async def test_unknown_underwriting(world):
    with pytest.raises(UnderwritingNotFoundError):
        await world.service.list_comments(999)
    with pytest.raises(UnderwritingNotFoundError):
        await world.post(999)
    assert world.discussion_repo.threads == {}


@pytest.mark.asyncio
async def test_invalid_comment_errors_propagate(world):
    with pytest.raises(InvalidBodyError):
        await world.service.create_comment(
            UW, author_user_id=SAM.id, payload=CreateCommentRequest(body=doc(para()))
        )
    with pytest.raises(RepliesNotSupportedError):
        await world.service.create_comment(
            UW,
            author_user_id=SAM.id,
            payload=CreateCommentRequest(
                body=doc(para(text("x"))), parent_comment_id=1
            ),
        )


# ── Routes ───────────────────────────────────────────────────────────────────


def test_post_creates_comment_and_commits(world):
    response = world.client.post(
        url(), json={"body": doc(para(text("ADR high, "), mention(42)))}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["author_user_id"] == SAM.id
    assert data["body"] == doc(para(text("ADR high, "), mention(42)))
    assert set(data["users"]) == {"7", "42"}
    assert world.session.commits == 1


def test_post_ignores_client_author(world):
    response = world.client.post(
        url(), json={"body": doc(para(text("x"))), "author_user_id": 42}
    )
    assert response.status_code == 422
    assert world.session.commits == 0


@pytest.mark.asyncio
async def test_get_lists_page(world):
    for _ in range(30):
        await world.post()
    response = world.client.get(url(), params={"page": 2, "page_size": 25})
    assert response.status_code == 200
    data = response.json()
    assert (data["total"], data["page"], data["page_size"], data["pages"]) == (
        30,
        2,
        25,
        2,
    )
    assert len(data["items"]) == 5
    assert world.session.commits == 0


def test_get_without_thread(world):
    response = world.client.get(url())
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "users": {},
        "total": 0,
        "page": 1,
        "page_size": 25,
        "pages": 0,
    }


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"page_size": 20}, {"page_size": 1000}, {"page": "x"}]
)
def test_get_rejects_bad_paging(world, params):
    assert world.client.get(url(), params=params).status_code == 422


@pytest.mark.parametrize("method", ["get", "post"])
def test_unknown_underwriting_is_404(world, method):
    kwargs = {"json": {"body": doc(para(text("x")))}} if method == "post" else {}
    response = getattr(world.client, method)(url(999), **kwargs)
    assert response.status_code == 404
    assert response.json() == {"detail": "Underwriting not found"}
    assert world.session.commits == 0


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"body": doc(para())}, "value_error"),
        ({"body": doc({"type": "heading"})}, "union_tag_invalid"),
        ({"body": doc(para(mention(99)))}, "invalid_mention"),
        (
            {"body": doc(para(text("x"))), "parent_comment_id": 5},
            "replies_not_supported",
        ),
    ],
)
def test_post_invalid_is_422_and_not_committed(world, payload, error_type):
    response = world.client.post(url(), json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == error_type
    # The lazily created thread/link would roll back with the session.
    assert world.session.commits == 0


def test_post_unexpected_error_is_500(world, monkeypatch):
    async def boom(*_args, **_kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(world.thread_repo, "get_thread_id", boom)
    response = world.client.post(url(), json={"body": doc(para(text("x")))})
    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to create comment"}
    assert world.session.commits == 0


def test_routes_registered_on_app():
    from app import create_app

    paths = create_app().openapi()["paths"]
    assert {"get", "post"} <= set(
        paths["/iron-bank/underwritings/{underwriting_id}/comments"]
    )
