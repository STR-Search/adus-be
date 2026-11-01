from collections import defaultdict
from datetime import date

from app.analytics.repositories.status_history_analytics_repository import (
    StatusHistoryAnalyticsRepository,
)
from app.analytics.schemas.status_history import (
    AnalystOutputRow,
    BacklogAge,
    BacklogRow,
    TeamOutput,
    TimeToPresent,
)
from app.analytics.services.pipeline_analytics_service import LIVE_STATUSES
from app.core.analytics.ordering import fill_series, order_fixed, order_ranked
from app.core.analytics.schemas import Granularity, MedianValue, Series
from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.underwriting_analytics import UnderwritingAnalyticsFilters
from app.iron_bank.services.analytics.underwriting_analytics_service import (
    status_items,
)

# Metric 8: (key, label, lower inclusive, upper exclusive) in days.
BACKLOG_AGE_BUCKETS: tuple[tuple[str, str, int | None, int | None], ...] = (
    ("under_3d", "Under 3 days", None, 3),
    ("3_7d", "3 to 7 days", 3, 7),
    ("7_14d", "7 to 14 days", 7, 14),
    ("over_14d", "Over 14 days", 14, None),
)

# Metric 27: the statuses an analyst moves a deal to.
ANALYST_STATUSES: tuple[DealStatus, ...] = (
    DealStatus.ANALYST_STARTED,
    DealStatus.ANALYST_COMPLETED,
)

UNKNOWN_USER_LABEL = "Unknown"


def _float(value) -> float | None:
    return None if value is None else float(value)


class StatusHistoryAnalyticsService:
    """Shapes the metrics read from the deal-status history (process log)."""

    def __init__(self, repository: StatusHistoryAnalyticsRepository):
        self.repository = repository

    async def get_backlog_age(
        self, filters: UnderwritingAnalyticsFilters
    ) -> BacklogAge:
        statuses = tuple(
            status
            for status in LIVE_STATUSES
            if filters.deal_status is None or status in filters.deal_status
        )
        kwargs = dict(
            statuses=statuses,
            buckets=[
                (key, lower, upper) for key, _, lower, upper in BACKLOG_AGE_BUCKETS
            ],
        )
        (overall,) = await self.repository.backlog_age(
            filters, group_by_status=False, **kwargs
        )
        per_status = {
            row["deal_status"]: row
            for row in await self.repository.backlog_age(
                filters, group_by_status=True, **kwargs
            )
        }
        return BacklogAge(
            overall=self._backlog_row(None, "All statuses", overall),
            by_status=[
                self._backlog_row(item.key, item.label, per_status.get(item.key))
                for item in status_items(
                    {key: row["deals"] for key, row in per_status.items()}, statuses
                )
            ],
        )

    async def get_time_to_present(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        presented_from: date | None = None,
        presented_to: date | None = None,
    ) -> TimeToPresent:
        row = await self.repository.time_to_present(
            filters, presented_from=presented_from, presented_to=presented_to
        )
        return TimeToPresent(
            median_days=MedianValue(
                value=_float(row["median_days"]), sample_size=row["measured"]
            ),
            p75_days=_float(row["p75_days"]),
            observed=row["observed"],
            estimated=row["measured"] - row["observed"],
        )

    async def get_team_output(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        granularity: Granularity = Granularity.WEEK,
        occurred_from: date | None = None,
        occurred_to: date | None = None,
    ) -> TeamOutput:
        dates = dict(occurred_from=occurred_from, occurred_to=occurred_to)
        analyst_rows = await self.repository.moved_to_by_actor(
            filters, ANALYST_STATUSES, **dates
        )
        presented_rows = await self.repository.moved_to_by_actor_and_period(
            filters, DealStatus.PRESENT_TO_CLIENTS, granularity, **dates
        )
        names = await self.repository.user_names(
            sorted(
                {
                    actor
                    for actor, *_ in analyst_rows + presented_rows
                    if actor is not None
                }
            )
        )

        def label(actor: int | None) -> str:
            if actor is None:
                return UNKNOWN_USER_LABEL
            return names.get(actor, f"User {actor}")

        by_analyst: dict[int | None, dict[str, int]] = defaultdict(dict)
        for actor, status, count in analyst_rows:
            by_analyst[actor][status] = count
        analysts = order_ranked(
            (
                AnalystOutputRow(
                    key=None if actor is None else str(actor),
                    label=label(actor),
                    started=counts.get(DealStatus.ANALYST_STARTED.value, 0),
                    completed=counts.get(DealStatus.ANALYST_COMPLETED.value, 0),
                )
                for actor, counts in by_analyst.items()
            ),
            by="completed",
        )

        by_approver: dict[int | None, dict[date, int]] = defaultdict(dict)
        for actor, start, count in presented_rows:
            by_approver[actor][start] = count
        # One shared period range, so every approver's line covers the same weeks.
        periods = [start for _, start, _ in presented_rows]
        first = occurred_from or (min(periods) if periods else None)
        last = occurred_to or (max(periods) if periods else None)
        series = [
            Series(
                key=None if actor is None else str(actor),
                label=label(actor),
                points=fill_series(
                    counts, start=first, end=last, granularity=granularity
                ),
            )
            for actor, counts in by_approver.items()
        ]
        # Same order as a ranked table: most presented first, unknown last.
        series.sort(
            key=lambda s: (
                s.key is None,
                -sum(point.count for point in s.points),
                s.label,
                s.key or "",
            )
        )
        return TeamOutput(analysts=analysts, presented_by_approver=series)

    @staticmethod
    def _backlog_row(key: str | None, label: str, row: dict | None) -> BacklogRow:
        row = row or {}
        deals = row.get("deals", 0)
        counts = {k: row.get(k, 0) for k, _, _, _ in BACKLOG_AGE_BUCKETS}
        # Deals with no date at all fall in no bucket; show them as unknown.
        counts[None] = deals - sum(counts.values())
        return BacklogRow(
            key=key,
            label=label,
            deals=deals,
            by_age=order_fixed(
                counts,
                known=[(k, lbl) for k, lbl, _, _ in BACKLOG_AGE_BUCKETS],
                unknown_label="No date",
            ),
            median_days=MedianValue(
                value=_float(row.get("median_days")),
                sample_size=row.get("measured", 0),
            ),
            observed=row.get("observed", 0),
        )
