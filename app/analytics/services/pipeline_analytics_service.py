import uuid
from collections import defaultdict
from datetime import date

from app.analytics.repositories.pipeline_analytics_repository import (
    PipelineAnalyticsRepository,
)
from app.analytics.schemas.pipeline import (
    Coverage,
    CoverageRow,
    OffMarket,
    OffMarketStatusRow,
    PriceDrops,
)
from app.core.analytics.ordering import order_open, order_ranked
from app.core.analytics.schemas import (
    BreakdownItem,
    MedianValue,
    breakdown,
    humanize,
    ratio,
)
from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.schemas.underwriting_analytics import (
    DEFAULT_ANALYTICS_SOURCES,
    UnderwritingAnalyticsFilters,
)
from app.iron_bank.services.analytics.underwriting_analytics_service import (
    ANALYSIS_STATUSES,
    status_items,
)
from app.iron_bank.services.deal_status_service import TERMINAL_DEAL_STATUSES

# "Still in the pipeline": a status is set and the deal can still move.
LIVE_STATUSES: tuple[DealStatus, ...] = tuple(
    status for status in DealStatus if status.value not in TERMINAL_DEAL_STATUSES
)


class PipelineAnalyticsService:
    """Shapes the metrics that join zillow listings to iron_bank underwritings."""

    def __init__(self, repository: PipelineAnalyticsRepository):
        self.repository = repository

    async def get_coverage(
        self,
        *,
        source: tuple[UnderwritingSource, ...] = DEFAULT_ANALYTICS_SOURCES,
        preset_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> Coverage:
        kwargs = dict(
            source=source,
            preset_id=preset_id,
            created_from=created_from,
            created_to=created_to,
        )
        (overall,) = await self.repository.coverage(group_by_preset=False, **kwargs)
        presets = await self.repository.coverage(group_by_preset=True, **kwargs)

        def row(key, label, listings, underwritten, median_days) -> CoverageRow:
            return CoverageRow(
                key=key,
                label=label,
                listings=listings,
                underwritten=underwritten,
                coverage=ratio(underwritten, listings),
                median_days_to_underwrite=None
                if median_days is None
                else float(median_days),
            )

        return Coverage(
            overall=row(None, "All presets", *overall[2:]),
            presets=order_ranked(
                (row(str(group), name, *rest) for group, name, *rest in presets),
                by="listings",
            ),
        )

    async def get_off_market(self, filters: UnderwritingAnalyticsFilters) -> OffMarket:
        by_status: dict[str | None, dict[str | None, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for status, home_status, count in await self.repository.count_off_market(
            filters
        ):
            # "" and NULL both mean the listing's status is unknown.
            by_status[status][home_status or None] += count

        totals = {status: sum(homes.values()) for status, homes in by_status.items()}
        rows = [
            OffMarketStatusRow(
                key=item.key,
                label=item.label,
                off_market=item.count,
                by_home_status=order_open(
                    BreakdownItem(
                        key=home,
                        label=humanize(home) if home else "Unknown",
                        count=count,
                    )
                    for home, count in by_status.get(item.key, {}).items()
                ),
            )
            for item in status_items(totals, filters.deal_status)
        ]
        missed = totals.get(DealStatus.PRESENT_TO_CLIENTS.value, 0)
        presented_total = await self.repository.count_with_status(
            filters, (DealStatus.PRESENT_TO_CLIENTS,)
        )
        return OffMarket(
            by_status=rows,
            missed_deals=missed,
            presented_total=presented_total,
            missed_rate=ratio(missed, presented_total),
            wasted_analysis=sum(totals.get(s.value, 0) for s in ANALYSIS_STATUSES),
        )

    async def get_price_drops(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        changed_from: date | None = None,
        changed_to: date | None = None,
    ) -> PriceDrops:
        statuses = tuple(
            status
            for status in LIVE_STATUSES
            if filters.deal_status is None or status in filters.deal_status
        )
        rows, median, sample_size = await self.repository.price_drops(
            filters, statuses=statuses, changed_from=changed_from, changed_to=changed_to
        )
        return PriceDrops(
            deals=breakdown(status_items(dict(rows), statuses)),
            median_drop_pct=MedianValue(
                value=None if median is None else float(median),
                sample_size=sample_size,
            ),
        )
