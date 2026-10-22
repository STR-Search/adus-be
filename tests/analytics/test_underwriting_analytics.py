from datetime import date

import pytest
from sqlalchemy.dialects import postgresql

from app.iron_bank.repositories.underwriting_analytics_repository import (
    UnderwritingAnalyticsRepository,
)
from app.iron_bank.services.analytics.underwriting_analytics_service import (
    UnderwritingAnalyticsService,
)


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
        self.calls = []

    async def count_by_deal_status(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.rows)


def _sql(query) -> str:
    return str(
        query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


@pytest.mark.asyncio
async def test_breakdown_orders_by_workflow_and_labels_statuses():
    repo = FakeRepository(
        [
            ("present_to_clients", 2),
            (None, 1),
            ("legacy_value", 4),
            ("template_generated", 10),
        ]
    )

    result = await UnderwritingAnalyticsService(repo).get_deal_status_breakdown(market_id=7)

    assert result.total == 17
    assert [(s.key, s.label, s.count) for s in result.statuses] == [
        ("template_generated", "Template Generated", 10),
        ("present_to_clients", "Present To Clients", 2),
        ("legacy_value", "legacy_value", 4),
        (None, "No Status", 1),
    ]
    assert repo.calls == [
        {"market_id": 7, "analyst_id": None, "added_from": None, "added_to": None}
    ]


@pytest.mark.asyncio
async def test_breakdown_empty():
    result = await UnderwritingAnalyticsService(FakeRepository([])).get_deal_status_breakdown()

    assert result.total == 0
    assert result.statuses == []


@pytest.mark.asyncio
async def test_repository_groups_by_status_with_filters():
    db = CapturingDb(rows=[("maybe", 3)])

    rows = await UnderwritingAnalyticsRepository(db).count_by_deal_status(
        market_id=7,
        analyst_id=3,
        added_from=date(2026, 10, 1),
        added_to=date(2026, 10, 1),
    )

    assert rows == [("maybe", 3)]
    sql = _sql(db.queries[0])
    assert "GROUP BY iron_bank.underwritings.deal_status" in sql
    assert "iron_bank.underwritings.market_id = 7" in sql
    assert "iron_bank.underwritings.analyst_id = 3" in sql
    # min == max still covers that whole UTC day.
    assert "deal_added >= '2026-10-01 00:00:00+00:00'" in sql
    assert "deal_added < '2026-10-02 00:00:00+00:00'" in sql


@pytest.mark.asyncio
async def test_repository_without_filters_has_no_where():
    db = CapturingDb()

    await UnderwritingAnalyticsRepository(db).count_by_deal_status()

    assert "WHERE" not in _sql(db.queries[0])
