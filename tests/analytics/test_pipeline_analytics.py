import uuid

import pytest

from app.analytics.repositories.pipeline_analytics_repository import (
    PipelineAnalyticsRepository,
)
from app.analytics.services.pipeline_analytics_service import (
    LIVE_STATUSES,
    PipelineAnalyticsService,
)
from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.schemas.underwriting_analytics import UnderwritingAnalyticsFilters
from app.iron_bank.services.deal_status_service import (
    STATUS_OPTIONS,
    TERMINAL_DEAL_STATUSES,
)
from tests.analytics.conftest import CapturingDb, sql

PRESET = uuid.UUID("00000000-0000-0000-0000-00000000000a")
ALL_STATUSES = [status.value for status, _, _ in STATUS_OPTIONS]


class FakeRepository:
    def __init__(self, **responses):
        self.responses = responses
        self.calls = []

    def __getattr__(self, name):
        async def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            response = self.responses[name]
            return response(kwargs) if callable(response) else response

        return method


# Repository ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_off_market_joins_listing_and_uses_pending_rule():
    db = CapturingDb()

    await PipelineAnalyticsRepository(db).count_off_market(
        UnderwritingAnalyticsFilters(source=tuple(UnderwritingSource))
    )

    query = sql(db.queries[0])
    assert "JOIN zillow.scheduled_listings" in query
    assert (
        "coalesce(zillow.scheduled_listings.home_status, '') NOT IN ('FOR_SALE', 'OTHER')"
        in query
    )
    assert "source IN ('adus', 'legacy_sheet', 'blank')" in query


@pytest.mark.asyncio
async def test_coverage_left_joins_earliest_underwriting():
    db = CapturingDb([(10, 4, 1.5)])

    rows = await PipelineAnalyticsRepository(db).coverage(
        source=(UnderwritingSource.ADUS,), group_by_preset=False, preset_id=PRESET
    )

    assert rows == [(None, None, 10, 4, 1.5)]
    query = sql(db.queries[0])
    assert "LEFT OUTER JOIN (SELECT iron_bank.underwritings.zpid" in query
    assert "min(iron_bank.underwritings.deal_added)" in query
    assert "source IN ('adus')" in query
    assert f"zillow.scheduled_listings.preset_id = '{PRESET}'" in query
    assert "percentile_cont(0.5) WITHIN GROUP" in query


@pytest.mark.asyncio
async def test_coverage_filters_by_market_through_the_preset():
    db = CapturingDb([])

    await PipelineAnalyticsRepository(db).coverage(
        source=(UnderwritingSource.ADUS,), group_by_preset=True, market_id=12
    )

    query = sql(db.queries[0])
    assert (
        "zillow.scheduled_listings.preset_id IN (SELECT zillow.scheduled_presets.id"
        in query
    )
    assert "zillow.scheduled_presets.market_id = 12" in query
    # The per-preset rows' join is still the only one to presets.
    assert query.count("JOIN zillow.scheduled_presets") == 1


@pytest.mark.asyncio
async def test_coverage_passes_market_to_both_queries():
    def coverage(kwargs):
        return [] if kwargs["group_by_preset"] else [(None, None, 0, 0, None)]

    repo = FakeRepository(coverage=coverage)

    await PipelineAnalyticsService(repo).get_coverage(market_id=12)

    assert [call[2]["market_id"] for call in repo.calls] == [12, 12]


@pytest.mark.asyncio
async def test_price_drops_only_negative_changes_for_given_statuses():
    db = CapturingDb([("maybe", 2)], [(0.05, 2)])

    rows, median, sample = await PipelineAnalyticsRepository(db).price_drops(
        UnderwritingAnalyticsFilters(), statuses=(DealStatus.MAYBE,)
    )

    assert (rows, median, sample) == ([("maybe", 2)], 0.05, 2)
    per_status, median_query = (sql(q) for q in db.queries)
    for query in (per_status, median_query):
        assert "JOIN zillow.scheduled_listing_details" in query
        assert "price_change < 0" in query
        assert "deal_status IN ('maybe')" in query


# Service ---------------------------------------------------------------------


def test_live_statuses_exclude_terminal():
    assert LIVE_STATUSES
    assert not {s.value for s in LIVE_STATUSES} & TERMINAL_DEAL_STATUSES


@pytest.mark.asyncio
async def test_coverage_overall_and_presets():
    def coverage(kwargs):
        if kwargs["group_by_preset"]:
            return [(PRESET, "Alpha", 10, 4, 2.0), (uuid.uuid4(), "Beta", 20, 0, None)]
        return [(None, None, 30, 4, 2.0)]

    result = await PipelineAnalyticsService(
        FakeRepository(coverage=coverage)
    ).get_coverage()

    assert (result.overall.label, result.overall.listings, result.overall.coverage) == (
        "All presets",
        30,
        4 / 30,
    )
    assert [p.label for p in result.presets] == ["Beta", "Alpha"]
    assert result.presets[0].coverage == 0
    assert result.presets[0].median_days_to_underwrite is None


@pytest.mark.asyncio
async def test_off_market_splits_by_home_status_and_counts_missed_and_wasted():
    repo = FakeRepository(
        count_off_market=[
            ("present_to_clients", "PENDING", 3),
            ("present_to_clients", "SOLD", 1),
            ("present_to_clients", "", 1),
            ("client_under_contract", "SOLD", 5),
            ("analyst_started", "PENDING", 2),
            ("maybe", None, 1),
        ],
        count_with_status=10,
    )

    result = await PipelineAnalyticsService(repo).get_off_market(
        UnderwritingAnalyticsFilters()
    )

    assert [r.key for r in result.by_status] == ALL_STATUSES
    presented = next(r for r in result.by_status if r.key == "present_to_clients")
    assert presented.off_market == 5
    assert [(i.key, i.count) for i in presented.by_home_status] == [
        ("PENDING", 3),
        ("SOLD", 1),
        (None, 1),
    ]
    # Under contract and off the market is a win, not a miss.
    assert result.missed_deals == 5
    assert result.presented_total == 10
    assert result.missed_rate == 0.5
    assert result.wasted_analysis == 3


@pytest.mark.asyncio
async def test_price_drops_zero_fill_live_statuses_only():
    repo = FakeRepository(price_drops=([("maybe", 2)], 0.04, 2))

    result = await PipelineAnalyticsService(repo).get_price_drops(
        UnderwritingAnalyticsFilters()
    )

    keys = [item.key for item in result.deals.items]
    assert keys == [s.value for s in LIVE_STATUSES]
    assert "client_under_contract" not in keys
    assert result.deals.total == 2
    assert result.median_drop_pct.value == 0.04


@pytest.mark.asyncio
async def test_price_drops_status_filter_intersects_live_statuses():
    repo = FakeRepository(price_drops=([], None, 0))
    filters = UnderwritingAnalyticsFilters(
        deal_status=(DealStatus.MAYBE, DealStatus.DELETE_DEAL)
    )

    result = await PipelineAnalyticsService(repo).get_price_drops(filters)

    assert repo.calls[0][2]["statuses"] == (DealStatus.MAYBE,)
    assert [item.key for item in result.deals.items] == ["maybe"]
    assert result.median_drop_pct.value is None
