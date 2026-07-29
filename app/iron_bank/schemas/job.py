import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobCreatedResponse(BaseModel):
    """Returned with 202 when a batch job is accepted."""

    id: uuid.UUID
    status: str


class JobStatusResponse(BaseModel):
    """Polling target for a job's live status and eventual result."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    status: str
    params: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
