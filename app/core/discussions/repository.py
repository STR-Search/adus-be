"""Data access for ``discussions`` tables.

Unlike most repositories here, this one never commits: it only executes and
flushes. The caller owns the transaction, because a domain's lazy thread
creation (thread + its own link row + first comment) must be atomic. See
``docs/underwriting_discussions.md`` §5.
"""

from collections.abc import Collection
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    case,
    delete,
    func,
    insert,
    literal,
    or_,
    select,
    tuple_,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discussions.models import Comment, CommentMention, Thread


class DiscussionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Threads ──────────────────────────────────────────────────────────────

    async def create_thread(
        self, subject_type: str, created_by_user_id: int | None
    ) -> int:
        return await self.db.scalar(
            insert(Thread)
            .values(subject_type=subject_type, created_by_user_id=created_by_user_id)
            .returning(Thread.id)
        )

    async def delete_thread(self, thread_id: int) -> None:
        await self.db.execute(delete(Thread).where(Thread.id == thread_id))

    async def get_threads(self, thread_ids: Collection[int]) -> list[Thread]:
        if not thread_ids:
            return []
        result = await self.db.execute(
            select(Thread).where(Thread.id.in_(set(thread_ids)))
        )
        return list(result.scalars().all())

    async def record_comment_created(
        self, thread_id: int, comment_id: int, created_at: datetime
    ) -> None:
        """Bump the count and move ``last_comment_*`` forward, never back.

        ``created_at`` is the inserting transaction's start time, so two
        concurrent posts can reach this UPDATE out of order; the row-value
        comparison keeps whichever comment is newer by ``(created_at, id)``.
        """
        incoming = tuple_(
            literal(created_at, DateTime(timezone=True)),
            literal(comment_id, BigInteger),
        )
        is_newer = or_(
            Thread.last_comment_at.is_(None),
            Thread.last_comment_id.is_(None),
            incoming > tuple_(Thread.last_comment_at, Thread.last_comment_id),
        )
        await self.db.execute(
            update(Thread)
            .where(Thread.id == thread_id)
            .values(
                comment_count=Thread.comment_count + 1,
                last_comment_id=case(
                    (is_newer, comment_id), else_=Thread.last_comment_id
                ),
                last_comment_at=case(
                    (is_newer, created_at), else_=Thread.last_comment_at
                ),
            )
            .execution_options(synchronize_session=False)
        )

    async def record_comment_deleted(self, thread_id: int, comment_id: int) -> None:
        """Decrement the count; if it was the last comment, recompute from the
        newest non-deleted one (or NULL). Run after the soft delete."""
        newest = (
            select(Comment.id, Comment.created_at)
            .where(Comment.thread_id == thread_id, Comment.deleted_at.is_(None))
            .order_by(Comment.created_at.desc(), Comment.id.desc())
            .limit(1)
        )
        was_last = Thread.last_comment_id == comment_id
        await self.db.execute(
            update(Thread)
            .where(Thread.id == thread_id)
            .values(
                comment_count=Thread.comment_count - 1,
                last_comment_id=case(
                    (was_last, newest.with_only_columns(Comment.id).scalar_subquery()),
                    else_=Thread.last_comment_id,
                ),
                last_comment_at=case(
                    (
                        was_last,
                        newest.with_only_columns(Comment.created_at).scalar_subquery(),
                    ),
                    else_=Thread.last_comment_at,
                ),
            )
            .execution_options(synchronize_session=False)
        )

    # ── Comments ─────────────────────────────────────────────────────────────

    async def insert_comment(
        self,
        *,
        thread_id: int,
        author_user_id: int,
        parent_comment_id: int | None,
        body_version: int,
        body: dict,
        body_text: str,
    ) -> Comment:
        return await self.db.scalar(
            insert(Comment)
            .values(
                thread_id=thread_id,
                author_user_id=author_user_id,
                parent_comment_id=parent_comment_id,
                body_version=body_version,
                body=body,
                body_text=body_text,
            )
            .returning(Comment)
        )

    async def get_comment(
        self, comment_id: int, *, for_update: bool = False
    ) -> Comment | None:
        stmt = select(Comment).where(Comment.id == comment_id)
        if for_update:
            # Serializes edit/delete of one comment so a double delete cannot
            # decrement the count twice.
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self.db.scalar(stmt)

    async def update_comment_body(
        self, comment_id: int, *, body_version: int, body: dict, body_text: str
    ) -> Comment:
        return await self.db.scalar(
            update(Comment)
            .where(Comment.id == comment_id)
            .values(
                body_version=body_version,
                body=body,
                body_text=body_text,
                edited_at=func.now(),
            )
            .returning(Comment)
            .execution_options(populate_existing=True)
        )

    async def soft_delete_comment(self, comment_id: int) -> None:
        await self.db.execute(
            update(Comment)
            .where(Comment.id == comment_id)
            .values(deleted_at=func.now())
            .execution_options(synchronize_session=False)
        )

    async def list_comments(
        self, thread_id: int, *, page: int, page_size: int
    ) -> tuple[list[Comment], int]:
        """One page, newest first by ``(created_at, id)``, plus the total.

        Deleted comments are included (as placeholders) in both the page and
        the total, so ``threads.comment_count`` cannot serve as the total.
        """
        total: int = await self.db.scalar(
            select(func.count())
            .select_from(Comment)
            .where(Comment.thread_id == thread_id)
        )
        result = await self.db.execute(
            select(Comment)
            .where(Comment.thread_id == thread_id)
            .order_by(Comment.created_at.desc(), Comment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    # ── Mentions ─────────────────────────────────────────────────────────────

    async def add_mentions(self, comment_id: int, user_ids: Collection[int]) -> None:
        if not user_ids:
            return
        await self.db.execute(
            insert(CommentMention),
            [{"comment_id": comment_id, "user_id": user_id} for user_id in user_ids],
        )

    async def replace_mentions(
        self, comment_id: int, user_ids: Collection[int]
    ) -> None:
        await self.db.execute(
            delete(CommentMention).where(CommentMention.comment_id == comment_id)
        )
        await self.add_mentions(comment_id, user_ids)

    async def get_mentioned_user_ids(self, comment_ids: Collection[int]) -> set[int]:
        if not comment_ids:
            return set()
        result = await self.db.execute(
            select(CommentMention.user_id)
            .where(CommentMention.comment_id.in_(set(comment_ids)))
            .distinct()
        )
        return set(result.scalars().all())
