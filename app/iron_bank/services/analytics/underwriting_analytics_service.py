from collections import defaultdict
from collections.abc import Collection, Mapping
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.core.analytics.ordering import (
    fill_periods,
    order_fixed,
    order_open,
    order_ranked,
)
from app.core.analytics.schemas import (
    Breakdown,
    BreakdownItem,
    Granularity,
    MedianValue,
    breakdown,
    humanize,
    ratio,
)
from app.core.reference_data.service import ReferenceDataService
from app.iron_bank.enums import DealStatus
from app.iron_bank.repositories.underwriting_analytics_repository import (
    UnderwritingAnalyticsRepository,
)
from app.iron_bank.schemas.underwriting import MULTI_SELECT_TAG_FIELDS
from app.iron_bank.schemas.underwriting_analytics import (
    DeleteReasonRow,
    DeleteReasons,
    Duplicates,
    JobTypeHealth,
    MarketBreakdown,
    MarketRow,
    PriceBandRow,
    QualityComparison,
    QualityGroup,
    TagMix,
    TemplateProgressPoint,
    UnderwritingAnalyticsFilters,
    UnderwritingCompleteness,
)
from app.iron_bank.services.deal_status_service import STATUS_OPTIONS

# Status subsets the proposal's metric definitions need. Filters for specific
# metrics, not categories: no response returns a constant's name, and a status
# may sit in more than one (client_under_contract is presented *and* won).
# A deal under contract was presented first, so it counts as presented.
PRESENTED_STATUSES: tuple[DealStatus, ...] = (
    DealStatus.PRESENT_TO_CLIENTS,
    DealStatus.CLIENT_UNDER_CONTRACT,
)
WON_STATUSES: tuple[DealStatus, ...] = (DealStatus.CLIENT_UNDER_CONTRACT,)
DELETED_STATUSES: tuple[DealStatus, ...] = (
    DealStatus.DELETE_ZILLOW,
    DealStatus.DELETE_DEAL,
)
# "Still in analysis" for the wasted-effort metric (12).
ANALYSIS_STATUSES: tuple[DealStatus, ...] = (
    DealStatus.ANALYST_STARTED,
    DealStatus.ANALYST_COMPLETED,
    DealStatus.RE_FORECAST_REVENUE,
    DealStatus.AWAITING_REALTOR_DETAILS,
    DealStatus.MAYBE,
)

NO_STATUS_LABEL = "No Status"

# (key, label, lower inclusive, upper exclusive) on purchase_price, low to high.
PRICE_BANDS: tuple[tuple[str, str, Decimal | None, Decimal | None], ...] = (
    ("under_300k", "Under $300k", None, Decimal(300_000)),
    ("300k_500k", "$300k to $500k", Decimal(300_000), Decimal(500_000)),
    ("500k_750k", "$500k to $750k", Decimal(500_000), Decimal(750_000)),
    ("750k_1m", "$750k to $1M", Decimal(750_000), Decimal(1_000_000)),
    ("over_1m", "Over $1M", Decimal(1_000_000), None),
)

