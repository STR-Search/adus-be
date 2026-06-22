import pytest

from app.workflows.batch_reconcile_underwriting_prices_job import (
    BatchReconcileUnderwritingPricesJob,
)


class FakeListingDetailsService:
    def __init__(self, zpids):
        self.zpids = zpids
        self.called_with = None

    async def get_price_changed_zpids_since(self, *, since_hours, limit):
        self.called_with = {"since_hours": since_hours, "limit": limit}
        return self.zpids


class FakeReconcileJob:
    def __init__(self, results):
        self.results = results

    async def run(self, zpid):
        result = self.results[zpid]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.asyncio
async def test_processes_recent_price_changes_and_returns_summary():
    details_service = FakeListingDetailsService(["1", "2", "3", "4"])
    reconcile_job = FakeReconcileJob(
        {
            "1": {"zpid": "1", "status": "updated", "underwriting_id": 10},
            "2": {
                "zpid": "2",
                "status": "skipped_same_price",
                "underwriting_id": 20,
            },
            "3": {"zpid": "3", "status": "skipped_no_underwriting"},
            "4": RuntimeError("boom"),
        }
    )

    summary = await BatchReconcileUnderwritingPricesJob(
        listing_details_service=details_service,
        reconcile_job=reconcile_job,
    ).run(since_hours=24, limit=500)

    assert details_service.called_with == {"since_hours": 24, "limit": 500}
    assert summary == {
        "found": 4,
        "processed": 4,
        "updated": 1,
        "skipped_same_price": 1,
        "skipped_no_underwriting": 1,
        "skipped_no_purchase_price": 0,
        "failed": 1,
        "results": [
            {"zpid": "1", "status": "updated", "underwriting_id": 10},
            {
                "zpid": "2",
                "status": "skipped_same_price",
                "underwriting_id": 20,
            },
            {"zpid": "3", "status": "skipped_no_underwriting"},
            {"zpid": "4", "status": "failed", "error": "boom"},
        ],
    }
