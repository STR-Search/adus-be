from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.users.repositories.api_key_repository import ApiKeyRepository
from app.users.repositories.user_repository import UserRepository
from app.users.schemas.api_key import (
    ApiKeyListResult,
    ApiKeyResult,
    CreateApiKeyPayload,
    CreateApiKeyResult,
)
from app.users.services.api_key_service import ApiKeyService
import app.users.models  # noqa: F401 — ensures all models are registered with SQLAlchemy

router = APIRouter(prefix="/users", tags=["users"])


def get_api_key_service(db: AsyncSession = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(ApiKeyRepository(db), UserRepository(db))


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