# The values the job workflows write (ck_jobs_status), in lifecycle order.
JOB_STATUSES: tuple[tuple[str, str], ...] = (
    ("queued", "Queued"),
    ("running", "Running"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
)

# Metric 24: value driver, market type and guest type.
TAG_MIX_FIELDS: tuple[str, ...] = (
    "core_value_driver",
    "market_type",
    "primary_guest_avatar",
)


class MarketSort(StrEnum):
    UNDERWRITTEN = "underwritten"
    PRESENTED = "presented"
    WON = "won"
    PRESENTED_RATE = "presented_rate"
    WIN_RATE = "win_rate"


def status_options(
    only: Collection[DealStatus] | None = None,
) -> list[tuple[str, str]]:
    """``(key, label)`` in workflow order, optionally narrowed to ``only``."""
    return [
        (status.value, label)
        for status, label, _ in STATUS_OPTIONS
        if only is None or status in only
    ]


def status_items(
    counts: Mapping[str | None, int], only: Collection[DealStatus] | None = None
) -> list[BreakdownItem]:
    """Per-status items in workflow order, zero-filled (ordering Rule 1)."""
    return order_fixed(
        counts, known=status_options(only), unknown_label=NO_STATUS_LABEL
    )


class UnderwritingAnalyticsService:
    def __init__(
        self,
        repository: UnderwritingAnalyticsRepository,
        reference_data_service: ReferenceDataService | None = None,
    ):
        self.repository = repository
        self.reference_data_service = reference_data_service

    async def get_deal_status_breakdown(
        self, filters: UnderwritingAnalyticsFilters
    ) -> Breakdown:
        rows = await self.repository.count_by_deal_status(filters)
        return breakdown(status_items(dict(rows), filters.deal_status))

    async def get_template_progress(
        self, filters: UnderwritingAnalyticsFilters, granularity: Granularity
    ) -> list[TemplateProgressPoint]:
        rows = {
            start: (created, past)
            for start, created, past in await self.repository.template_progress(
                filters, granularity
            )
        }
        points = []
        for period in fill_periods(
            rows,
            start=filters.added_from,
            end=filters.added_to,
            granularity=granularity,
        ):
            created, past = rows.get(period, (0, 0))
            points.append(
                TemplateProgressPoint(
                    period_start=period,
                    created=created,
                    past_template=past,
                    share=ratio(past, created),
                )
            )
        return points

    async def get_market_breakdown(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        market_labels: Mapping[int, str],
        sort: MarketSort = MarketSort.UNDERWRITTEN,
    ) -> MarketBreakdown:
        by_market, overall = _pivot(
            await self.repository.count_by_market_and_status(filters)
        )

        def row(
            key: str | None, label: str, counts: Mapping[str | None, int]
        ) -> MarketRow:
            underwritten = sum(counts.values())
            presented = _sum_statuses(counts, PRESENTED_STATUSES)
            won = _sum_statuses(counts, WON_STATUSES)
            return MarketRow(
                key=key,
                label=label,
                underwritten=underwritten,
                by_status=status_items(counts, filters.deal_status),
                presented=presented,
                won=won,
                presented_rate=ratio(presented, underwritten),
                win_rate=ratio(won, presented),
            )

        return MarketBreakdown(
            overall=row(None, "All markets", overall),
            markets=order_ranked(
                (
                    row(*_market_key_label(market_id, market_labels), counts)
                    for market_id, counts in by_market.items()
                ),
                by=sort.value,
            ),
        )

    async def get_price_bands(
        self, filters: UnderwritingAnalyticsFilters
    ) -> list[PriceBandRow]:
        by_band, _ = _pivot(
            await self.repository.count_by_price_band_and_status(
                filters, [(key, lower, upper) for key, _, lower, upper in PRICE_BANDS]
            )
        )

        def row(key: str | None, label: str) -> PriceBandRow:
            counts = by_band.get(key, {})
            return PriceBandRow(
                key=key,
                label=label,
                total=sum(counts.values()),
                by_status=status_items(counts, filters.deal_status),
            )

        rows = [row(key, label) for key, label, _, _ in PRICE_BANDS]
        if by_band.get(None):
            rows.append(row(None, "No Price"))
        return rows

    async def get_quality_comparison(
        self, filters: UnderwritingAnalyticsFilters
    ) -> QualityComparison:
        groups = []
        for key, label, statuses in (
            ("presented", "Presented", PRESENTED_STATUSES),
            ("deleted", "Deleted", DELETED_STATUSES),
        ):
            values = await self.repository.quality_medians(filters, statuses)
            groups.append(
                QualityGroup(
                    key=key,
                    label=label,
                    statuses=[status.value for status in statuses],
                    deals=values["deals"],
                    median_cash_on_cash=_median(values, "cash_on_cash"),
                    median_deal_score=_median(values, "deal_score"),
                    median_total_oop=_median(values, "total_oop"),
                )
            )
        return QualityComparison(groups=groups)

    async def get_delete_reasons(
        self, filters: UnderwritingAnalyticsFilters, *, market_labels: Mapping[int, str]
    ) -> DeleteReasons:
        filters = filters.model_copy(update={"deal_status": DELETED_STATUSES})
        by_market, overall = _pivot(
            await self.repository.count_by_market_and_status(filters)
        )

        def row(
            key: str | None, label: str, counts: Mapping[str | None, int]
        ) -> DeleteReasonRow:
            return DeleteReasonRow(
                key=key,
                label=label,
                total=sum(counts.values()),
                by_status=status_items(counts, DELETED_STATUSES),
            )

        return DeleteReasons(
            overall=row(None, "All markets", overall),
            markets=order_ranked(
                (
                    row(*_market_key_label(market_id, market_labels), counts)
                    for market_id, counts in by_market.items()
                ),
                by="total",
            ),
        )

    async def get_tag_mix(self, filters: UnderwritingAnalyticsFilters) -> TagMix:
        if filters.deal_status is None:
            filters = filters.model_copy(update={"deal_status": PRESENTED_STATUSES})
        label_map: Mapping[tuple[str, str], str] = {}
        if self.reference_data_service is not None:
            label_map = await self.reference_data_service.get_label_map(
                domain="iron_bank", set_codes=TAG_MIX_FIELDS
            )

        fields = {}
        for field in TAG_MIX_FIELDS:
            deals, rows = await self.repository.count_tags(
                filters, field, multi_select=field in MULTI_SELECT_TAG_FIELDS
            )
            items = order_open(
                BreakdownItem(
                    key=slug,
                    label=label_map.get((field, slug), slug) if slug else "Not Tagged",
                    count=count,
                )
                for slug, count in rows
            )
            fields[field] = Breakdown(total=deals, items=items)
        return TagMix(fields=fields)

    async def get_duplicates(self, filters: UnderwritingAnalyticsFilters) -> Duplicates:
        properties, rows, copies = await self.repository.duplicates(filters)
        return Duplicates(
            properties_underwritten_repeatedly=properties,
            underwritings_on_those_properties=rows,
            duplicate_button_copies=copies,
        )

    async def get_automation_split(
        self, filters: UnderwritingAnalyticsFilters
    ) -> Breakdown:
        counts = {
            None if flag is None else ("automated" if flag else "manual"): count
            for flag, count in await self.repository.count_by_automated(filters)
        }
        return breakdown(
            order_fixed(
                counts,
                known=(("automated", "Automated"), ("manual", "Manual")),
                unknown_label="Unknown",
            )
        )

    async def get_job_health(
        self, *, created_from: date | None = None, created_to: date | None = None
    ) -> list[JobTypeHealth]:
        by_type: dict[str, dict[str | None, int]] = defaultdict(dict)
        last_finished: dict[str, object] = {}
        for job_type, status, count, finished in await self.repository.job_health(
            created_from=created_from, created_to=created_to
        ):
            by_type[job_type][status] = count
            if finished is not None and (
                last_finished.get(job_type) is None
                or finished > last_finished[job_type]
            ):
                last_finished[job_type] = finished

        rows = [
            JobTypeHealth(
                key=job_type,
                label=humanize(job_type),
                total=sum(counts.values()),
                by_status=order_fixed(counts, known=JOB_STATUSES),
                last_finished_at=last_finished.get(job_type),
            )
            for job_type, counts in by_type.items()
        ]
        # Ordering Rule 2 (open set of job types) by total jobs.
        return sorted(rows, key=lambda row: (-row.total, row.key))

    async def get_completeness(
        self, filters: UnderwritingAnalyticsFilters
    ) -> UnderwritingCompleteness:
        return UnderwritingCompleteness(**await self.repository.completeness(filters))


def _pivot(rows) -> tuple[dict, dict[str | None, int]]:
    """``(group, status, count)`` rows -> per-group status counts, plus overall."""
    by_group: dict = defaultdict(dict)
    overall: dict[str | None, int] = defaultdict(int)
    for group, status, count in rows:
        by_group[group][status] = count
        overall[status] += count
    return by_group, overall


def _sum_statuses(
    counts: Mapping[str | None, int], statuses: Collection[DealStatus]
) -> int:
    return sum(counts.get(status.value, 0) for status in statuses)


def _market_key_label(
    market_id: int | None, market_labels: Mapping[int, str]
) -> tuple[str | None, str]:
    if market_id is None:
        return None, "Unassigned"
    # A soft-deleted market drops out of the label lookup but its deals remain.
    return str(market_id), market_labels.get(market_id) or f"Market {market_id}"


def _median(values: Mapping[str, object], name: str) -> MedianValue:
    median = values[f"{name}_median"]
    return MedianValue(
        value=None if median is None else float(median),
        sample_size=values[f"{name}_count"],
    )
