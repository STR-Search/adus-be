"""``DiscussionService``: the only entry point for domains.

Methods never commit. The caller owns the transaction so a domain can create
a thread, its own link row, and the first comment atomically; the
discussions controller commits for its own routes.
"""

import math
from collections.abc import Collection, Iterable, Mapping
from typing import Any

from app.core.discussions.body.pipeline import process_body
from app.core.discussions.enums import SubjectType
from app.core.discussions.exceptions import (
    CommentNotFoundError,
    NotCommentAuthorError,
    RepliesNotSupportedError,
)
from app.core.discussions.interfaces import UserLookup, UserRef
from app.core.discussions.models import Comment
from app.core.discussions.repository import DiscussionRepository
from app.core.discussions.schemas import (
    CommentDetail,
    CommentPage,
    CommentRead,
    CommentUser,
    DiscussionSummary,
)
from app.core.enums import PageSize


class DiscussionService:
    def __init__(self, repository: DiscussionRepository, user_lookup: UserLookup):
        self.repository = repository
        self.user_lookup = user_lookup

    # ── Threads ──────────────────────────────────────────────────────────────

    async def create_thread(
        self, subject_type: SubjectType, created_by_user_id: int | None
    ) -> int:
        return await self.repository.create_thread(
            SubjectType(subject_type).value, created_by_user_id
        )

    async def discard_thread(self, thread_id: int) -> None:
        """Delete a thread created moments ago that lost a link-creation race."""
        await self.repository.delete_thread(thread_id)

    async def get_summaries(
        self, thread_ids: Collection[int]
    ) -> dict[int, DiscussionSummary]:
        """Stored counters per thread id. Ids with no thread are omitted."""
        threads = await self.repository.get_threads(thread_ids)
        return {
            t.id: DiscussionSummary(
                thread_id=t.id,
                comment_count=t.comment_count,
                last_comment_at=t.last_comment_at,
            )
            for t in threads
        }

    # ── Comments ─────────────────────────────────────────────────────────────

    async def list_comments(
        self,
        thread_id: int | None,
        *,
        page: int = 1,
        page_size: PageSize = PageSize.SMALL,
    ) -> CommentPage:
        """Newest first. ``thread_id=None`` (no thread yet) is an empty page."""
        if page < 1:
            raise ValueError("page must be >= 1")
        page_size = PageSize(page_size)

        rows: list[Comment] = []
        total = 0
        if thread_id is not None:
            rows, total = await self.repository.list_comments(
                thread_id, page=page, page_size=page_size
            )

        # One user lookup: authors plus users mentioned in visible comments.
        # Bodies are not parsed for this; comment_mentions is the index.
        visible_ids = [c.id for c in rows if c.deleted_at is None]
        user_ids = {c.author_user_id for c in rows}
        user_ids |= await self.repository.get_mentioned_user_ids(visible_ids)
        users = await self._lookup(user_ids)

        return CommentPage(
            items=[_to_read(c) for c in rows],
            users=_users_map(users.values()),
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size),
        )

    async def create_comment(
        self,
        thread_id: int,
        *,
        author_user_id: int,
        body_version: int,
        body: Any,
        parent_comment_id: int | None = None,
    ) -> CommentDetail:
        if parent_comment_id is not None:
            raise RepliesNotSupportedError()

        processed = await process_body(body_version, body, self.user_lookup)
        comment = await self.repository.insert_comment(
            thread_id=thread_id,
            author_user_id=author_user_id,
            parent_comment_id=None,
            body_version=body_version,
            body=processed.body,
            body_text=processed.body_text,
        )
        await self.repository.add_mentions(comment.id, processed.mention_user_ids)
        await self.repository.record_comment_created(
            thread_id, comment.id, comment.created_at
        )
        return await self._detail(comment, processed.users)

    async def edit_comment(
        self,
        comment_id: int,
        *,
        user_id: int,
        body_version: int,
        body: Any,
    ) -> CommentDetail:
        await self._get_own_live_comment(comment_id, user_id)
        processed = await process_body(body_version, body, self.user_lookup)
        comment = await self.repository.update_comment_body(
            comment_id,
            body_version=body_version,
            body=processed.body,
            body_text=processed.body_text,
        )
        await self.repository.replace_mentions(comment_id, processed.mention_user_ids)
        return await self._detail(comment, processed.users)

    async def delete_comment(self, comment_id: int, *, user_id: int) -> None:
        comment = await self._get_own_live_comment(comment_id, user_id)
        await self.repository.soft_delete_comment(comment_id)
        await self.repository.record_comment_deleted(comment.thread_id, comment_id)

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _get_own_live_comment(self, comment_id: int, user_id: int) -> Comment:
        """Lock the comment row; 404 if missing or deleted, 403 if not the author."""
        comment = await self.repository.get_comment(comment_id, for_update=True)
        if comment is None or comment.deleted_at is not None:
            raise CommentNotFoundError(comment_id)
        if comment.author_user_id != user_id:
            raise NotCommentAuthorError(comment_id)
        return comment

    async def _lookup(self, user_ids: Collection[int]) -> dict[int, UserRef]:
        return await self.user_lookup.get_users(user_ids) if user_ids else {}

    async def _detail(
        self, comment: Comment, mentioned: Mapping[int, UserRef]
    ) -> CommentDetail:
        users = dict(mentioned)
        if comment.author_user_id not in users:
            users |= await self._lookup([comment.author_user_id])
        return CommentDetail(
            **_to_read(comment).model_dump(), users=_users_map(users.values())
        )


def _to_read(comment: Comment) -> CommentRead:
    is_deleted = comment.deleted_at is not None
    return CommentRead(
        id=comment.id,
        thread_id=comment.thread_id,
        author_user_id=comment.author_user_id,
        parent_comment_id=comment.parent_comment_id,
        body_version=comment.body_version,
        body=None if is_deleted else comment.body,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
        is_deleted=is_deleted,
    )


def _users_map(users: Iterable[UserRef]) -> dict[int, CommentUser]:
    return {u.id: CommentUser.model_validate(u) for u in users}
