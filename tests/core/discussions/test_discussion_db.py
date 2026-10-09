"""DiscussionService + DiscussionRepository against a real Postgres.

Opt-in: ``RUN_DB_TESTS=1 uv run pytest tests/core/discussions/test_discussion_db.py``.
Uses ``DATABASE_URL`` and refuses to run against the production project.
Each test deletes the threads it created (comments and mentions cascade).
Requires users 1 and 2 to exist and be active.
"""

import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_config
from app.core.discussions.enums import SubjectType
from app.core.discussions.models import Comment, CommentMention, Thread
from app.core.discussions.repository import DiscussionRepository
from app.core.discussions.service import DiscussionService
from app.dependencies import get_user_lookup
from tests.core.discussions.conftest import doc, mention, para
from tests.core.discussions.conftest import text as text_node

PROD_PROJECT_REF = "cnunaeslrrgetewuxsty"
USER_A, USER_B = 1, 2

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="set RUN_DB_TESTS=1 to run"
)


@pytest_asyncio.fixture
async def sessionmaker():
    url = get_config().async_database_url
    if PROD_PROJECT_REF in url:
        pytest.fail("Refusing to run DB tests against the production project")
    engine = create_async_engine(
        url,
        pool_size=3,  # one engine per test; reuses connections within it
        connect_args={
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__t_{os.urandom(8).hex()}__",
            "statement_cache_size": 0,
        },
    )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def created_threads(sessionmaker):
    ids: list[int] = []
    yield ids
    if ids:
        async with sessionmaker() as session:
            await session.execute(Thread.__table__.delete().where(Thread.id.in_(ids)))
            await session.commit()


def service_for(session) -> DiscussionService:
    return DiscussionService(DiscussionRepository(session), get_user_lookup(session))


async def new_thread(sessionmaker, created_threads) -> int:
    async with sessionmaker() as session:
        thread_id = await service_for(session).create_thread(
            SubjectType.UNDERWRITING, USER_A
        )
        await session.commit()
    created_threads.append(thread_id)
    return thread_id


def body(*inline):
    return doc(para(*inline))


async def read_thread(sessionmaker, thread_id) -> Thread:
    async with sessionmaker() as session:
        return await session.scalar(select(Thread).where(Thread.id == thread_id))


@pytest.mark.asyncio
async def test_round_trip(sessionmaker, created_threads):
    thread_id = await new_thread(sessionmaker, created_threads)

    async with sessionmaker() as session:
        created = await service_for(session).create_comment(
            thread_id,
            author_user_id=USER_A,
            body_version=1,
            body=body(text_node("hi "), mention(str(USER_B), label="x")),
        )
        await session.commit()
    assert created.created_at.tzinfo is not None
    assert created.body == body(text_node("hi "), mention(USER_B))
    assert set(created.users) == {USER_A, USER_B}

    thread = await read_thread(sessionmaker, thread_id)
    assert thread.comment_count == 1
    assert thread.last_comment_id == created.id
    assert thread.last_comment_at == created.created_at

    async with sessionmaker() as session:
        edited = await service_for(session).edit_comment(
            created.id,
            user_id=USER_A,
            body_version=1,
            body=body(text_node("edited")),
        )
        await session.commit()
    assert edited.body == body(text_node("edited"))
    assert edited.edited_at is not None
    assert edited.users.keys() == {USER_A}

    async with sessionmaker() as session:
        row = await session.scalar(select(Comment).where(Comment.id == created.id))
        assert row.body_text == "edited"
        mentions = await session.scalars(
            select(CommentMention.user_id).where(
                CommentMention.comment_id == created.id
            )
        )
        assert list(mentions) == []

    async with sessionmaker() as session:
        page = await service_for(session).list_comments(thread_id)
    assert [c.id for c in page.items] == [created.id]
    assert page.items[0].body == body(text_node("edited"))

    async with sessionmaker() as session:
        await service_for(session).delete_comment(created.id, user_id=USER_A)
        await session.commit()

    thread = await read_thread(sessionmaker, thread_id)
    assert thread.comment_count == 0
    assert thread.last_comment_id is None
    assert thread.last_comment_at is None

    async with sessionmaker() as session:
        page = await service_for(session).list_comments(thread_id)
    assert page.items[0].is_deleted and page.items[0].body is None


