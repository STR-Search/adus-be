from types import SimpleNamespace

import pytest

from scripts import run_uw_auto_prepare


class FakeSessionFactory:
    def __init__(self):
        self.session = SimpleNamespace(name="session")

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeCreationJob:
    session = None
    called_with = None

    @classmethod
    def from_session(cls, session):
        cls.session = session
        return cls()

    async def run(self, *, since_hours, limit):
        self.__class__.called_with = {"since_hours": since_hours, "limit": limit}
        return {"saved": 2, "failed": 0}


class FakeReconciliationJob:
    session = None
    called_with = None

    @classmethod
    def from_session(cls, session):
        cls.session = session
        return cls()

    async def run(self, *, since_hours, limit):
        self.__class__.called_with = {"since_hours": since_hours, "limit": limit}
        return {"updated": 1, "failed": 0}


@pytest.mark.asyncio
async def test_run_batch_runs_creation_and_price_reconciliation():
    summary = await run_uw_auto_prepare.run_batch(
        since_hours=24,
        limit=500,
        session_factory=FakeSessionFactory,
        creation_job_cls=FakeCreationJob,
        reconciliation_job_cls=FakeReconciliationJob,
    )

    assert summary == {
        "creation": {"saved": 2, "failed": 0},
        "price_reconciliation": {"updated": 1, "failed": 0},
    }
    assert FakeCreationJob.session.name == "session"
    assert FakeReconciliationJob.session.name == "session"
    assert FakeCreationJob.called_with == {"since_hours": 24, "limit": 500}
    assert FakeReconciliationJob.called_with == {
        "since_hours": 24,
        "limit": 500,
    }


class FakeSingleJob:
    session = None
    called_with = None

    @classmethod
    def from_session(cls, session):
        cls.session = session
        return cls()

    async def run(self, zpid):
        self.__class__.called_with = {"zpid": zpid}
        return {"zpid": zpid, "status": "saved", "underwriting_id": 7}


@pytest.mark.asyncio
async def test_run_single_uses_session_and_single_job():
    summary = await run_uw_auto_prepare.run_single(
        zpid="12345",
        session_factory=FakeSessionFactory,
        job_cls=FakeSingleJob,
    )

    assert summary == {"zpid": "12345", "status": "saved", "underwriting_id": 7}
    assert FakeSingleJob.session.name == "session"
    assert FakeSingleJob.called_with == {"zpid": "12345"}
