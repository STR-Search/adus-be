from datetime import date
from enum import StrEnum

from pydantic import BaseModel


class Granularity(StrEnum):
    # Postgres ``date_trunc`` field names; weeks start on Monday.
    DAY = "day"
    WEEK = "week"


class BreakdownItem(BaseModel):
    # Stable slug; ``None`` = unknown/unset.
    key: str | None
    label: str
    count: int


class Breakdown(BaseModel):
    total: int
    items: list[BreakdownItem]


class SeriesPoint(BaseModel):
    period_start: date
    count: int


class Series(BaseModel):
    key: str | None
    label: str
    points: list[SeriesPoint]


class GroupRow(BaseModel):
    """One row of a per-group table (market, preset, ...).

    ``key`` is the group's id as a string; ``None`` = unassigned. Subclasses add
    the metric-specific numbers.
    """

    key: str | None
    label: str


class MedianValue(BaseModel):
    value: float | None
    # Number of non-null values the median is based on.
    sample_size: int


def ratio(numerator: int, denominator: int) -> float | None:
    """A rate as a fraction between 0 and 1.

    ``None`` over a zero denominator, so "no data" is never shown as 0%.
    Responses carry the numerator and denominator alongside, so the frontend
    never divides.
    """
    return numerator / denominator if denominator else None


def breakdown(items: list[BreakdownItem]) -> Breakdown:
    return Breakdown(total=sum(item.count for item in items), items=items)


def humanize(value: str) -> str:
    """``batch_prepare_by_preset`` / ``RECENTLY_SOLD`` -> title-cased words."""
    return value.replace("_", " ").title()
