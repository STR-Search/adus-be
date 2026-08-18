from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserSummary(BaseModel):
    """Minimal user shape for pickers and assignee dropdowns."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class UserDetail(UserSummary):
    """Full users.users row."""

    clerk_id: str
    is_deleted: bool | None = None
    created_at: datetime
    updated_at: datetime


class UserListResult(BaseModel):
    """Unpaginated user list — summaries by default, full rows when the caller
    asks for ``detailed=true``."""

    # UserDetail first: it's a superset of UserSummary, so a summary-only list
    # fails the detail branch and falls through, while a detail list keeps its
    # extra fields instead of being narrowed to the summary shape.
    items: list[UserDetail] | list[UserSummary] = Field(default_factory=list)
    total: int
