from datetime import date

import pytest
from fastapi import HTTPException

from app.analytics.controllers.analytics_controller import AnalyticsController
from app.core.analytics.schemas import Breakdown
from app.iron_bank.schemas.underwriting_analytics import (
    MarketBreakdown,
    MarketRow,
    UnderwritingAnalyticsFilters,
    UnderwritingCompleteness,
)
from app.iron_bank.services.analytics.underwriting_analytics_service import MarketSort
from app.zillow.schemas.listing_analytics import StaleListings
from tests.analytics.conftest import market

EMPTY = Breakdown(total=0, items=[])


def _row(label):
    return MarketRow(
        key=None,
        label=label,
        underwritten=0,
        by_status=[],
        presented=0,
        won=0,
        presented_rate=None,
        win_rate=None,
    )


class FakeUnderwritingAnalytics:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = []

    async def get_deal_status_breakdown(self, filters):
        self.calls.append(("deal_status_breakdown", filters))
        if self.error:
            raise self.error
        return EMPTY

    async def get_market_breakdown(self, filters, *, market_labels, sort):
        self.calls.append(("market_breakdown", market_labels, sort))
        return MarketBreakdown(overall=_row("All markets"), markets=[])

    async def get_automation_split(self, filters):
        self.calls.append(("automation_split", filters))
        return EMPTY

    async def get_job_health(self, **kwargs):
        self.calls.append(("job_health", kwargs))
        return []

    async def get_completeness(self, filters):
        return UnderwritingCompleteness(
            total=0,
            missing_market=0,
            missing_analyst=0,
            missing_price=0,
            missing_status=0,
        )


class FakeListingAnalytics:
    def __init__(self):
        self.calls = []

    async def get_home_status_breakdown(self, **kwargs):
        self.calls.append(kwargs)
        return EMPTY

    async def get_preset_runs(self):
        return []

    async def get_stale_listings(self, **kwargs):
        self.calls.append(kwargs)
        return StaleListings(
            total=0, stale_after_days=kwargs["stale_after_days"], presets=[]
        )


class FakeMarketService:
    async def get_all_summary(self):
        return [market(1, "Asheville - NC"), market(2, None)]


@pytest.mark.asyncio
async def test_passes_filters_through_to_domain_services():
    underwriting, listing = FakeUnderwritingAnalytics(), FakeListingAnalytics()
    controller = AnalyticsController(underwriting, listing)
    filters = UnderwritingAnalyticsFilters(analyst_id=3, added_to=date(2026, 10, 2))

    await controller.get_deal_status_breakdown(filters)
    await controller.get_home_status_breakdown(created_to=date(2026, 10, 2))

    assert underwriting.calls == [("deal_status_breakdown", filters)]
    assert listing.calls == [
        {
            "market_id": None,
            "preset_id": None,
            "created_from": None,
            "created_to": date(2026, 10, 2),
        }
    ]


@pytest.mark.asyncio
async def test_inverted_range_is_400_and_skips_query():
    underwriting = FakeUnderwritingAnalytics()
    controller = AnalyticsController(underwriting, FakeListingAnalytics())

    with pytest.raises(HTTPException) as exc:
        await controller.get_deal_status_breakdown(
            UnderwritingAnalyticsFilters(
                added_from=date(2026, 10, 5), added_to=date(2026, 10, 1)
            )
        )

    assert exc.value.status_code == 400
    assert underwriting.calls == []


@pytest.mark.asyncio
async def test_inverted_secondary_range_is_400():
    controller = AnalyticsController(
        FakeUnderwritingAnalytics(), FakeListingAnalytics()
    )

    with pytest.raises(HTTPException) as exc:
        await controller.get_price_drops(
            UnderwritingAnalyticsFilters(),
            changed_from=date(2026, 10, 5),
            changed_to=date(2026, 10, 1),
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_unexpected_error_is_500():
    controller = AnalyticsController(
        FakeUnderwritingAnalytics(error=RuntimeError("db down")), FakeListingAnalytics()
    )

    with pytest.raises(HTTPException) as exc:
        await controller.get_deal_status_breakdown(UnderwritingAnalyticsFilters())

    assert exc.value.status_code == 500
    assert exc.value.detail == "Failed to fetch deal status breakdown"


@pytest.mark.asyncio
async def test_market_breakdown_gets_market_names_from_markets_domain():
    underwriting = FakeUnderwritingAnalytics()
    controller = AnalyticsController(
        underwriting, FakeListingAnalytics(), market_service=FakeMarketService()
    )

    await controller.get_market_breakdown(
        UnderwritingAnalyticsFilters(), MarketSort.WON
    )

    # A market with no name is left out so the service falls back to "Market <id>".
    assert underwriting.calls == [
        ("market_breakdown", {1: "Asheville - NC"}, MarketSort.WON)
    ]


@pytest.mark.asyncio
async def test_automation_applies_created_range_to_underwritings_and_jobs():
    underwriting = FakeUnderwritingAnalytics()
    controller = AnalyticsController(underwriting, FakeListingAnalytics())

    await controller.get_automation(
        market_id=4, created_from=date(2026, 10, 1), created_to=date(2026, 10, 7)
    )

    (_, filters), (_, job_kwargs) = underwriting.calls
    assert (filters.market_id, filters.added_from, filters.added_to) == (
        4,
        date(2026, 10, 1),
        date(2026, 10, 7),
    )
    assert job_kwargs == {
        "created_from": date(2026, 10, 1),
        "created_to": date(2026, 10, 7),
    }


@pytest.mark.asyncio
async def test_data_completeness_composes_both_domains():
    listing = FakeListingAnalytics()
    controller = AnalyticsController(FakeUnderwritingAnalytics(), listing)

    result = await controller.get_data_completeness(
        UnderwritingAnalyticsFilters(), stale_after_days=30
    )

    assert result.stale_listings.stale_after_days == 30
    assert listing.calls == [{"stale_after_days": 30}]
