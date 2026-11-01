from collections import defaultdict
from collections.abc import Callable
from datetime import date

from app.analytics.repositories.status_history_analytics_repository import (
    StatusHistoryAnalyticsRepository,
)
from app.analytics.schemas.status_history import (
    AnalystApproval,
    AnalystApprovalRow,
    AnalystOutputRow,
    ApprovalWait,
    ApprovalWaitRow,
    BacklogAge,
    BacklogRow,
    TeamOutput,
    TimeToPresent,
)
from app.analytics.services.pipeline_analytics_service import LIVE_STATUSES
from app.core.analytics.ordering import fill_series, order_fixed, order_ranked
from app.core.analytics.schemas import Granularity, MedianValue, Series, ratio
from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.underwriting_analytics import UnderwritingAnalyticsFilters
from app.iron_bank.services.analytics.underwriting_analytics_service import (
    DELETED_STATUSES,
    PRESENTED_STATUSES,
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
        label = await self._user_labeler(
            actor for actor, *_ in analyst_rows + presented_rows
        )

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

    async def get_analyst_approval(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        completed_from: date | None = None,
        completed_to: date | None = None,
    ) -> AnalystApproval:
        rows = await self.repository.approval_outcomes(
            filters,
            approved=PRESENTED_STATUSES,
            rejected=DELETED_STATUSES,
            completed_from=completed_from,
            completed_to=completed_to,
        )
        label = await self._user_labeler(actor for actor, _, _ in rows)
        by_analyst: dict[int | None, dict[str, int]] = defaultdict(dict)
        for actor, outcome, count in rows:
            by_analyst[actor][outcome] = count
        totals: dict[str, int] = defaultdict(int)
        for outcome_counts in by_analyst.values():
            for outcome, count in outcome_counts.items():
                totals[outcome] += count
        return AnalystApproval(
            overall=self._approval_row(None, "All analysts", totals),
            analysts=order_ranked(
                (
                    self._approval_row(
                        None if actor is None else str(actor), label(actor), counts
                    )
                    for actor, counts in by_analyst.items()
                ),
                by="completed",
            ),
        )

    async def get_approval_wait(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        presented_from: date | None = None,
        presented_to: date | None = None,
    ) -> ApprovalWait:
        dates = dict(presented_from=presented_from, presented_to=presented_to)
        (overall,) = await self.repository.approval_wait(
            filters, group_by_approver=False, **dates
        )
        per_approver = await self.repository.approval_wait(
            filters, group_by_approver=True, **dates
        )
        label = await self._user_labeler(row["approver"] for row in per_approver)

        def row(key: str | None, name: str, values: dict) -> ApprovalWaitRow:
            return ApprovalWaitRow(
                key=key,
                label=name,
                median_days=MedianValue(
                    value=_float(values["median_days"]),
                    sample_size=values["deals"],
                ),
                p75_days=_float(values["p75_days"]),
            )

        rows = [
            row(
                None if r["approver"] is None else str(r["approver"]),
                label(r["approver"]),
                r,
            )
            for r in per_approver
        ]
        # Ranked like a table: most deals first, unknown last.
        rows.sort(
            key=lambda r: (
                r.key is None,
                -r.median_days.sample_size,
                r.label,
                r.key or "",
            )
        )
        return ApprovalWait(
            overall=row(None, "All approvers", overall), by_approver=rows
        )

    async def _user_labeler(self, actors) -> Callable[[int | None], str]:
        """A ``user id -> display label`` function for the given actors."""
        names = await self.repository.user_names(
            sorted({actor for actor in actors if actor is not None})
        )

        def label(actor: int | None) -> str:
            if actor is None:
                return UNKNOWN_USER_LABEL
            return names.get(actor, f"User {actor}")

        return label

    @staticmethod
    def _approval_row(
        key: str | None, label: str, counts: dict[str, int]
    ) -> AnalystApprovalRow:
        approved = counts.get("approved", 0)
        rejected = counts.get("rejected", 0)
        pending = counts.get("pending", 0)
        return AnalystApprovalRow(
            key=key,
            label=label,
            completed=approved + rejected + pending,
            approved=approved,
            rejected=rejected,
            pending=pending,
            approval_rate=ratio(approved, approved + rejected),
        )

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
