"""Query-param parsing for the analytics routes.

The router builds ``UnderwritingAnalyticsFilters`` through shared dependencies;
these tests pin what reaches the controller for each kind of endpoint.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analytics.router import get_analytics_controller, router
from app.core.analytics.schemas import Breakdown
from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.schemas.underwriting_analytics import (
    DEFAULT_ANALYTICS_SOURCES,
    DeleteReasonRow,
    DeleteReasons,
)


class RecordingController:
    def __init__(self):
        self.calls = []

    async def get_deal_status_breakdown(self, filters):
        self.calls.append(filters)
        return Breakdown(total=0, items=[])

    async def get_delete_reasons(self, filters):
        self.calls.append(filters)
        row = DeleteReasonRow(key=None, label="All markets", total=0, by_status=[])
        return DeleteReasons(overall=row, markets=[])


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

    response = client.get("/analytics/underwritings/deal-status-breakdown?deal_status=nope")

    assert response.status_code == 422


def test_per_market_endpoint_ignores_market_id():
    client, controller = build_client()

    response = client.get("/analytics/underwritings/delete-reasons?market_id=7&analyst_id=3")

    assert response.status_code == 200
    (filters,) = controller.calls
    assert filters.market_id is None
    assert filters.analyst_id == 3
