from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.discussions.interfaces import UserRef


def text(value, marks=None):
    node = {"type": "text", "text": value}
    if marks is not None:
        node["marks"] = marks
    return node


def mention(user_id, **extra):
    return {"type": "mention", "attrs": {"id": user_id, **extra}}


def para(*inline):
    return (
        {"type": "paragraph", "content": list(inline)}
        if inline
        else {"type": "paragraph"}
    )


def item(paragraph, *lists):
    return {"type": "listItem", "content": [paragraph, *lists]}


def bullets(*items):
    return {"type": "bulletList", "content": list(items)}


def ordered(*items, start=None):
    node = {"type": "orderedList", "content": list(items)}
    if start is not None:
        node["attrs"] = {"start": start}
    return node


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


class FakeUserLookup:
    def __init__(self, users: list[UserRef]):
        self.users = {u.id: u for u in users}
        self.calls: list[set[int]] = []

    async def get_users(self, user_ids: Collection[int]) -> dict[int, UserRef]:
        self.calls.append(set(user_ids))
        return {i: self.users[i] for i in user_ids if i in self.users}


T0 = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


class FakeDiscussionRepository:
    def __init__(self):
        self.threads: dict[int, SimpleNamespace] = {}
        self.comments: dict[int, SimpleNamespace] = {}
        self.mentions: set[tuple[int, int]] = set()
        self.clock = T0
        self._ids = iter(range(1, 10_000))

    def tick(self, seconds=1):
        self.clock += timedelta(seconds=seconds)

    async def create_thread(self, subject_type, created_by_user_id):
        thread_id = next(self._ids)
        self.threads[thread_id] = SimpleNamespace(
            id=thread_id,
            subject_type=subject_type,
            created_by_user_id=created_by_user_id,
            comment_count=0,
            last_comment_id=None,
            last_comment_at=None,
        )
        return thread_id

    async def delete_thread(self, thread_id):
        self.threads.pop(thread_id, None)

    async def get_threads(self, thread_ids):
        return [self.threads[i] for i in thread_ids if i in self.threads]

    async def record_comment_created(self, thread_id, comment_id, created_at):
        t = self.threads[thread_id]
        t.comment_count += 1
        if t.last_comment_at is None or (created_at, comment_id) > (
            t.last_comment_at,
            t.last_comment_id,
        ):
            t.last_comment_id, t.last_comment_at = comment_id, created_at

    async def record_comment_deleted(self, thread_id, comment_id):
        t = self.threads[thread_id]
        t.comment_count -= 1
        if t.last_comment_id == comment_id:
            live = [
                c
                for c in self.comments.values()
                if c.thread_id == thread_id and c.deleted_at is None
            ]
            newest = max(live, key=lambda c: (c.created_at, c.id), default=None)
            t.last_comment_id = newest.id if newest else None
            t.last_comment_at = newest.created_at if newest else None

    async def insert_comment(self, **values):
        comment = SimpleNamespace(
            id=next(self._ids),
            created_at=self.clock,
            edited_at=None,
            deleted_at=None,
            **values,
        )
        self.comments[comment.id] = comment
        return comment

    async def get_comment(self, comment_id, *, for_update=False):
        return self.comments.get(comment_id)

    async def update_comment_body(self, comment_id, *, body_version, body, body_text):
        c = self.comments[comment_id]
        c.body_version, c.body, c.body_text = body_version, body, body_text
        c.edited_at = self.clock
        return c

    async def soft_delete_comment(self, comment_id):
        self.comments[comment_id].deleted_at = self.clock

    async def list_comments(self, thread_id, *, page, page_size):
        rows = [c for c in self.comments.values() if c.thread_id == thread_id]
        rows.sort(key=lambda c: (c.created_at, c.id), reverse=True)
        start = (page - 1) * page_size
        return rows[start : start + page_size], len(rows)

    async def add_mentions(self, comment_id, user_ids):
        self.mentions |= {(comment_id, u) for u in user_ids}

    async def replace_mentions(self, comment_id, user_ids):
        self.mentions = {m for m in self.mentions if m[0] != comment_id}
        await self.add_mentions(comment_id, user_ids)

    async def get_mentioned_user_ids(self, comment_ids):
        ids = set(comment_ids)
        return {u for c, u in self.mentions if c in ids}


SAM = UserRef(
    id=7, first_name="Sam", last_name="Lee", email="sam@x.com", is_deleted=False
)
JANE = UserRef(
    id=42, first_name="Jane", last_name="Doe", email="jane@x.com", is_deleted=False
)
GONE = UserRef(id=99, first_name="Old", last_name="User", email=None, is_deleted=True)


@pytest.fixture
def user_lookup() -> FakeUserLookup:
    return FakeUserLookup([SAM, JANE, GONE])
