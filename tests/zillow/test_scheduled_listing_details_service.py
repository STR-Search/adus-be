import pytest

from app.zillow.services.scheduled_listing_details_service import (
    ScheduledListingDetailsService,
)


class FakeDetailsRepository:
    def __init__(self):
        self.called_with = None

    async def get_price_changed_since(self, *, since_hours, limit):
        self.called_with = {"since_hours": since_hours, "limit": limit}
        return ["1", "2"]


@pytest.mark.asyncio
async def test_get_price_changed_zpids_since_delegates_window_and_limit():
    repository = FakeDetailsRepository()
    service = ScheduledListingDetailsService(repository)

    result = await service.get_price_changed_zpids_since(
        since_hours=24,
        limit=500,
    )

    assert result == ["1", "2"]
    assert repository.called_with == {"since_hours": 24, "limit": 500}
