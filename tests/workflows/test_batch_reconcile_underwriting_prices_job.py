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
async def test_processes_recent_price_changes_and_returns_summary():
    details_service = FakeListingDetailsService(["1", "2", "3", "4"])
    # zpid "1" carries two versions — one moved, one was already current — which
    # is why the per-listing counts and the per-underwriting counts differ.
    reconcile_job = FakeReconcileJob(
        {
            "1": {
                "zpid": "1",
                "status": "updated",
                "results": [
                    {"underwriting_id": 10, "version": 0, "status": "updated"},
                    {
                        "underwriting_id": 11,
                        "version": 1,
                        "status": "skipped_same_price",
                    },
                ],
            },
            "2": {
                "zpid": "2",
                "status": "skipped_same_price",
                "results": [
                    {
                        "underwriting_id": 20,
                        "version": 0,
                        "status": "skipped_same_price",
                    }
                ],
            },
            "3": {"zpid": "3", "status": "skipped_no_underwriting", "results": []},
            "4": RuntimeError("boom"),
        }
    )

    db = FakeSession()
    summary = await BatchReconcileUnderwritingPricesJob(
        db=db,
        listing_details_service=details_service,
        reconcile_job=reconcile_job,
    ).run(since_hours=24, limit=500)

    assert details_service.called_with == {"since_hours": 24, "limit": 500}
    # The one failing zpid ("4") must roll the session back.
    assert db.rollback_count == 1
    # listings
    assert summary["found"] == 4
    assert summary["processed"] == 4
    assert summary["updated"] == 1
    assert summary["skipped_same_price"] == 1
    assert summary["skipped_no_underwriting"] == 1
    assert summary["skipped_no_purchase_price"] == 0
    assert summary["skipped_terminal_status"] == 0
    assert summary["failed"] == 1
    # underwritings — 3 rows across those listings, counted independently
    assert summary["underwritings"] == {
        "updated": 1,
        "skipped_same_price": 2,
        "skipped_no_underwriting": 0,
        "skipped_no_purchase_price": 0,
        "skipped_terminal_status": 0,
        "failed": 0,
    }
    assert [r["zpid"] for r in summary["results"]] == ["1", "2", "3", "4"]
    assert summary["results"][3] == {
        "zpid": "4",
        "status": "failed",
        "error": "boom",
    }


@pytest.mark.asyncio
async def test_an_unknown_status_does_not_kill_the_batch():
    """A status added to the reconcile job must not KeyError mid-run."""
    details_service = FakeListingDetailsService(["1"])
    reconcile_job = FakeReconcileJob(
        {
            "1": {
                "zpid": "1",
                "status": "some_new_status",
                "results": [
                    {"underwriting_id": 10, "version": 0, "status": "some_new_row"}
                ],
            }
        }
    )

    summary = await BatchReconcileUnderwritingPricesJob(
        db=FakeSession(),
        listing_details_service=details_service,
        reconcile_job=reconcile_job,
    ).run(since_hours=24, limit=None)

    assert summary["some_new_status"] == 1
    assert summary["underwritings"]["some_new_row"] == 1
    assert summary["failed"] == 0


@pytest.mark.asyncio
async def test_rolls_back_and_continues_after_a_mid_batch_failure():
    """A failure partway through must not take the rest of the batch with it.

    Without the rollback the session stays in an aborted transaction and every
    subsequent query raises PendingRollbackError, so one transient error would
    fail the whole run.
    """
    details_service = FakeListingDetailsService(["1", "2", "3"])
    reconcile_job = FakeReconcileJob(
        {
            "1": {"zpid": "1", "status": "updated", "underwriting_id": 10},
            "2": RuntimeError("boom"),
            "3": {"zpid": "3", "status": "updated", "underwriting_id": 30},
        }
    )

    db = FakeSession()
    summary = await BatchReconcileUnderwritingPricesJob(
        db=db,
        listing_details_service=details_service,
        reconcile_job=reconcile_job,
    ).run(since_hours=24, limit=None)

    assert reconcile_job.requested_zpids == ["1", "2", "3"]
    assert db.rollback_count == 1
    assert summary["updated"] == 2
    assert summary["failed"] == 1
