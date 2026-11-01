from pydantic import BaseModel

from app.core.analytics.schemas import BreakdownItem, GroupRow, MedianValue, Series


class BacklogRow(BaseModel):
    # deal_status; None = the "All statuses" row.
    key: str | None
    label: str
    deals: int
    # BACKLOG_AGE_BUCKETS in order, zeros filled; a trailing None item counts
    # deals with no date to measure from.
    by_age: list[BreakdownItem]
    median_days: MedianValue
    # Deals whose wait is measured from a logged status change. The rest are
    # estimates: the backfill date, or updated_at when the log is missing or
    # out of step with the deal.
    observed: int


class BacklogAge(BaseModel):
    # Metric 8.
    overall: BacklogRow
    by_status: list[BacklogRow]


class TimeToPresent(BaseModel):
    # Metric 14: days from deal_added to the deal's first presentation.
    median_days: MedianValue
    # The slowest 25% take at least this long.
    p75_days: float | None
    # Presentation time from the status log.
    observed: int
    # Presentation time from deal_approved (presented before the log existed).
    estimated: int


class AnalystOutputRow(GroupRow):
    # Distinct deals this user moved to analyst_started / analyst_completed.
    started: int
    completed: int


class TeamOutput(BaseModel):
    # Metric 27. Only logged status changes count, so history starts at launch.
    analysts: list[AnalystOutputRow]
    # Deals each user moved to present_to_clients, per period; key = user id.
    presented_by_approver: list[Series]
