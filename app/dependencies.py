from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.clerk import verify_clerk_token
from app.core.database import get_db
from app.users.models.user import User
from app.users.repositories.user_repository import UserRepository

__all__ = ["get_db", "get_current_user"]


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify the Clerk JWT and resolve the calling user from our DB.

    Lives in this shared module so domain routers can depend on it without
    importing one another.
    """
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