@pytest.mark.asyncio
async def test_delete_recomputes_last_comment(sessionmaker, created_threads):
    thread_id = await new_thread(sessionmaker, created_threads)
    ids = []
    for word in ("one", "two"):
        async with sessionmaker() as session:
            c = await service_for(session).create_comment(
                thread_id,
                author_user_id=USER_A,
                body_version=1,
                body=body(text_node(word)),
            )
            await session.commit()
            ids.append(c)

    async with sessionmaker() as session:
        await service_for(session).delete_comment(ids[1].id, user_id=USER_A)
        await session.commit()

    thread = await read_thread(sessionmaker, thread_id)
    assert thread.comment_count == 1
    assert thread.last_comment_id == ids[0].id
    assert thread.last_comment_at == ids[0].created_at


@pytest.mark.asyncio
async def test_pagination_with_timestamp_ties(sessionmaker, created_threads):
    thread_id = await new_thread(sessionmaker, created_threads)
    # One multi-row INSERT in one transaction: every row gets the same
    # created_at (now() is the transaction start), so order relies on the id
    # tiebreak. Bypasses the service to keep it to one round trip.
    async with sessionmaker() as session:
        result = await session.execute(
            insert(Comment).returning(Comment.id),
            [
                {
                    "thread_id": thread_id,
                    "author_user_id": USER_A,
                    "body": body(text_node(f"c{i}")),
                    "body_text": f"c{i}",
                }
                for i in range(30)
            ],
        )
        ids = sorted(result.scalars().all())
        await session.commit()

    async with sessionmaker() as session:
        service = service_for(session)
        first = await service.list_comments(thread_id, page=1)
        second = await service.list_comments(thread_id, page=2)
    assert len({c.created_at for c in first.items + second.items}) == 1
    assert (first.total, first.pages) == (30, 2)
    assert [len(first.items), len(second.items)] == [25, 5]
    assert [c.id for c in first.items + second.items] == list(reversed(ids))


@pytest.mark.asyncio
async def test_last_comment_survives_out_of_order_commit(sessionmaker, created_threads):
    """A's transaction starts first (earlier created_at) but commits last."""
    thread_id = await new_thread(sessionmaker, created_threads)

    async with sessionmaker() as session_a:
        await session_a.execute(text("SELECT 1"))  # A's transaction starts
        await asyncio.sleep(0.05)

        async with sessionmaker() as session_b:
            b = await service_for(session_b).create_comment(
                thread_id,
                author_user_id=USER_B,
                body_version=1,
                body=body(text_node("b")),
            )
            await session_b.commit()

        a = await service_for(session_a).create_comment(
            thread_id, author_user_id=USER_A, body_version=1, body=body(text_node("a"))
        )
        await session_a.commit()

    assert a.created_at < b.created_at
    assert a.id > b.id
    thread = await read_thread(sessionmaker, thread_id)
    assert thread.comment_count == 2
    assert thread.last_comment_id == b.id


@pytest.mark.asyncio
async def test_concurrent_double_delete_decrements_once(sessionmaker, created_threads):
    thread_id = await new_thread(sessionmaker, created_threads)
    async with sessionmaker() as session:
        c = await service_for(session).create_comment(
            thread_id, author_user_id=USER_A, body_version=1, body=body(text_node("x"))
        )
        await session.commit()

    async def delete():
        async with sessionmaker() as session:
            try:
                await service_for(session).delete_comment(c.id, user_id=USER_A)
                await session.commit()
                return "deleted"
            except Exception as exc:  # noqa: BLE001
                return type(exc).__name__

    results = sorted(await asyncio.gather(delete(), delete()))
    assert results == ["CommentNotFoundError", "deleted"]
    assert (await read_thread(sessionmaker, thread_id)).comment_count == 0


@pytest.mark.asyncio
async def test_summaries(sessionmaker, created_threads):
    thread_id = await new_thread(sessionmaker, created_threads)
    async with sessionmaker() as session:
        await service_for(session).create_comment(
            thread_id, author_user_id=USER_A, body_version=1, body=body(text_node("x"))
        )
        await session.commit()
    async with sessionmaker() as session:
        summaries = await service_for(session).get_summaries([thread_id])
    assert summaries[thread_id].comment_count == 1
    assert summaries[thread_id].last_comment_at is not None
