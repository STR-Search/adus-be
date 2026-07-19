from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BaseResponse(BaseModel):
    """Response base enabling ORM attribute reads (mirrors markets' BaseResponse)."""

    model_config = {"from_attributes": True}


class ReferenceDataOption(BaseResponse):
    """A single option as returned to consumers (grouped under its set_code)."""

    key: str
    label: str
    sort_order: int
    is_active: bool
    is_default: bool
    metadata: dict[str, Any] | None = None


class ReferenceDataResult(BaseModel):
    """Options grouped by ``set_code``."""

    options: dict[str, list[ReferenceDataOption]]


class CreateEnumOptionPayload(BaseModel):
    domain: str
    set_code: str
    key: str
    label: str
    sort_order: int = 0
    is_active: bool = True
    is_default: bool = False
    metadata: dict[str, Any] | None = None


class UpdateEnumOptionPayload(BaseModel):
    label: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    is_default: bool | None = None
    metadata: dict[str, Any] | None = None


class EnumOptionRead(BaseResponse):
    """Full option row (admin CRUD responses)."""

    id: int
    domain: str
    set_code: str
    key: str
    label: str
    sort_order: int
    is_active: bool
    is_default: bool
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
