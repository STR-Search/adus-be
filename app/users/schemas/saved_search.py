from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Resources are free-form strings rather than an enum: constraining them to a
# known list would mean the users domain carrying knowledge of every other
# domain's list views. The pattern is only here to keep typos and junk out —
# lowercase segments joined by dots, e.g. "iron_bank.underwritings".
RESOURCE_PATTERN = r"^[a-z0-9_]+(\.[a-z0-9_]+)*$"

SavedSearchName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]

SavedSearchFilters = dict[str, Any] | list[Any]


class CreateSavedSearchPayload(BaseModel):
    resource: str = Field(..., min_length=1, max_length=100, pattern=RESOURCE_PATTERN)
    name: SavedSearchName
    filters: SavedSearchFilters
    query_string: str | None = Field(None, max_length=4000)


class UpdateSavedSearchPayload(BaseModel):
    """PATCH payload — every field optional.

    Only fields actually present in the request body are applied, so omitting
    ``query_string`` leaves it alone while sending it as ``null`` clears it.
    ``resource`` is absent by design: moving a saved search between list views
    would produce filters that mean nothing to the destination.
    """

    name: SavedSearchName | None = None
    filters: SavedSearchFilters | None = None
    query_string: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        """``null`` is only meaningful for the nullable column.

        ``name`` and ``filters`` are NOT NULL, so an explicit null would reach
        the DB as a constraint violation and surface as an opaque 500. Only
        ``query_string`` can actually be cleared.
        """
        for field in ("name", "filters"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null; omit it to leave unchanged")
        return self


class SavedSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource: str
    name: str
    filters: SavedSearchFilters
    query_string: str | None = None
    created_at: datetime
    updated_at: datetime


class SavedSearchListResult(BaseModel):
    items: list[SavedSearchResult] = Field(default_factory=list)
