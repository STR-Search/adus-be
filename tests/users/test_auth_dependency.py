from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.dependencies as deps
from app.dependencies import get_current_user


def _request(headers: dict) -> SimpleNamespace:
    return SimpleNamespace(headers=headers)


@pytest.mark.asyncio
async def test_missing_authorization_header_returns_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_request({}), db=None)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_malformed_authorization_header_returns_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_request({"authorization": "token-without-bearer"}), db=None)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_unknown_clerk_user_returns_401(monkeypatch):
    async def fake_verify(_token):
        return {"sub": "clerk_unknown"}

    class FakeUserRepository:
        def __init__(self, _db):
            pass

        async def get_by_clerk_id(self, _clerk_id):
            return None

    monkeypatch.setattr(deps, "verify_clerk_token", fake_verify)
    monkeypatch.setattr(deps, "UserRepository", FakeUserRepository)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(_request({"authorization": "Bearer abc.def.ghi"}), db=None)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_returns_user(monkeypatch):
    user = SimpleNamespace(id=7, clerk_id="clerk_known")

    async def fake_verify(_token):
        return {"sub": "clerk_known"}

    class FakeUserRepository:
        def __init__(self, _db):
            pass

        async def get_by_clerk_id(self, clerk_id):
            return user if clerk_id == "clerk_known" else None

    monkeypatch.setattr(deps, "verify_clerk_token", fake_verify)
    monkeypatch.setattr(deps, "UserRepository", FakeUserRepository)

    result = await get_current_user(_request({"authorization": "Bearer abc.def.ghi"}), db=None)

    assert result is user
