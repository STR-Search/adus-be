import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import TypeVar

from fastapi import HTTPException

from app.analytics.schemas.composed import Automation, DataCompleteness
from app.analytics.schemas.pipeline import Coverage, OffMarket, PriceDrops
from app.analytics.services.pipeline_analytics_service import PipelineAnalyticsService
from app.core.analytics.schemas import Breakdown, Granularity, Series
from app.core.logger import logger
from app.iron_bank.enums import UnderwritingSource
from app.iron_bank.schemas.underwriting_analytics import (
    DEFAULT_ANALYTICS_SOURCES,
    Duplicates,
    MarketBreakdown,
    PriceBandRow,
    QualityComparison,
    TagMix,
    TemplateProgressPoint,
    UnderwritingAnalyticsFilters,
)
from app.iron_bank.services.analytics.underwriting_analytics_service import (
    MarketSort,
    UnderwritingAnalyticsService,
)
from app.zillow.schemas.listing_analytics import IntakeGroupBy
from app.zillow.services.listing_analytics_service import ListingAnalyticsService

T = TypeVar("T")


class AnalyticsController:
    def __init__(
        self,
        underwriting_analytics: UnderwritingAnalyticsService,
        listing_analytics: ListingAnalyticsService,
        pipeline_analytics: PipelineAnalyticsService | None = None,
        market_service=None,
    ):
        self.underwriting_analytics = underwriting_analytics
        self.listing_analytics = listing_analytics
        self.pipeline_analytics = pipeline_analytics
        # Anything with ``get_all_summary()`` (the markets domain's MarketService);
        # only used for market names, which iron_bank must not look up itself.
        self.market_service = market_service

    # -- listings (zillow) ---------------------------------------------------

    async def get_home_status_breakdown(
        self,
        *,
        market_id: int | None = None,
        preset_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> Breakdown:
        self._validate_range(created_from, created_to)
        return await self._run(
            "home_status_breakdown",
            lambda: self.listing_analytics.get_home_status_breakdown(
                market_id=market_id,
                preset_id=preset_id,
                created_from=created_from,
                created_to=created_to,
            ),
        )

    async def get_intake(
        self,
        *,
        granularity: Granularity = Granularity.WEEK,
        group_by: IntakeGroupBy = IntakeGroupBy.NONE,
        market_id: int | None = None,
        preset_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> list[Series]:
        self._validate_range(created_from, created_to)

        async def run():
            market_labels = (
                await self._market_labels() if group_by is IntakeGroupBy.MARKET else {}
            )
            return await self.listing_analytics.get_intake(
                granularity=granularity,
                group_by=group_by,
                market_labels=market_labels,
                market_id=market_id,
                preset_id=preset_id,
                created_from=created_from,
                created_to=created_to,
            )

        return await self._run("intake", run)

    # -- underwritings (iron_bank) -------------------------------------------

    async def get_deal_status_breakdown(
        self, filters: UnderwritingAnalyticsFilters
    ) -> Breakdown:
        self._validate_filters(filters)
        return await self._run(
            "deal_status_breakdown",
            lambda: self.underwriting_analytics.get_deal_status_breakdown(filters),
        )

    async def get_template_progress(
        self, filters: UnderwritingAnalyticsFilters, granularity: Granularity
    ) -> list[TemplateProgressPoint]:
        self._validate_filters(filters)
        return await self._run(
            "template_progress",
            lambda: self.underwriting_analytics.get_template_progress(
                filters, granularity
            ),
        )

    async def get_market_breakdown(
        self, filters: UnderwritingAnalyticsFilters, sort: MarketSort
    ) -> MarketBreakdown:
        self._validate_filters(filters)

        async def run():
            return await self.underwriting_analytics.get_market_breakdown(
                filters, market_labels=await self._market_labels(), sort=sort
            )

        return await self._run("market_breakdown", run)

    async def get_price_bands(
        self, filters: UnderwritingAnalyticsFilters
    ) -> list[PriceBandRow]:
        self._validate_filters(filters)
        return await self._run(
            "price_bands", lambda: self.underwriting_analytics.get_price_bands(filters)
        )

    async def get_quality_comparison(
        self, filters: UnderwritingAnalyticsFilters
    ) -> QualityComparison:
        self._validate_filters(filters)
        return await self._run(
            "quality_comparison",
            lambda: self.underwriting_analytics.get_quality_comparison(filters),
        )

    async def get_tag_mix(self, filters: UnderwritingAnalyticsFilters) -> TagMix:
        self._validate_filters(filters)
        return await self._run(
            "tag_mix", lambda: self.underwriting_analytics.get_tag_mix(filters)
        )

    async def get_duplicates(self, filters: UnderwritingAnalyticsFilters) -> Duplicates:
        self._validate_filters(filters)
        return await self._run(
            "duplicates", lambda: self.underwriting_analytics.get_duplicates(filters)
        )

    # -- composed: iron_bank + zillow ----------------------------------------

    async def get_automation(
        self,
        *,
        market_id: int | None = None,
        source: tuple[UnderwritingSource, ...] = DEFAULT_ANALYTICS_SOURCES,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> Automation:
        self._validate_range(created_from, created_to)
        # The created range applies to underwritings' deal_added and jobs'
        # created_at; market and source narrow underwritings only.
        filters = UnderwritingAnalyticsFilters(
            market_id=market_id,
            source=source,
            added_from=created_from,
            added_to=created_to,
        )

        async def run():
            return Automation(
                underwritings=await self.underwriting_analytics.get_automation_split(
                    filters
                ),
                jobs=await self.underwriting_analytics.get_job_health(
                    created_from=created_from, created_to=created_to
                ),
                presets=await self.listing_analytics.get_preset_runs(),
            )

        return await self._run("automation", run)

    async def get_data_completeness(
        self, filters: UnderwritingAnalyticsFilters, *, stale_after_days: int = 14
    ) -> DataCompleteness:
        self._validate_filters(filters)

        async def run():
            return DataCompleteness(
                underwritings=await self.underwriting_analytics.get_completeness(
                    filters
                ),
                stale_listings=await self.listing_analytics.get_stale_listings(
                    stale_after_days=stale_after_days
                ),
            )

        return await self._run("data_completeness", run)

    # -- joined: zillow listings x iron_bank underwritings -------------------

    async def get_coverage(
        self,
        *,
        source: tuple[UnderwritingSource, ...] = DEFAULT_ANALYTICS_SOURCES,
        preset_id: uuid.UUID | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
    ) -> Coverage:
        self._validate_range(created_from, created_to)
        return await self._run(
            "coverage",
            lambda: self.pipeline_analytics.get_coverage(
                source=source,
                preset_id=preset_id,
                created_from=created_from,
                created_to=created_to,
            ),
        )

    async def get_off_market(self, filters: UnderwritingAnalyticsFilters) -> OffMarket:
        self._validate_filters(filters)
        return await self._run(
            "off_market", lambda: self.pipeline_analytics.get_off_market(filters)
        )

    async def get_price_drops(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        changed_from: date | None = None,
        changed_to: date | None = None,
    ) -> PriceDrops:
        self._validate_filters(filters)
        self._validate_range(changed_from, changed_to)
        return await self._run(
            "price_drops",
            lambda: self.pipeline_analytics.get_price_drops(
                filters, changed_from=changed_from, changed_to=changed_to
            ),
        )

    # -- helpers -------------------------------------------------------------

    async def _market_labels(self) -> dict[int, str]:
        if self.market_service is None:
            return {}
        markets = await self.market_service.get_all_summary()
        return {
            market.id: market.market_name for market in markets if market.market_name
        }

    @staticmethod
    async def _run(metric: str, call: Callable[[], Awaitable[T]]) -> T:
        try:
            return await call()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"analytics.{metric}.error", error=str(e))
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch {metric.replace('_', ' ')}",
            ) from e

    @classmethod
    def _validate_filters(cls, filters: UnderwritingAnalyticsFilters) -> None:
        cls._validate_range(filters.added_from, filters.added_to)

    @staticmethod
    def _validate_range(start: date | None, end: date | None) -> None:
        if start is not None and end is not None and start > end:
            raise HTTPException(
                status_code=400, detail="Range start must be on or before range end"
            )
