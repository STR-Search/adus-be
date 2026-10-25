from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class SnapshotInput:
    """A subject's state, built by the owning domain.

    ``payload`` must already be JSON-ready (decimals as strings, datetimes as
    ISO strings) so the same state always hashes the same way.
    """

    schema_version: int
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class HeadSeed:
    """A first row to seed for a subject that has no chain yet (backfills)."""

    subject_type: str
    subject_id: int
    flow: str
    to_status: str
    source: str
    actor_user_id: int | None = None
    note: str | None = None
    occurred_at: datetime | None = None
    snapshot: SnapshotInput | None = None


class TransitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    subject_type: str
    subject_id: int
    flow: str
    previous_transition_id: int | None
    from_status: str | None
    to_status: str
    actor_user_id: int | None
    source: str
    note: str | None
    # Reads the ORM attribute ``metadata_``; exposed as ``metadata``.
    metadata: dict[str, Any] | None = Field(validation_alias="metadata_")
    snapshot_id: int | None
    occurred_at: datetime
