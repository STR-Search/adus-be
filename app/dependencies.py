from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.clerk import verify_clerk_token
from app.core.database import get_db
from app.users.models.user import User
from app.users.repositories.api_key_repository import ApiKeyRepository
from app.users.repositories.user_repository import UserRepository
from app.users.services.api_key_service import ApiKeyService

__all__ = ["get_db", "get_current_user"]

API_KEY_HEADER = "x-adus-api-key"

# Registers the API-key header as an OpenAPI security scheme so Swagger's
# "Authorize" button shows an X-ADUS-API-KEY field. auto_error=False keeps the
# real resolution below (and the Clerk fallback) unchanged — this is docs-only.
api_key_scheme = APIKeyHeader(name="X-ADUS-API-KEY", auto_error=False)

# Paths served without authentication. The app-level get_current_user
# dependency runs for every route (FastAPI only exempts /docs, /redoc,
# /openapi.json), so public routes must be allow-listed here. Exact match.
PUBLIC_PATHS = frozenset({"/health"})


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _api_key: str | None = Depends(api_key_scheme),
) -> User | None:
    """Resolve the calling user from either auth credential.

    Two independent, Clerk-optional paths, checked in this order:
      1. ``X-ADUS-API-KEY`` header  -> API-key auth (CLI / external teams)
      2. ``Authorization: Bearer``  -> Clerk JWT auth (app / browser users)

    Both resolve to the same ``User``. Lives in this shared module so domain
    routers can depend on it without importing one another. Returns ``None``
    for allow-listed public paths (see ``PUBLIC_PATHS``).
    """
    if request.url.path in PUBLIC_PATHS:
        return None

    api_key = request.headers.get(API_KEY_HEADER)
    if api_key:
        return await _user_from_api_key(api_key, db)

    return await _user_from_clerk_token(request, db)


async def _user_from_api_key(api_key: str, db: AsyncSession) -> User:
    service = ApiKeyService(ApiKeyRepository(db), UserRepository(db))
    user = await service.resolve_user(api_key)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user


async def _user_from_clerk_token(request: Request, db: AsyncSession) -> User:
    """Verify the Clerk JWT and resolve the calling user from our DB."""
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    claims = await verify_clerk_token(parts[1])
    clerk_id = claims.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    user = await UserRepository(db).get_by_clerk_id(clerk_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not registered")

    return user
