from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models.api_key import ApiKey


class ApiKeyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_by_hash(self, key_hash: str) -> ApiKey | None:
        """Returns the active (non-revoked) key matching the hash, if any."""
        result = await self.db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self, *, user_id: int, name: str, prefix: str, key_hash: str
    ) -> ApiKey:
        api_key = ApiKey(
            user_id=user_id,
            name=name,
            prefix=prefix,
            key_hash=key_hash,
        )
        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)
        return api_key

    async def list_by_user(self, user_id: int) -> list[ApiKey]:
        result = await self.db.execute(
            select(ApiKey)
            .where(ApiKey.user_id == user_id)
            .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
        )
        return list(result.scalars().all())

    async def get_by_id_for_user(self, api_key_id: int, user_id: int) -> ApiKey | None:
        result = await self.db.execute(
            select(ApiKey).where(
                ApiKey.id == api_key_id,
                ApiKey.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def revoke(self, api_key: ApiKey) -> ApiKey:
        api_key.revoked_at = func.now()
        await self.db.commit()
        await self.db.refresh(api_key)
        return api_key
