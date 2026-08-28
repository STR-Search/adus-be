from fastapi import HTTPException

from app.core.logger import logger
from app.users.schemas.saved_search import (
    CreateSavedSearchPayload,
    SavedSearchListResult,
    SavedSearchResult,
    UpdateSavedSearchPayload,
)
from app.users.services.saved_search_service import (
    DuplicateSavedSearchNameError,
    SavedSearchService,
)


class SavedSearchController:
    def __init__(self, service: SavedSearchService):
        self.service = service

    async def list_saved_searches(
        self, *, user_id: int, resource: str | None = None
    ) -> SavedSearchListResult:
        try:
            items = await self.service.list_for_user(
                user_id=user_id, resource=resource
            )
            return SavedSearchListResult(
                items=[SavedSearchResult.model_validate(item) for item in items]
            )
        except Exception as e:
            logger.error(
                "users.list_saved_searches.error",
                user_id=user_id,
                resource=resource,
                error=str(e),
            )
            raise HTTPException(
                status_code=500, detail="Failed to fetch saved searches"
            )

    async def create_saved_search(
        self, *, user_id: int, payload: CreateSavedSearchPayload
    ) -> SavedSearchResult:
        try:
            created = await self.service.create(user_id=user_id, payload=payload)
            return SavedSearchResult.model_validate(created)
        except DuplicateSavedSearchNameError as e:
            raise HTTPException(
                status_code=409,
                detail={"message": str(e), "existing_id": e.existing_id},
            )
        except Exception as e:
            logger.error(
                "users.create_saved_search.error",
                user_id=user_id,
                resource=payload.resource,
                error=str(e),
            )
            raise HTTPException(
                status_code=500, detail="Failed to create saved search"
            )

    async def update_saved_search(
        self, *, saved_search_id: int, user_id: int, payload: UpdateSavedSearchPayload
    ) -> SavedSearchResult:
        saved_search = await self._get_owned_or_404(
            saved_search_id=saved_search_id, user_id=user_id
        )
        try:
            updated = await self.service.update(
                saved_search=saved_search, payload=payload
            )
            return SavedSearchResult.model_validate(updated)
        except DuplicateSavedSearchNameError as e:
            raise HTTPException(
                status_code=409,
                detail={"message": str(e), "existing_id": e.existing_id},
            )
        except Exception as e:
            logger.error(
                "users.update_saved_search.error",
                user_id=user_id,
                saved_search_id=saved_search_id,
                error=str(e),
            )
            raise HTTPException(
                status_code=500, detail="Failed to update saved search"
            )

    async def delete_saved_search(self, *, saved_search_id: int, user_id: int) -> None:
        saved_search = await self._get_owned_or_404(
            saved_search_id=saved_search_id, user_id=user_id
        )
        try:
            await self.service.delete(saved_search)
        except Exception as e:
            logger.error(
                "users.delete_saved_search.error",
                user_id=user_id,
                saved_search_id=saved_search_id,
                error=str(e),
            )
            raise HTTPException(
                status_code=500, detail="Failed to delete saved search"
            )

    async def _get_owned_or_404(self, *, saved_search_id: int, user_id: int):
        """The lookup is user-scoped, so another user's row 404s like a missing one."""
        saved_search = await self.service.get_for_user(
            saved_search_id=saved_search_id, user_id=user_id
        )
        if saved_search is None:
            raise HTTPException(status_code=404, detail="Saved search not found")
        return saved_search
