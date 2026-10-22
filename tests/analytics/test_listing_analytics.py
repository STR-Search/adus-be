from datetime import date

import pytest
from sqlalchemy.dialects import postgresql

from app.zillow.repositories.listing_analytics_repository import (
    ListingAnalyticsRepository,
)
from app.zillow.services.listing_analytics_service import ListingAnalyticsService


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class CapturingDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return FakeResult(self.rows)


class FakeRepository:
    def __init__(self, rows):
        self.rows = rows

    async def count_by_home_status(self, **kwargs):
        return list(self.rows)


def _sql(query) -> str:
    return str(
        query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


@pytest.mark.asyncio
async def test_breakdown_sorts_by_count_desc():
    repo = FakeRepository([("PENDING", 3), ("FOR_SALE", 40), (None, 1)])

    result = await ListingAnalyticsService(repo).get_home_status_breakdown()

    assert result.total == 44
    assert [(s.home_status, s.count) for s in result.statuses] == [
        ("FOR_SALE", 40),
        ("PENDING", 3),
        (None, 1),
    ]


@pytest.mark.asyncio
async def test_breakdown_merges_blank_status_into_unknown():
    repo = FakeRepository([("FOR_SALE", 5), ("", 3), (None, 1)])

    result = await ListingAnalyticsService(repo).get_home_status_breakdown()

    assert result.total == 9
    assert [(s.home_status, s.count) for s in result.statuses] == [
        ("FOR_SALE", 5),
        (None, 4),
    ]


@pytest.mark.asyncio
async def test_repository_joins_preset_only_when_filtering_by_market():
    db = CapturingDb()
    repo = ListingAnalyticsRepository(db)

    await repo.count_by_home_status()
    await repo.count_by_home_status(market_id=12)

    unfiltered, by_market = (_sql(q) for q in db.queries)
    assert "JOIN" not in unfiltered
    assert "JOIN zillow.scheduled_presets" in by_market
    assert "zillow.scheduled_presets.market_id = 12" in by_market
    assert "GROUP BY zillow.scheduled_listings.home_status" in by_market


@pytest.mark.asyncio
async def test_repository_created_range_is_inclusive_utc_days():
    db = CapturingDb()

    await ListingAnalyticsRepository(db).count_by_home_status(
        created_from=date(2026, 10, 1), created_to=date(2026, 10, 3)
    )

    sql = _sql(db.queries[0])
    assert "created_at >= '2026-10-01 00:00:00+00:00'" in sql
    assert "created_at < '2026-10-04 00:00:00+00:00'" in sql
