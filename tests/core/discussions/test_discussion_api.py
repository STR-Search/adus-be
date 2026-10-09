"""PATCH/DELETE /comments/{id}: routing, error mapping, and commit behaviour.

Runs the real controller and service over the in-memory repository; only the
DB session (commit tracking), auth, and user lookup are faked.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.discussions.controller import DiscussionController
from app.core.discussions.enums import SubjectType
from app.core.discussions.router import get_discussion_controller, router
from app.core.discussions.service import DiscussionService
from app.dependencies import get_current_user
from tests.core.discussions.conftest import (
    JANE,
    SAM,
    FakeDiscussionRepository,
    doc,
    mention,
    para,
    text,
)


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class Harness:
    def __init__(self, user_lookup):
        self.repo = FakeDiscussionRepository()
        self.session = FakeSession()
        self.service = DiscussionService(self.repo, user_lookup)
        self.current_user = SimpleNamespace(id=SAM.id)

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_discussion_controller] = lambda: (
            DiscussionController(self.service, self.session)
        )
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app)

    async def seed_comment(self, author=SAM.id, inline=None):
        thread_id = await self.service.create_thread(SubjectType.UNDERWRITING, author)
        return await self.service.create_comment(
            thread_id,
            author_user_id=author,
            body_version=1,
            body=doc(para(*(inline or [text("original")]))),
        )


@pytest.fixture
def harness(user_lookup):
    return Harness(user_lookup)


def edit_payload(*inline):
    return {"body_version": 1, "body": doc(para(*inline))}


# ── PATCH ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_returns_detail_and_commits(harness):
    comment = await harness.seed_comment()
    response = harness.client.patch(
        f"/comments/{comment.id}",
        json=edit_payload(text("new "), mention("42", label="Jane")),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == comment.id
    assert data["body"] == doc(para(text("new "), mention(42)))
    assert data["is_deleted"] is False
    assert data["edited_at"] is not None
    # Author plus mentioned users; JSON object keys are strings.
    assert set(data["users"]) == {"7", "42"}
    assert data["users"]["42"]["first_name"] == "Jane"
    assert harness.session.commits == 1


@pytest.mark.asyncio
async def test_edit_by_non_author_is_403(harness):
    comment = await harness.seed_comment(author=JANE.id)
    response = harness.client.patch(
        f"/comments/{comment.id}", json=edit_payload(text("x"))
    )
    assert response.status_code == 403
    assert harness.session.commits == 0


def test_edit_missing_is_404(harness):
    response = harness.client.patch("/comments/999", json=edit_payload(text("x")))
    assert response.status_code == 404
    assert response.json() == {"detail": "Comment not found"}


@pytest.mark.asyncio
async def test_edit_invalid_body_is_422_with_path(harness):
    comment = await harness.seed_comment()
    response = harness.client.patch(
        f"/comments/{comment.id}",
        json={"body": doc({"type": "heading", "content": [text("x")]})},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"][:3] == ["body", "content", 0]
    assert detail[0]["type"] == "union_tag_invalid"
    assert harness.session.commits == 0


@pytest.mark.asyncio
async def test_edit_empty_body_is_422(harness):
    comment = await harness.seed_comment()
    response = harness.client.patch(
        f"/comments/{comment.id}", json={"body": doc(para())}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "comment is empty"


@pytest.mark.asyncio
async def test_edit_invalid_mention_is_422_with_ids(harness):
    comment = await harness.seed_comment()
    response = harness.client.patch(
        f"/comments/{comment.id}", json=edit_payload(mention(99), mention(12345))
    )
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["type"] == "invalid_mention"
    assert detail["ctx"] == {"user_ids": [99, 12345]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},  # body required
        {"body": doc(para(text("x"))), "parent_comment_id": None},  # extra field
        {"body": doc(para(text("x"))), "author_user_id": 42},  # extra field
        {"body": doc(para(text("x"))), "body_version": "one"},
    ],
)
async def test_edit_request_validation(harness, payload):
    comment = await harness.seed_comment()
    response = harness.client.patch(f"/comments/{comment.id}", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_edit_unsupported_body_version_is_422(harness):
    comment = await harness.seed_comment()
    response = harness.client.patch(
        f"/comments/{comment.id}",
        json={"body_version": 2, "body": doc(para(text("x")))},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body_version"]


# ── DELETE ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_is_204_and_commits(harness):
    comment = await harness.seed_comment()
    response = harness.client.delete(f"/comments/{comment.id}")
    assert response.status_code == 204
    assert response.content == b""
    assert harness.session.commits == 1
    assert harness.repo.comments[comment.id].deleted_at is not None
    assert harness.repo.threads[comment.thread_id].comment_count == 0


@pytest.mark.asyncio
async def test_delete_twice_is_404(harness):
    comment = await harness.seed_comment()
    assert harness.client.delete(f"/comments/{comment.id}").status_code == 204
    assert harness.client.delete(f"/comments/{comment.id}").status_code == 404
    assert harness.session.commits == 1


@pytest.mark.asyncio
async def test_delete_by_non_author_is_403(harness):
    comment = await harness.seed_comment(author=JANE.id)
    response = harness.client.delete(f"/comments/{comment.id}")
    assert response.status_code == 403
    assert harness.repo.comments[comment.id].deleted_at is None


def test_non_integer_id_is_422(harness):
    assert harness.client.delete("/comments/abc").status_code == 422


# ── Unexpected errors ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unexpected_error_is_500_without_commit(harness, monkeypatch):
    comment = await harness.seed_comment()

    async def boom(*_args, **_kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(harness.repo, "soft_delete_comment", boom)
    response = harness.client.delete(f"/comments/{comment.id}")
    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to delete comment"}
    assert harness.session.commits == 0


# ── App wiring ───────────────────────────────────────────────────────────────


def test_routes_registered_on_app():
    from app import create_app

    operations = create_app().openapi()["paths"]["/comments/{comment_id}"]
    assert {"patch", "delete"} <= set(operations)
