from datetime import datetime, timezone

import pytest

from app.zillow.repositories import scheduled_listings_repository
from app.zillow.repositories.scheduled_listings_repository import (
    ScheduledListingsRepository,
)


class FakeScalars:
    def all(self):
        return []


class FakeResult:
    def scalars(self):
        return FakeScalars()


class FakeDb:
    async def execute(self, query):
        return FakeResult()


class FakeDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 6, 24, 15, 30, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_get_active_since_logs_utc_window(monkeypatch):
    logs = []

    monkeypatch.setattr(scheduled_listings_repository, "datetime", FakeDateTime)
    monkeypatch.setattr(
        scheduled_listings_repository.logger,
        "debug",
        lambda event, **kwargs: logs.append((event, kwargs)),
    )

    await ScheduledListingsRepository(FakeDb()).get_active_since(
        since_hours=24,
        limit=500,
    )

    assert logs[-1] == (
        "zillow.scheduled_listings.get_active_since",
        {
            "since_hours": 24,
            "limit": 500,
            "server_now_utc": "2026-06-24T15:30:00+00:00",
            "cutoff_utc": "2026-06-23T15:30:00+00:00",
            "count": 0,
        },
    )
