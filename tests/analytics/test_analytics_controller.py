from datetime import date

import pytest
from fastapi import HTTPException

from app.analytics.controllers.analytics_controller import AnalyticsController
from app.iron_bank.schemas.underwriting_analytics import DealStatusBreakdown
from app.zillow.schemas.listing_analytics import HomeStatusBreakdown


class FakeUnderwritingAnalytics:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = []

    async def get_deal_status_breakdown(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return DealStatusBreakdown(total=0, statuses=[])


class FakeListingAnalytics:
    def __init__(self):
        self.calls = []

    async def get_home_status_breakdown(self, **kwargs):
        self.calls.append(kwargs)
        return HomeStatusBreakdown(total=0, statuses=[])


@pytest.mark.asyncio
async def test_passes_filters_through_to_domain_services():
    underwriting, listing = FakeUnderwritingAnalytics(), FakeListingAnalytics()
    controller = AnalyticsController(underwriting, listing)

    await controller.get_deal_status_breakdown(analyst_id=3, added_to=date(2026, 10, 2))
    await controller.get_home_status_breakdown(market_id=12)

    assert underwriting.calls == [
        {"market_id": None, "analyst_id": 3, "added_from": None, "added_to": date(2026, 10, 2)}
    ]
    assert listing.calls == [{"market_id": 12, "created_from": None, "created_to": None}]


@pytest.mark.asyncio
async def test_inverted_range_is_400_and_skips_query():
    underwriting = FakeUnderwritingAnalytics()
    controller = AnalyticsController(underwriting, FakeListingAnalytics())

    with pytest.raises(HTTPException) as exc:
        await controller.get_deal_status_breakdown(
            added_from=date(2026, 10, 5), added_to=date(2026, 10, 1)
        )

    assert exc.value.status_code == 400
    assert underwriting.calls == []


@pytest.mark.asyncio
async def test_unexpected_error_is_500():
    controller = AnalyticsController(
        FakeUnderwritingAnalytics(error=RuntimeError("db down")), FakeListingAnalytics()
    )

    with pytest.raises(HTTPException) as exc:
        await controller.get_deal_status_breakdown()

    assert exc.value.status_code == 500
