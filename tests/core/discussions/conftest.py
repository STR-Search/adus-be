from collections.abc import Collection

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
