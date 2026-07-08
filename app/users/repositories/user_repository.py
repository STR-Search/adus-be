from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_clerk_id(self, clerk_id: str) -> User | None:
        result = await self.db.execute(
            select(User).where(
                User.clerk_id == clerk_id,
                User.is_deleted.is_not(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.db.execute(
            select(User).where(
                User.id == user_id,
                User.is_deleted.is_not(True),
            )
        )
        return result.scalar_one_or_none()
