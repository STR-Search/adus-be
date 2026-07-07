from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateApiKeyPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ApiKeyResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class CreateApiKeyResult(ApiKeyResult):
    # The plaintext key — returned ONCE at creation and never again.
    api_key: str


class ApiKeyListResult(BaseModel):
    items: list[ApiKeyResult] = Field(default_factory=list)
