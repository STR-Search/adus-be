from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.users.controllers.saved_search_controller import SavedSearchController
from app.users.controllers.user_controller import UserController
from app.users.repositories.api_key_repository import ApiKeyRepository
from app.users.repositories.saved_search_repository import SavedSearchRepository
from app.users.repositories.user_repository import UserRepository
from app.users.schemas.api_key import (
    ApiKeyListResult,
    ApiKeyResult,
    CreateApiKeyPayload,
    CreateApiKeyResult,
)
from app.users.schemas.saved_search import (
    CreateSavedSearchPayload,
    SavedSearchListResult,
    SavedSearchResult,
    UpdateSavedSearchPayload,
)
from app.users.schemas.user import UserListResult
from app.users.services.api_key_service import ApiKeyService
from app.users.services.saved_search_service import SavedSearchService
from app.users.services.user_service import UserService
import app.users.models  # noqa: F401 — ensures all models are registered with SQLAlchemy

router = APIRouter(prefix="/users", tags=["users"])


def get_api_key_service(db: AsyncSession = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(ApiKeyRepository(db), UserRepository(db))


def get_user_controller(db: AsyncSession = Depends(get_db)) -> UserController:
    return UserController(UserService(UserRepository(db)))


def get_saved_search_controller(
    db: AsyncSession = Depends(get_db),
) -> SavedSearchController:
    return SavedSearchController(SavedSearchService(SavedSearchRepository(db)))


@router.get("", response_model=UserListResult, tags=["users"])
async def list_users(
    detailed: bool = Query(
        False,
        description=(
            "Return the full user row (clerk_id, timestamps) instead of the "
            "id/email/name summary."
        ),
    ),
    controller: UserController = Depends(get_user_controller),
):
    return await controller.get_users(detailed=detailed)


@router.post(
    "/api-keys",
    response_model=CreateApiKeyResult,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
async def create_api_key(
    payload: CreateApiKeyPayload,
    service: ApiKeyService = Depends(get_api_key_service),
    current_user=Depends(get_current_user),
):
    api_key, raw_key = await service.create_key(
        user_id=current_user.id, name=payload.name
    )
    return CreateApiKeyResult(
        **ApiKeyResult.model_validate(api_key).model_dump(),
        api_key=raw_key,
    )


@router.get("/api-keys", response_model=ApiKeyListResult, tags=["users"])
async def list_api_keys(
    service: ApiKeyService = Depends(get_api_key_service),
    current_user=Depends(get_current_user),
):
    keys = await service.list_keys(current_user.id)
    return ApiKeyListResult(items=[ApiKeyResult.model_validate(k) for k in keys])


@router.delete(
    "/api-keys/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["users"],
)
async def revoke_api_key(
    api_key_id: int,
    service: ApiKeyService = Depends(get_api_key_service),
    current_user=Depends(get_current_user),
):
    revoked = await service.revoke_key(api_key_id=api_key_id, user_id=current_user.id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")


# Saved searches. Every route is scoped to the authenticated user — the owner
# is taken from the token, never from the path or body, so a user can only ever
# read and write their own rows.


@router.get("/saved-searches", response_model=SavedSearchListResult, tags=["users"])
async def list_saved_searches(
    resource: str | None = Query(
        None,
        description=(
            "Filter to one list view, e.g. 'iron_bank.underwritings'. "
            "All of the user's saved searches if omitted."
        ),
    ),
    controller: SavedSearchController = Depends(get_saved_search_controller),
    current_user=Depends(get_current_user),
):
    return await controller.list_saved_searches(
        user_id=current_user.id, resource=resource
    )


@router.post(
    "/saved-searches",
    response_model=SavedSearchResult,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
async def create_saved_search(
    payload: CreateSavedSearchPayload,
    controller: SavedSearchController = Depends(get_saved_search_controller),
    current_user=Depends(get_current_user),
):
    return await controller.create_saved_search(
        user_id=current_user.id, payload=payload
    )


@router.patch(
    "/saved-searches/{saved_search_id}",
    response_model=SavedSearchResult,
    tags=["users"],
)
async def update_saved_search(
    saved_search_id: int,
    payload: UpdateSavedSearchPayload,
    controller: SavedSearchController = Depends(get_saved_search_controller),
    current_user=Depends(get_current_user),
):
    return await controller.update_saved_search(
        saved_search_id=saved_search_id,
        user_id=current_user.id,
        payload=payload,
    )


@router.delete(
    "/saved-searches/{saved_search_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["users"],
)
async def delete_saved_search(
    saved_search_id: int,
    controller: SavedSearchController = Depends(get_saved_search_controller),
    current_user=Depends(get_current_user),
):
    await controller.delete_saved_search(
        saved_search_id=saved_search_id, user_id=current_user.id
    )
