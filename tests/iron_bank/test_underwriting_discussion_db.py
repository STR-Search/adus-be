"""Lazy thread creation for underwriting comments against a real Postgres.

Opt-in: ``RUN_DB_TESTS=1 uv run pytest tests/iron_bank/test_underwriting_discussion_db.py``.
Same guard and setup as tests/core/discussions/test_discussion_db.py. Uses
the newest underwriting that has no thread yet, and deletes every thread
created during the test (its link and comments cascade).
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.discussions.models import Comment, Thread
from app.core.discussions.repository import DiscussionRepository
from app.core.discussions.schemas import CreateCommentRequest
from app.core.discussions.service import DiscussionService
from app.dependencies import get_user_lookup
from app.iron_bank.models import Underwriting, UnderwritingThread
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.repositories.underwriting_thread_repository import (
    UnderwritingThreadRepository,
)
from app.iron_bank.services.underwriting_discussion_service import (
    UnderwritingDiscussionService,
)
from tests.core.discussions.conftest import doc, para, text
from tests.core.discussions.test_discussion_db import (  # noqa: F401 (fixture)
    USER_A,
    USER_B,
    pytestmark,
    sessionmaker,
)

CONCURRENT_FIRST_COMMENTS = 5


def service_for(session) -> UnderwritingDiscussionService:
    return UnderwritingDiscussionService(
        UnderwritingRepository(session),
        UnderwritingThreadRepository(session),
        DiscussionService(DiscussionRepository(session), get_user_lookup(session)),
    )


@pytest_asyncio.fixture
async def underwriting_id(sessionmaker):  # noqa: F811
    """Newest underwriting without a thread; cleans up threads made meanwhile."""
    async with sessionmaker() as session:
        uw_id = await session.scalar(
            select(func.max(Underwriting.id)).where(
                ~select(UnderwritingThread.underwriting_id)
                .where(UnderwritingThread.underwriting_id == Underwriting.id)
                .exists()
            )
        )
        max_thread_before = await session.scalar(select(func.max(Thread.id))) or 0
    assert uw_id is not None
    yield uw_id
    async with sessionmaker() as session:
        await session.execute(
            Thread.__table__.delete().where(Thread.id > max_thread_before)
        )
        await session.commit()


async def threads_created_since_fixture(sessionmaker, uw_id):  # noqa: F811
    async with sessionmaker() as session:
        links = (
            (
                await session.execute(
                    select(UnderwritingThread.thread_id).where(
                        UnderwritingThread.underwriting_id == uw_id
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(links)


@pytest.mark.asyncio
async def test_concurrent_first_comments_share_one_thread(
    sessionmaker,  # noqa: F811
    underwriting_id,
    monkeypatch,
):
    # Count losers so the test proves the race path ran, not just that
    # sequential requests reused a thread.
    discarded = []
    original_discard = DiscussionService.discard_thread

    async def counting_discard(self, thread_id):
        discarded.append(thread_id)
        await original_discard(self, thread_id)

    monkeypatch.setattr(DiscussionService, "discard_thread", counting_discard)

    async def first_comment(i: int):
        async with sessionmaker() as session:
            detail = await service_for(session).create_comment(
                underwriting_id,
                author_user_id=USER_A if i % 2 else USER_B,
                payload=CreateCommentRequest(body=doc(para(text(f"race {i}")))),
            )
            await session.commit()
            return detail

    results = await asyncio.gather(
        *(first_comment(i) for i in range(CONCURRENT_FIRST_COMMENTS))
    )

    assert discarded, "no request lost the link race; the race path was not exercised"
    thread_ids = {r.thread_id for r in results}
    assert len(thread_ids) == 1
    (thread_id,) = thread_ids

    async with sessionmaker() as session:
        links = (
            (
                await session.execute(
                    select(UnderwritingThread).where(
                        UnderwritingThread.underwriting_id == underwriting_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [(link.kind, link.thread_id) for link in links] == [
            ("general", thread_id)
        ]

        thread = await session.scalar(select(Thread).where(Thread.id == thread_id))
        assert thread.comment_count == CONCURRENT_FIRST_COMMENTS
        assert thread.subject_type == "underwriting"

        comments = await session.scalar(
            select(func.count())
            .select_from(Comment)
            .where(Comment.thread_id == thread_id)
        )
        assert comments == CONCURRENT_FIRST_COMMENTS

        # Losers discarded their threads: none left without a link.
        orphans = await session.scalar(
            select(func.count())
            .select_from(Thread)
            .where(
                Thread.id > thread_id - 2 * CONCURRENT_FIRST_COMMENTS,
                Thread.subject_type == "underwriting",
                ~select(UnderwritingThread.thread_id)
                .where(UnderwritingThread.thread_id == Thread.id)
                .exists(),
            )
        )
        assert orphans == 0

    async with sessionmaker() as session:
        page = await service_for(session).list_comments(underwriting_id)
    assert page.total == CONCURRENT_FIRST_COMMENTS


@pytest.mark.asyncio
async def test_rejected_first_comment_leaves_no_thread(
    sessionmaker,  # noqa: F811
    underwriting_id,
):
    async with sessionmaker() as session:
        with pytest.raises(Exception, match="empty"):
            await service_for(session).create_comment(
                underwriting_id,
                author_user_id=USER_A,
                payload=CreateCommentRequest(body=doc(para())),
            )
        # No commit: the session closes and rolls back, as get_db does.

    assert await threads_created_since_fixture(sessionmaker, underwriting_id) == []
