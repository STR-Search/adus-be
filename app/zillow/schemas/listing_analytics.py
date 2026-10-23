from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.core.analytics.schemas import GroupRow


class IntakeGroupBy(StrEnum):
    NONE = "none"
    PRESET = "preset"
    # A listing's market is its preset's market.
    MARKET = "market"


class PresetRun(BaseModel):
    key: str
    label: str
    last_run: datetime | None
    next_run: datetime | None
    last_full_run: datetime | None
    # next_run is in the past.
    overdue: bool


class StalePresetRow(GroupRow):
    stale: int


class StaleListings(BaseModel):
    total: int
    stale_after_days: int
    presets: list[StalePresetRow]
