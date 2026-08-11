from fastapi import HTTPException

from app.core.logger import logger
from app.users.schemas.user import UserListResult
from app.users.services.user_service import UserService


class UserController:
    """HTTP-facing layer for the users domain — one controller for all of it."""

    def __init__(self, service: UserService):
        self.service = service

    async def get_users(self, *, detailed: bool = False) -> UserListResult:
        try:
            return await self.service.get_all(detailed=detailed)
        except Exception as e:
            logger.error(
                "users.get_users.error",
                detailed=detailed,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch users")
