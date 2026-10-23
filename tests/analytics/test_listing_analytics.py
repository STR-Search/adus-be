import uuid
from datetime import date, datetime, timezone

import pytest

from app.core.analytics.schemas import Granularity
from app.zillow.repositories.listing_analytics_repository import (
    ListingAnalyticsRepository,
)
from app.zillow.services.listing_analytics_service import ListingAnalyticsService
from tests.analytics.conftest import CapturingDb, sql

PRESET_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
PRESET_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")


class FakeRepository:
    def __init__(self, **responses):
        self.responses = responses
        self.calls = []

    def __getattr__(self, name):
        async def method(*args, **kwargs):
            self.calls.append((name, kwargs))
            return list(self.responses[name])

        return method


def _items(items):
    return [(item.key, item.count) for item in items]


@pytest.mark.asyncio
async def test_home_status_sorts_by_count_with_key_tiebreak_and_labels():
    repo = FakeRepository(
        count_by_home_status=[("SOLD", 3), ("FOR_SALE", 40), ("PENDING", 3), (None, 1)]
    )

    result = await ListingAnalyticsService(repo).get_home_status_breakdown()

    assert result.total == 47
    assert _items(result.items) == [
        ("FOR_SALE", 40),
        ("PENDING", 3),
        ("SOLD", 3),
        (None, 1),
    ]
    assert [item.label for item in result.items] == [
        "For Sale",
        "Pending",
        "Sold",
        "Unknown",
    ]


@pytest.mark.asyncio
async def test_home_status_unknown_is_last_even_when_largest():
    repo = FakeRepository(count_by_home_status=[("FOR_SALE", 5), ("", 3), (None, 4)])

    result = await ListingAnalyticsService(repo).get_home_status_breakdown()

    assert result.total == 12
    assert _items(result.items) == [("FOR_SALE", 5), (None, 7)]


@pytest.mark.asyncio
async def test_repository_filters_by_preset_without_joining():
    db = CapturingDb()
    repo = ListingAnalyticsRepository(db)

    await repo.count_by_home_status()
    await repo.count_by_home_status(preset_id=PRESET_A)

    unfiltered, by_preset = (sql(q) for q in db.queries)
    assert "WHERE" not in unfiltered
    assert "JOIN" not in by_preset
    assert f"zillow.scheduled_listings.preset_id = '{PRESET_A}'" in by_preset
    assert "GROUP BY zillow.scheduled_listings.home_status" in by_preset


@pytest.mark.asyncio
async def test_repository_filters_by_market_through_the_preset():
    db = CapturingDb()

    await ListingAnalyticsRepository(db).count_by_home_status(market_id=12)

    query = sql(db.queries[0])
    assert "JOIN" not in query
    assert (
        "zillow.scheduled_listings.preset_id IN (SELECT zillow.scheduled_presets.id"
        in query
    )
    assert "zillow.scheduled_presets.market_id = 12" in query


@pytest.mark.asyncio
async def test_repository_intake_market_filter_composes_with_preset_grouping():
    db = CapturingDb()

    await ListingAnalyticsRepository(db).intake(
        granularity=Granularity.WEEK, group_by_preset=True, market_id=12
    )

    query = sql(db.queries[0])
    assert query.count("JOIN zillow.scheduled_presets") == 1
    assert "zillow.scheduled_presets.market_id = 12" in query
    assert "GROUP BY zillow.scheduled_listings.preset_id" in query


@pytest.mark.asyncio
async def test_intake_passes_market_through():
    repo = FakeRepository(intake=[])

    await ListingAnalyticsService(repo).get_intake(market_id=12)

    assert repo.calls[0][1]["market_id"] == 12


@pytest.mark.asyncio
async def test_repository_created_range_is_inclusive_utc_days():
    db = CapturingDb()

    await ListingAnalyticsRepository(db).count_by_home_status(
        created_from=date(2026, 10, 1), created_to=date(2026, 10, 3)
    )

    query = sql(db.queries[0])
    assert "created_at >= '2026-10-01 00:00:00+00:00'" in query
    assert "created_at < '2026-10-04 00:00:00+00:00'" in query


@pytest.mark.asyncio
async def test_intake_single_series_fills_requested_range():
    repo = FakeRepository(intake=[(None, None, date(2026, 10, 5), 7)])

    (series,) = await ListingAnalyticsService(repo).get_intake(
        created_from=date(2026, 9, 28), created_to=date(2026, 10, 12)
    )

    assert (series.key, series.label) == (None, "All listings")
    assert [(p.period_start, p.count) for p in series.points] == [
        (date(2026, 9, 28), 0),
        (date(2026, 10, 5), 7),
        (date(2026, 10, 12), 0),
    ]


@pytest.mark.asyncio
async def test_intake_per_preset_series_share_periods_and_rank_by_total():
    repo = FakeRepository(
        intake=[
            (PRESET_A, "Alpha", date(2026, 9, 28), 1),
            (PRESET_B, "Beta", date(2026, 10, 12), 5),
        ]
    )

    series = await ListingAnalyticsService(repo).get_intake(group_by_preset=True)

    assert [s.label for s in series] == ["Beta", "Alpha"]
    for s in series:
        assert [p.period_start for p in s.points] == [
            date(2026, 9, 28),
            date(2026, 10, 5),
            date(2026, 10, 12),
        ]


@pytest.mark.asyncio
async def test_intake_without_data_returns_empty_all_listings_series():
    repo = FakeRepository(intake=[])

    (series,) = await ListingAnalyticsService(repo).get_intake(
        granularity=Granularity.DAY
    )

    assert series.points == []


@pytest.mark.asyncio
async def test_preset_runs_overdue_first_then_oldest_run():
    old = datetime(2026, 10, 1, tzinfo=timezone.utc)
    new = datetime(2026, 10, 20, tzinfo=timezone.utc)
    repo = FakeRepository(
        preset_runs=[
            ("1", "Fresh", new, None, None, False),
            ("2", "Stale", old, None, None, False),
            ("3", "Overdue", new, old, None, True),
            ("4", "Never run", None, None, None, False),
        ]
    )

    runs = await ListingAnalyticsService(repo).get_preset_runs()

    assert [r.label for r in runs] == ["Overdue", "Never run", "Stale", "Fresh"]


@pytest.mark.asyncio
async def test_repository_stale_listings_use_keep_updated_and_last_seen():
    db = CapturingDb()

    await ListingAnalyticsRepository(db).count_stale_by_preset(stale_after_days=14)

    query = sql(db.queries[0])
    assert "keep_updated IS true" in query
    assert "last_seen < now() -" in query


@pytest.mark.asyncio
async def test_stale_listings_ranked_by_count():
    repo = FakeRepository(
        count_stale_by_preset=[(PRESET_A, "Alpha", 2), (PRESET_B, "Beta", 9)]
    )

    result = await ListingAnalyticsService(repo).get_stale_listings()

    assert result.total == 11
    assert [p.label for p in result.presets] == ["Beta", "Alpha"]
