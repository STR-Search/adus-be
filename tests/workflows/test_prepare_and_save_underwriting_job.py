from types import SimpleNamespace

import pytest

from app.workflows.prepare_and_save_underwriting_job import PrepareAndSaveUnderwritingJob


class FakePrepareJob:
    def __init__(self, prepared):
        self.prepared = prepared
        self.requested_zpid = None

    async def run(self, zpid):
        self.requested_zpid = zpid
        return self.prepared


class FakePayloadBuilder:
    def __init__(self, payload):
        self.payload = payload
        self.received = None

    def build(self, prepared):
        self.received = prepared
        return self.payload


class FakeExistingRepository:
    def __init__(self, underwriting=None):
        self.underwriting = underwriting
        self.requested_zpid = None

    async def get_by_zpid(self, zpid):
        self.requested_zpid = zpid
        return self.underwriting


class FakeSaveService:
    def __init__(self):
        self.saved_payload = None

    async def save(self, payload):
        self.saved_payload = payload
        return SimpleNamespace(underwriting_id=42)


@pytest.mark.asyncio
async def test_prepares_maps_and_saves_listing():
    prepared = {"zillow_property": {"id": "12345"}}
    payload = SimpleNamespace(zpid="12345")
    prepare_job = FakePrepareJob(prepared)
    builder = FakePayloadBuilder(payload)
    save_service = FakeSaveService()

    result = await PrepareAndSaveUnderwritingJob(
        prepare_job=prepare_job,
        payload_builder=builder,
        save_service=save_service,
        underwriting_repository=FakeExistingRepository(),
    ).run("12345")

    assert result == {
        "zpid": "12345",
        "status": "saved",
        "underwriting_id": 42,
    }
    assert prepare_job.requested_zpid == "12345"
    assert builder.received is prepared
    assert save_service.saved_payload is payload


@pytest.mark.asyncio
async def test_skips_existing_underwriting_for_zpid():
    existing = SimpleNamespace(id=7)
    save_service = FakeSaveService()

    result = await PrepareAndSaveUnderwritingJob(
        prepare_job=FakePrepareJob({"zillow_property": {"id": "12345"}}),
        payload_builder=FakePayloadBuilder(SimpleNamespace(zpid="12345")),
        save_service=save_service,
        underwriting_repository=FakeExistingRepository(existing),
    ).run("12345")

    assert result == {
        "zpid": "12345",
        "status": "skipped_existing",
        "underwriting_id": 7,
    }
    assert save_service.saved_payload is None
