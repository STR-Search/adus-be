from types import SimpleNamespace

import pytest

from app.workflows.batch_prepare_and_save_underwritings_job import (
    BatchPrepareAndSaveUnderwritingsJob,
)


class FakeListingsService:
    def __init__(self, listings):
        self.listings = listings
        self.called_with = None

    async def get_active_since(self, *, since_hours, limit):
        self.called_with = {"since_hours": since_hours, "limit": limit}
        return self.listings


class FakePrepareAndSaveJob:
    def __init__(self, results):
        self.results = results
        self.requested_zpids = []

    async def run(self, zpid):
        self.requested_zpids.append(zpid)
        result = self.results[zpid]
        if isinstance(result, Exception):
            raise result
        return result


class FakeSession:
    def __init__(self):
        self.rollback_count = 0

    async def rollback(self):
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_processes_recent_listings_and_returns_summary():
    listings_service = FakeListingsService(
        [
            SimpleNamespace(zpid="1"),
            SimpleNamespace(zpid="2"),
            SimpleNamespace(zpid="3"),
            SimpleNamespace(zpid="4"),
        ]
    )
    prepare_and_save_job = FakePrepareAndSaveJob(
        {
            "1": {"zpid": "1", "status": "saved", "underwriting_id": 10},
            "2": {"zpid": "2", "status": "skipped_existing", "underwriting_id": 20},
            "3": RuntimeError("boom"),
            "4": {"zpid": "4", "status": "skipped_no_purchase_price"},
        }
    )

    db = FakeSession()
    summary = await BatchPrepareAndSaveUnderwritingsJob(
        db=db,
        listings_service=listings_service,
        prepare_and_save_job=prepare_and_save_job,
    ).run(since_hours=24, limit=500)

    assert listings_service.called_with == {"since_hours": 24, "limit": 500}
    assert prepare_and_save_job.requested_zpids == ["1", "2", "3", "4"]
    # The one failing listing ("3") must roll the session back so the rest
    # of the batch runs on a clean transaction.
    assert db.rollback_count == 1
    assert summary == {
        "found": 4,
        "processed": 4,
        "saved": 1,
        "skipped_existing": 1,
        "skipped_no_purchase_price": 1,
        "failed": 1,
        "results": [
            {"zpid": "1", "status": "saved", "underwriting_id": 10},
            {"zpid": "2", "status": "skipped_existing", "underwriting_id": 20},
            {"zpid": "3", "status": "failed", "error": "boom"},
            {"zpid": "4", "status": "skipped_no_purchase_price"},
        ],
    }
