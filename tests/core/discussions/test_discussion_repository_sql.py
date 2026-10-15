"""Compile-level checks for the repository's non-trivial SQL.

No database: a capturing session records each statement and it is compiled
with the PostgreSQL dialect. Behaviour against a real database is not covered
here.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects import postgresql

from app.core.discussions.repository import DiscussionRepository

AT = datetime(2026, 10, 8, tzinfo=UTC)


class _Result:
    def scalars(self):
        return self

    def all(self):
        return []


class CapturingSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement, params=None):
        self.statements.append(statement)
        return _Result()

    async def scalar(self, statement):
        self.statements.append(statement)


def sql(statement) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


@pytest.fixture
def session():
    return CapturingSession()


@pytest.fixture
def repo(session):
    return DiscussionRepository(session)


@pytest.mark.asyncio
async def test_record_created_guards_last_comment(repo, session):
    await repo.record_comment_created(88, 981, AT)
    stmt = sql(session.statements[0])
    assert "comment_count=(discussions.threads.comment_count + " in stmt
    assert (
        "> (discussions.threads.last_comment_at, discussions.threads.last_comment_id)"
        in stmt
    )
    assert stmt.count("CASE WHEN") == 2


@pytest.mark.asyncio
async def test_record_deleted_recomputes_from_live_comments(repo, session):
    await repo.record_comment_deleted(88, 981)
    stmt = sql(session.statements[0])
    assert "comment_count=(discussions.threads.comment_count - " in stmt
    assert "discussions.comments.deleted_at IS NULL" in stmt
    assert (
        "ORDER BY discussions.comments.created_at DESC, discussions.comments.id DESC"
        in stmt
    )


@pytest.mark.asyncio
async def test_list_comments_counts_all_and_pages_newest_first(repo, session):
    await repo.list_comments(88, page=3, page_size=25)
    count, page = (sql(s) for s in session.statements)
    assert count.startswith("SELECT count(*) AS count_1 FROM discussions.comments")
    assert "deleted_at" not in count  # placeholders are counted
    assert (
        "ORDER BY discussions.comments.created_at DESC, discussions.comments.id DESC"
        in page
    )
    compiled = session.statements[1].compile(dialect=postgresql.dialect())
    assert compiled.params["param_1"] == 25  # limit
    assert compiled.params["param_2"] == 50  # offset


@pytest.mark.asyncio
async def test_edit_and_delete_lock_comment(repo, session):
    await repo.get_comment(981, for_update=True)
    assert sql(session.statements[0]).endswith("FOR UPDATE")


@pytest.mark.asyncio
async def test_empty_inputs_skip_queries(repo, session):
    await repo.add_mentions(1, [])
    assert await repo.get_mentioned_user_ids([]) == set()
    assert await repo.get_threads([]) == []
    assert session.statements == []
