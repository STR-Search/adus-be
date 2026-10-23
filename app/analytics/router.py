import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.controllers.analytics_controller import AnalyticsController
from app.analytics.repositories.pipeline_analytics_repository import (
    PipelineAnalyticsRepository,
)
from app.analytics.schemas.composed import Automation, DataCompleteness
from app.analytics.schemas.pipeline import Coverage, OffMarket, PriceDrops
from app.analytics.services.pipeline_analytics_service import PipelineAnalyticsService
from app.core.analytics.schemas import Breakdown, Granularity, Series
from app.core.database import get_db
from app.core.reference_data.repository import ReferenceDataRepository
from app.core.reference_data.service import ReferenceDataService
from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.repositories.underwriting_analytics_repository import (
    UnderwritingAnalyticsRepository,
)
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
from app.markets.repositories.construction_repository import (
    ConstructionAmenitiesRepository,
)
from app.markets.repositories.market_repository import MarketRepository
from app.markets.repositories.realtor_repository import RealtorRepository
from app.markets.services.market_service import MarketService
from app.zillow.repositories.listing_analytics_repository import (
    ListingAnalyticsRepository,
)
from app.zillow.schemas.listing_analytics import IntakeGroupBy
from app.zillow.services.listing_analytics_service import ListingAnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

_ADDED = "Inclusive, on deal_added (UTC)"
_CREATED = "Inclusive, on created_at (UTC)"
_LISTING_MARKET = "The market of the preset that found the listing"
_SOURCE = (
    "Repeatable. Defaults to adus + blank; add legacy_sheet to include sheet rows."
)


def get_analytics_controller(db: AsyncSession = Depends(get_db)) -> AnalyticsController:
    return AnalyticsController(
        underwriting_analytics=UnderwritingAnalyticsService(
            UnderwritingAnalyticsRepository(db),
            reference_data_service=ReferenceDataService(ReferenceDataRepository(db)),
        ),
        listing_analytics=ListingAnalyticsService(ListingAnalyticsRepository(db)),
        pipeline_analytics=PipelineAnalyticsService(PipelineAnalyticsRepository(db)),
        market_service=MarketService(
            MarketRepository(db),
            ConstructionAmenitiesRepository(db),
            RealtorRepository(db),
        ),
    )


def _sources(source: list[UnderwritingSource] | None) -> tuple[UnderwritingSource, ...]:
    return tuple(dict.fromkeys(source)) if source else DEFAULT_ANALYTICS_SOURCES


def underwriting_filters(
    market_id: int | None = Query(None),
    analyst_id: int | None = Query(None),
    source: list[UnderwritingSource] | None = Query(None, description=_SOURCE),
    added_from: date | None = Query(None, description=_ADDED),
    added_to: date | None = Query(None, description=_ADDED),
) -> UnderwritingAnalyticsFilters:
    return UnderwritingAnalyticsFilters(
        market_id=market_id,
        analyst_id=analyst_id,
        source=_sources(source),
        added_from=added_from,
        added_to=added_to,
    )


def underwriting_filters_by_status(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters),
    deal_status: list[DealStatus] | None = Query(None, description="Repeatable"),
) -> UnderwritingAnalyticsFilters:
    if not deal_status:
        return filters
    return filters.model_copy(update={"deal_status": tuple(dict.fromkeys(deal_status))})


def underwriting_filters_all_markets(
    analyst_id: int | None = Query(None),
    source: list[UnderwritingSource] | None = Query(None, description=_SOURCE),
    added_from: date | None = Query(None, description=_ADDED),
    added_to: date | None = Query(None, description=_ADDED),
) -> UnderwritingAnalyticsFilters:
    """Common filters minus ``market_id``, for the per-market endpoints."""
    return underwriting_filters(
        market_id=None,
        analyst_id=analyst_id,
        source=source,
        added_from=added_from,
        added_to=added_to,
    )


# -- listings (zillow) -------------------------------------------------------


