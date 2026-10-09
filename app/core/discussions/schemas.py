from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.core.discussions.body.nodes import CURRENT_BODY_VERSION


class BaseResponse(BaseModel):
    """Response base enabling attribute reads (ORM rows, ``UserRef``)."""

    model_config = {"from_attributes": True}


# ── Requests ─────────────────────────────────────────────────────────────────


class CreateCommentRequest(BaseModel):
    body_version: int = CURRENT_BODY_VERSION
    # Raw Tiptap JSON; validated and normalized by the body pipeline.
    body: Any
    # Reserved for replies; must be null in v1.
    parent_comment_id: int | None = None


class UpdateCommentRequest(BaseModel):
    body_version: int = CURRENT_BODY_VERSION
    body: Any


# ── Responses ────────────────────────────────────────────────────────────────


class CommentUser(BaseResponse):
    id: int
    first_name: str | None
    last_name: str | None
    email: str | None
    is_deleted: bool


class CommentRead(BaseModel):
    id: int
    thread_id: int
    author_user_id: int
    parent_comment_id: int | None
    body_version: int
    # null for deleted comments (placeholders)
    body: dict[str, Any] | None
    created_at: datetime
    edited_at: datetime | None
    is_deleted: bool


class CommentDetail(CommentRead):
    """A single comment (create/edit response) with its own users map."""

    users: dict[int, CommentUser]


class CommentPage(BaseModel):
    items: list[CommentRead]
    # Authors of the page plus users mentioned in it; keys are user ids.
    users: dict[int, CommentUser]
    # Same paging fields as the other list endpoints. total includes deleted
    # placeholders.
    total: int
    page: int
    page_size: int
    pages: int


class DiscussionSummary(BaseModel):
    """Per-subject summary for list views, read from the stored counters."""

    thread_id: int | None
    comment_count: int
    last_comment_at: datetime | None

    @classmethod
    def empty(cls) -> "DiscussionSummary":
        return cls(thread_id=None, comment_count=0, last_comment_at=None)
