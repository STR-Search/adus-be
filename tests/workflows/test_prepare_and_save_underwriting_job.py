from types import SimpleNamespace

import pytest

from app.airbnb_public.services.cleaned_data_service import CleanedDataService
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService
from app.workflows.prepare_and_save_underwriting_job import (
    PrepareAndSaveUnderwritingJob,
)
from app.zillow.services.scheduled_listings_service import ScheduledListingsService


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
    payload = SimpleNamespace(
        zpid="12345",
        purchase_price=None,
        details=SimpleNamespace(
            purchase_details=SimpleNamespace(purchase_price=100000)
        ),
    )
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
        payload_builder=FakePayloadBuilder(
            SimpleNamespace(zpid="12345", purchase_price=100000)
        ),
        save_service=save_service,
        underwriting_repository=FakeExistingRepository(existing),
    ).run("12345")

    assert result == {
        "zpid": "12345",
        "status": "skipped_existing",
        "underwriting_id": 7,
    }
    assert save_service.saved_payload is None


@pytest.mark.asyncio
async def test_skips_listing_when_purchase_price_is_missing():
    prepared = {"zillow_property": {"id": "12345"}}
    payload = SimpleNamespace(zpid="12345", purchase_price=None)
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
        "status": "skipped_no_purchase_price",
    }
    assert builder.received is prepared
    assert save_service.saved_payload is None


def test_from_session_wires_save_service_for_airbnb_revenue_fallback():
    job = PrepareAndSaveUnderwritingJob.from_session(object())

    assert isinstance(job.save_service, SaveUnderwritingService)
    assert job.save_service.market_service is not None
    assert isinstance(job.save_service.listings_service, ScheduledListingsService)
    assert isinstance(job.save_service.cleaned_data_service, CleanedDataService)


class FakeListingsServiceForGuard:
    def __init__(self, detail_url):
        self.detail_url = detail_url
        self.requested_zpid = None

    async def get_by_zpid(self, zpid):
        self.requested_zpid = zpid
        return SimpleNamespace(detail_url=self.detail_url)


class GuardRepository:
    """Repository whose zpid lookup misses but whose URL lookup hits."""

    def __init__(self, by_zpid=None, by_listing_url=None):
        self._by_zpid = by_zpid
        self._by_listing_url = by_listing_url
        self.requested_listing_url = None

    async def get_by_zpid(self, zpid):
        return self._by_zpid

    async def get_by_listing_url(self, listing_url):
        self.requested_listing_url = listing_url
        return self._by_listing_url


DETAIL_URL = "https://www.zillow.com/homedetails/26110417_zpid/"


@pytest.mark.asyncio
async def test_skips_a_null_zpid_deal_found_by_listing_url():
    """A URL-created deal predating zpid capture must still block automation.

    Without the fallback the automated run creates a second, unrelated series
    for a property an analyst has already underwritten.
    """
    repository = GuardRepository(
        by_zpid=None, by_listing_url=SimpleNamespace(id=77)
    )
    listings = FakeListingsServiceForGuard(DETAIL_URL)
    job = PrepareAndSaveUnderwritingJob(
        prepare_job=FakePrepareJob({}),
        payload_builder=FakePayloadBuilder(SimpleNamespace()),
        save_service=FakeSaveService(),
        underwriting_repository=repository,
        listings_service=listings,
    )

    result = await job.run("26110417")

    assert result == {
        "zpid": "26110417",
        "status": "skipped_existing",
        "underwriting_id": 77,
    }
    assert repository.requested_listing_url == DETAIL_URL


@pytest.mark.asyncio
async def test_zpid_hit_short_circuits_before_the_url_lookup():
    repository = GuardRepository(by_zpid=SimpleNamespace(id=10))
    listings = FakeListingsServiceForGuard(DETAIL_URL)
    job = PrepareAndSaveUnderwritingJob(
        prepare_job=FakePrepareJob({}),
        payload_builder=FakePayloadBuilder(SimpleNamespace()),
        save_service=FakeSaveService(),
        underwriting_repository=repository,
        listings_service=listings,
    )

    result = await job.run("26110417")

    assert result["underwriting_id"] == 10
    # no wasted listing fetch when the zpid already matched
    assert listings.requested_zpid is None
    assert repository.requested_listing_url is None
