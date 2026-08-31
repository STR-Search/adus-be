from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models.saved_search import SavedSearch


class SavedSearchRepository:
    """Every method is scoped by ``user_id``.

    Saved-search ids are sequential and guessable, so ownership is enforced in
    the WHERE clause rather than by a check after the fetch — a row belonging
    to another user must be indistinguishable from one that does not exist.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_user(
        self, *, user_id: int, resource: str | None = None
    ) -> list[SavedSearch]:
        query = select(SavedSearch).where(SavedSearch.user_id == user_id)
        if resource is not None:
            query = query.where(SavedSearch.resource == resource)
        result = await self.db.execute(
            query.order_by(SavedSearch.updated_at.desc(), SavedSearch.id.desc())
        )
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self, *, saved_search_id: int, user_id: int
    ) -> SavedSearch | None:
        result = await self.db.execute(
            select(SavedSearch).where(
                SavedSearch.id == saved_search_id,
                SavedSearch.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name_for_user(
        self, *, user_id: int, resource: str, name: str
    ) -> SavedSearch | None:
        result = await self.db.execute(
            select(SavedSearch).where(
                SavedSearch.user_id == user_id,
                SavedSearch.resource == resource,
                SavedSearch.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        resource: str,
        name: str,
        filters: dict[str, Any],
        query_string: str | None,
    ) -> SavedSearch:
        saved_search = SavedSearch(
            user_id=user_id,
            resource=resource,
            name=name,
            filters=filters,
            query_string=query_string,
        )
        self.db.add(saved_search)
        await self.db.commit()
        await self.db.refresh(saved_search)
        return saved_search

    async def update(
        self, saved_search: SavedSearch, changes: dict[str, Any]
    ) -> SavedSearch:
        for field, value in changes.items():
            setattr(saved_search, field, value)
        await self.db.commit()
        await self.db.refresh(saved_search)
        return saved_search

    async def delete(self, saved_search: SavedSearch) -> None:
        await self.db.delete(saved_search)
        await self.db.commit()
