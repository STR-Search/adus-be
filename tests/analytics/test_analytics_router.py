"""Query-param parsing for the analytics routes.

The router builds ``UnderwritingAnalyticsFilters`` through shared dependencies;
these tests pin what reaches the controller for each kind of endpoint.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analytics.router import get_analytics_controller, router
from app.analytics.schemas.pipeline import Coverage, CoverageRow
from app.analytics.schemas.status_history import TeamOutput, TimeToPresent
from app.core.analytics.schemas import Breakdown, Granularity, MedianValue
from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.schemas.underwriting_analytics import (
    DEFAULT_ANALYTICS_SOURCES,
    MarketBreakdown,
    MarketRow,
)
from app.zillow.schemas.listing_analytics import IntakeGroupBy


class RecordingController:
    def __init__(self):
        self.calls = []

    async def get_deal_status_breakdown(self, filters):
        self.calls.append(filters)
        return Breakdown(total=0, items=[])

    async def get_home_status_breakdown(self, **kwargs):
        self.calls.append(kwargs)
        return Breakdown(total=0, items=[])

    async def get_market_breakdown(self, filters, sort):
        self.calls.append(filters)
        row = MarketRow(
            key=None,
            label="All markets",
            underwritten=0,
            presented=0,
            won=0,
            presented_rate=None,
            win_rate=None,
        )
        return MarketBreakdown(overall=row, markets=[])

    async def get_coverage(self, **kwargs):
        self.calls.append(kwargs)
        row = CoverageRow(
            key=None,
            label="All presets",
            listings=0,
            underwritten=0,
            coverage=None,
            median_days_to_underwrite=None,
        )
        return Coverage(overall=row, presets=[])

    async def get_intake(self, **kwargs):
        self.calls.append(kwargs)
        return []

    async def get_time_to_present(self, filters, **kwargs):
        self.calls.append((filters, kwargs))
        return TimeToPresent(
            median_days=MedianValue(value=None, sample_size=0),
            p75_days=None,
            observed=0,
            estimated=0,
        )

    async def get_team_output(self, filters, **kwargs):
        self.calls.append((filters, kwargs))
        return TeamOutput(analysts=[], presented_by_approver=[])


def build_client() -> tuple[TestClient, RecordingController]:
    controller = RecordingController()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_analytics_controller] = lambda: controller
    return TestClient(app), controller


def test_defaults_to_current_system_sources_and_every_status():
    client, controller = build_client()

    response = client.get("/analytics/underwritings/deal-status-breakdown")

    assert response.status_code == 200
    (filters,) = controller.calls
    assert filters.source == DEFAULT_ANALYTICS_SOURCES
    assert filters.deal_status is None


def test_repeatable_source_and_deal_status():
    client, controller = build_client()

    response = client.get(
        "/analytics/underwritings/deal-status-breakdown"
        "?source=adus&source=legacy_sheet&deal_status=maybe&deal_status=delete_deal"
        "&market_id=7&added_from=2026-10-01"
    )

    assert response.status_code == 200
    (filters,) = controller.calls
    assert filters.source == (UnderwritingSource.ADUS, UnderwritingSource.LEGACY_SHEET)
    assert filters.deal_status == (DealStatus.MAYBE, DealStatus.DELETE_DEAL)
    assert filters.market_id == 7
    assert str(filters.added_from) == "2026-10-01"


def test_unknown_deal_status_is_422():
    client, _ = build_client()

    response = client.get(
        "/analytics/underwritings/deal-status-breakdown?deal_status=nope"
    )

    assert response.status_code == 422


def test_per_market_endpoint_ignores_market_id():
    client, controller = build_client()

    response = client.get(
        "/analytics/underwritings/market-breakdown?market_id=7&analyst_id=3"
    )

    assert response.status_code == 200
    (filters,) = controller.calls
    assert filters.market_id is None
    assert filters.analyst_id == 3


def test_listing_endpoint_accepts_market_id():
    client, controller = build_client()

    response = client.get("/analytics/listings/home-status-breakdown?market_id=12")

    assert response.status_code == 200
    assert controller.calls == [
        {"market_id": 12, "preset_id": None, "created_from": None, "created_to": None}
    ]


def test_intake_group_by_market():
    client, controller = build_client()

    response = client.get("/analytics/listings/intake?group_by=market")

    assert response.status_code == 200
    assert controller.calls[0]["group_by"] is IntakeGroupBy.MARKET


def test_intake_unknown_group_by_is_422():
    client, _ = build_client()

    assert client.get("/analytics/listings/intake?group_by=state").status_code == 422


def test_delete_reasons_endpoint_is_gone():
    client, _ = build_client()

    response = client.get("/analytics/underwritings/delete-reasons")

    assert response.status_code == 404


def test_coverage_accepts_market_id():
    client, controller = build_client()

    response = client.get("/analytics/pipeline/coverage?market_id=3")

    assert response.status_code == 200
    assert controller.calls[0]["market_id"] == 3


def test_time_to_present_takes_global_filters_and_presented_range():
    client, controller = build_client()

    response = client.get(
        "/analytics/status-history/time-to-present"
        "?market_id=4&added_from=2026-09-01&presented_from=2026-10-01"
    )

    assert response.status_code == 200
    ((filters, kwargs),) = controller.calls
    assert filters.market_id == 4
    assert str(filters.added_from) == "2026-09-01"
    assert str(kwargs["presented_from"]) == "2026-10-01"
    assert kwargs["presented_to"] is None


def test_team_output_ignores_analyst_id_and_takes_occurred_range():
    client, controller = build_client()

    response = client.get(
        "/analytics/status-history/team-output"
        "?market_id=4&analyst_id=3&occurred_to=2026-10-31&granularity=day"
    )

    assert response.status_code == 200
    ((filters, kwargs),) = controller.calls
    assert filters.market_id == 4
    assert filters.analyst_id is None
    assert str(kwargs["occurred_to"]) == "2026-10-31"
    assert kwargs["granularity"] is Granularity.DAY