@router.get("/listings/home-status-breakdown", response_model=Breakdown)
async def get_home_status_breakdown(
    market_id: int | None = Query(None, description=_LISTING_MARKET),
    preset_id: uuid.UUID | None = Query(None),
    created_from: date | None = Query(None, description=_CREATED),
    created_to: date | None = Query(None, description=_CREATED),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_home_status_breakdown(
        market_id=market_id,
        preset_id=preset_id,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/listings/intake", response_model=list[Series])
async def get_listing_intake(
    market_id: int | None = Query(None, description=_LISTING_MARKET),
    preset_id: uuid.UUID | None = Query(None),
    created_from: date | None = Query(None, description=_CREATED),
    created_to: date | None = Query(None, description=_CREATED),
    granularity: Granularity = Query(Granularity.WEEK),
    group_by: IntakeGroupBy = Query(IntakeGroupBy.NONE),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_intake(
        granularity=granularity,
        group_by=group_by,
        market_id=market_id,
        preset_id=preset_id,
        created_from=created_from,
        created_to=created_to,
    )


# -- underwritings (iron_bank) -----------------------------------------------


@router.get("/underwritings/deal-status-breakdown", response_model=Breakdown)
async def get_deal_status_breakdown(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters_by_status),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_deal_status_breakdown(filters)


@router.get(
    "/underwritings/template-progress", response_model=list[TemplateProgressPoint]
)
async def get_template_progress(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters),
    granularity: Granularity = Query(Granularity.WEEK),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_template_progress(filters, granularity)


@router.get("/underwritings/market-breakdown", response_model=MarketBreakdown)
async def get_market_breakdown(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters_all_markets),
    sort: MarketSort = Query(MarketSort.UNDERWRITTEN),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_market_breakdown(filters, sort)


@router.get("/underwritings/price-bands", response_model=list[PriceBandRow])
async def get_price_bands(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters_by_status),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_price_bands(filters)


@router.get("/underwritings/quality-comparison", response_model=QualityComparison)
async def get_quality_comparison(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_quality_comparison(filters)


@router.get("/underwritings/tag-mix", response_model=TagMix)
async def get_tag_mix(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters_by_status),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    """Defaults to presented deals (present_to_clients + client_under_contract)."""
    return await controller.get_tag_mix(filters)


@router.get("/underwritings/duplicates", response_model=Duplicates)
async def get_duplicates(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_duplicates(filters)


# -- composed: iron_bank + zillow --------------------------------------------


@router.get("/automation", response_model=Automation)
async def get_automation(
    market_id: int | None = Query(None, description="Underwritings only"),
    source: list[UnderwritingSource] | None = Query(None, description=_SOURCE),
    created_from: date | None = Query(
        None, description="Inclusive; underwritings' deal_added and jobs' created_at"
    ),
    created_to: date | None = Query(
        None, description="Inclusive; underwritings' deal_added and jobs' created_at"
    ),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_automation(
        market_id=market_id,
        source=_sources(source),
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/data-completeness", response_model=DataCompleteness)
async def get_data_completeness(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters),
    stale_after_days: int = Query(14, ge=1),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_data_completeness(
        filters, stale_after_days=stale_after_days
    )


# -- joined: zillow listings x iron_bank underwritings -----------------------


@router.get("/pipeline/coverage", response_model=Coverage)
async def get_coverage(
    preset_id: uuid.UUID | None = Query(None),
    source: list[UnderwritingSource] | None = Query(None, description=_SOURCE),
    created_from: date | None = Query(
        None, description="Inclusive, on the listing's created_at (UTC)"
    ),
    created_to: date | None = Query(
        None, description="Inclusive, on the listing's created_at (UTC)"
    ),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_coverage(
        source=_sources(source),
        preset_id=preset_id,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/pipeline/off-market", response_model=OffMarket)
async def get_off_market(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters_by_status),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_off_market(filters)


@router.get("/pipeline/price-drops", response_model=PriceDrops)
async def get_price_drops(
    filters: UnderwritingAnalyticsFilters = Depends(underwriting_filters_by_status),
    changed_from: date | None = Query(
        None, description="Inclusive, on price_change_date"
    ),
    changed_to: date | None = Query(
        None, description="Inclusive, on price_change_date"
    ),
    controller: AnalyticsController = Depends(get_analytics_controller),
):
    return await controller.get_price_drops(
        filters, changed_from=changed_from, changed_to=changed_to
    )
