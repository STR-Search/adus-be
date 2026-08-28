from sqlalchemy.exc import IntegrityError

from app.users.models.saved_search import SavedSearch
from app.users.repositories.saved_search_repository import SavedSearchRepository
from app.users.schemas.saved_search import (
    CreateSavedSearchPayload,
    UpdateSavedSearchPayload,
)


class DuplicateSavedSearchNameError(Exception):
    """The user already has a search under this name for this resource.

    Carries the existing row's id so the caller can point the client at the
    search to PATCH instead of leaving it to guess.
    """

    def __init__(self, name: str, existing_id: int | None):
        super().__init__(f"A saved search named '{name}' already exists")
        self.name = name
        self.existing_id = existing_id


class SavedSearchService:
    def __init__(self, repository: SavedSearchRepository):
        self.repository = repository

    async def list_for_user(
        self, *, user_id: int, resource: str | None = None
    ) -> list[SavedSearch]:
        return await self.repository.list_by_user(user_id=user_id, resource=resource)

    async def get_for_user(
        self, *, saved_search_id: int, user_id: int
    ) -> SavedSearch | None:
        return await self.repository.get_by_id_for_user(
            saved_search_id=saved_search_id, user_id=user_id
        )

    async def create(
        self, *, user_id: int, payload: CreateSavedSearchPayload
    ) -> SavedSearch:
        try:
            return await self.repository.create(
                user_id=user_id,
                resource=payload.resource,
                name=payload.name,
                filters=payload.filters,
                query_string=payload.query_string,
            )
        except IntegrityError:
            # The uniqueness check happens here rather than as a pre-flight
            # SELECT so two concurrent saves of the same name can't both pass
            # the check and race to insert.
            await self.repository.db.rollback()
            raise await self._duplicate_error(
                user_id=user_id, resource=payload.resource, name=payload.name
            )

    async def update(
        self, *, saved_search: SavedSearch, payload: UpdateSavedSearchPayload
    ) -> SavedSearch:
        # exclude_unset, not exclude_none: an omitted query_string must be left
        # as-is, while an explicit null is a request to clear it.
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return saved_search
        try:
            return await self.repository.update(saved_search, changes)
        except IntegrityError:
            await self.repository.db.rollback()
            raise await self._duplicate_error(
                user_id=saved_search.user_id,
                resource=saved_search.resource,
                name=changes.get("name", saved_search.name),
            )

    async def delete(self, saved_search: SavedSearch) -> None:
        await self.repository.delete(saved_search)

    async def _duplicate_error(
        self, *, user_id: int, resource: str, name: str
    ) -> DuplicateSavedSearchNameError:
        existing = await self.repository.get_by_name_for_user(
            user_id=user_id, resource=resource, name=name
        )
        return DuplicateSavedSearchNameError(
            name=name, existing_id=existing.id if existing else None
        )
