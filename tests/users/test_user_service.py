from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.users.controllers.user_controller import UserController
from app.users.schemas.user import UserDetail, UserListResult, UserSummary
from app.users.services.user_service import UserService


def _user(user_id: int, **overrides):
    base = dict(
        id=user_id,
        clerk_id=f"user_{user_id}",
        email=f"u{user_id}@example.com",
        first_name="Ada",
        last_name="Lovelace",
        is_deleted=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class StubRepository:
    def __init__(self, users=None, error=None):
        self._users = users or []
        self._error = error

    async def get_all(self):
        if self._error is not None:
            raise self._error
        return self._users


@pytest.mark.asyncio
async def test_get_all_returns_summaries_by_default():
    service = UserService(StubRepository([_user(1), _user(2)]))

    result = await service.get_all()

    assert result.total == 2
    assert all(isinstance(item, UserSummary) for item in result.items)
    assert result.items[0].model_dump() == {
        "id": 1,
        "email": "u1@example.com",
        "first_name": "Ada",
        "last_name": "Lovelace",
    }


@pytest.mark.asyncio
async def test_get_all_detailed_returns_full_rows():
    service = UserService(StubRepository([_user(1)]))

    result = await service.get_all(detailed=True)

    item = result.items[0]
    assert isinstance(item, UserDetail)
    assert item.clerk_id == "user_1"
    assert item.created_at == datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_detailed_fields_survive_response_model_validation():
    # FastAPI re-validates the return value against UserListResult; the items
    # union must not narrow detail rows down to the summary shape.
    service = UserService(StubRepository([_user(1)]))

    result = await service.get_all(detailed=True)
    revalidated = UserListResult.model_validate(result.model_dump())

    assert revalidated.items[0].clerk_id == "user_1"


@pytest.mark.asyncio
async def test_get_all_empty():
    result = await UserService(StubRepository([])).get_all()

    assert result.total == 0
    assert result.items == []


@pytest.mark.asyncio
async def test_controller_wraps_repository_failure_in_500():
    controller = UserController(
        UserService(StubRepository(error=RuntimeError("db down")))
    )

    with pytest.raises(HTTPException) as exc_info:
        await controller.get_users()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch users"


@pytest.mark.asyncio
async def test_controller_passes_detailed_through():
    controller = UserController(UserService(StubRepository([_user(1)])))

    result = await controller.get_users(detailed=True)

    assert isinstance(result.items[0], UserDetail)
