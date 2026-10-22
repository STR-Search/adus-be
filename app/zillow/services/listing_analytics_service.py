import uuid
from collections import defaultdict
from datetime import date

from app.core.analytics.ordering import fill_series, order_open, order_ranked
from app.core.analytics.schemas import (
    Breakdown,
    BreakdownItem,
    Granularity,
    Series,
    breakdown,
    humanize,
)
from app.zillow.repositories.listing_analytics_repository import (
    ListingAnalyticsRepository,
)
from app.zillow.schemas.listing_analytics import (
    PresetRun,
    StaleListings,
    StalePresetRow,
)


class ListingAnalyticsService:
    def __init__(self, repository: ListingAnalyticsRepository):
        self.repository = repository

    async def get_home_status_breakdown(
        self,
        *,
        preset_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> Breakdown:
        rows = await self.repository.count_by_home_status(
            preset_id=preset_id,
            created_from=created_from,
            created_to=created_to,
        )
        # Some scraped rows carry "" rather than NULL; both mean "unknown".
        counts: dict[str | None, int] = defaultdict(int)
        for status, count in rows:
            counts[status or None] += count
        return breakdown(
            order_open(
                BreakdownItem(
                    key=status,
                    label=humanize(status) if status else "Unknown",
                    count=count,
                )
                for status, count in counts.items()
            )
        )

    async def get_intake(
        self,
        *,
        granularity: Granularity = Granularity.WEEK,
        group_by_preset: bool = False,
        preset_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> list[Series]:
        rows = await self.repository.intake(
            granularity=granularity,
            group_by_preset=group_by_preset,
            preset_id=preset_id,
            created_from=created_from,
            created_to=created_to,
        )
        counts: dict[uuid.UUID | None, dict[date, int]] = defaultdict(dict)
        names: dict[uuid.UUID | None, str] = {None: "All listings"}
        for group, name, start, count in rows:
            counts[group][start] = count
            if group is not None:
                names[group] = name
        if not group_by_preset:
            counts.setdefault(None, {})

        # Every series spans the same periods, so charts line up: the requested
        # range, or the first-to-last period with data across all series.
        all_starts = [start for points in counts.values() for start in points]
        start = created_from or (min(all_starts) if all_starts else None)
        end = created_to or (max(all_starts) if all_starts else None)
        series = [
            (
                sum(points.values()),
                Series(
                    key=None if group is None else str(group),
                    label=names[group],
                    points=fill_series(
                        points, start=start, end=end, granularity=granularity
                    ),
                ),
            )
            for group, points in counts.items()
        ]
        # Ordering Rule 3 between series, by total count.
        series.sort(key=lambda item: (-item[0], item[1].label, item[1].key or ""))
        return [s for _, s in series]

    async def get_preset_runs(self) -> list[PresetRun]:
        runs = [
            PresetRun(
                key=str(preset_id),
                label=name,
                last_run=last_run,
                next_run=next_run,
                last_full_run=last_full_run,
                overdue=bool(overdue),
            )
            for preset_id, name, last_run, next_run, last_full_run, overdue in (
                await self.repository.preset_runs()
            )
        ]
        # The presets most in need of attention lead: overdue first, then the
        # oldest run (never-run presets first of all), then name.
        return sorted(
            runs,
            key=lambda run: (
                not run.overdue,
                run.last_run is not None,
                run.last_run.timestamp() if run.last_run else 0,
                run.label,
            ),
        )

    async def get_stale_listings(
        self, *, stale_after_days: int = 14, preset_id: uuid.UUID | None = None
    ) -> StaleListings:
        presets = [
            StalePresetRow(key=str(group), label=name, stale=count)
            for group, name, count in await self.repository.count_stale_by_preset(
                stale_after_days=stale_after_days, preset_id=preset_id
            )
        ]
        return StaleListings(
            total=sum(row.stale for row in presets),
            stale_after_days=stale_after_days,
            presets=order_ranked(presets, by="stale"),
        )
