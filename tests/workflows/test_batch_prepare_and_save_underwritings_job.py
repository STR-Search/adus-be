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


@pytest.mark.asyncio
async def test_processes_recent_listings_and_returns_summary():
    listings_service = FakeListingsService(
        [
            SimpleNamespace(zpid="1"),
            SimpleNamespace(zpid="2"),
            SimpleNamespace(zpid="3"),
        ]
    )
    prepare_and_save_job = FakePrepareAndSaveJob(
        {
            "1": {"zpid": "1", "status": "saved", "underwriting_id": 10},
            "2": {"zpid": "2", "status": "skipped_existing", "underwriting_id": 20},
            "3": RuntimeError("boom"),
        }
    )

    summary = await BatchPrepareAndSaveUnderwritingsJob(
        listings_service=listings_service,
        prepare_and_save_job=prepare_and_save_job,
    ).run(since_hours=24, limit=500)

    assert listings_service.called_with == {"since_hours": 24, "limit": 500}
    assert prepare_and_save_job.requested_zpids == ["1", "2", "3"]
    assert summary == {
        "found": 3,
        "processed": 3,
        "saved": 1,
        "skipped_existing": 1,
        "failed": 1,
        "results": [
            {"zpid": "1", "status": "saved", "underwriting_id": 10},
            {"zpid": "2", "status": "skipped_existing", "underwriting_id": 20},
            {"zpid": "3", "status": "failed", "error": "boom"},
        ],
    }
