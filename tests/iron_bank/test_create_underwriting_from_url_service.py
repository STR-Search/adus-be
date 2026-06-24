from types import SimpleNamespace

import pytest

from app.iron_bank.services.create_underwriting_from_url_service import (
    CreateUnderwritingFromUrlService,
    UnderwritingAlreadyExistsError,
)

REQUEST_URL = "https://www.zillow.com/homedetails/26110417_zpid/"


class FakeZillowPropertyService:
    def __init__(self, result):
        self.result = result
        self.called_url = None

    async def fetch_property_details(self, *, url: str):
        self.called_url = url
        return self.result


class FakeSaveService:
    def __init__(self):
        self.saved_payload = None

    async def save(self, payload):
        self.saved_payload = payload
        return type("Result", (), {"underwriting_id": 130})()


class FakeUnderwritingReader:
    def __init__(self, existing=None):
        self.existing = existing
        self.requested_url = None

    async def get_by_listing_url(self, listing_url: str):
        self.requested_url = listing_url
        return self.existing


def _zillow_property():
    return {
        "id": "26110417",
        "url": "https://www.zillow.com/homedetails/mapped",
        "price": 389000.0,
        "address": "727 N Pine St, San Antonio, TX 78202",
        "bedrooms": 5,
    }


@pytest.mark.asyncio
async def test_create_fetches_builds_and_saves():
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    save_service = FakeSaveService()
    reader = FakeUnderwritingReader(existing=None)
    service = CreateUnderwritingFromUrlService(zillow_service, save_service, reader)

    result = await service.create(url=REQUEST_URL)

    # checked for an existing underwriting by the request URL first
    assert reader.requested_url == REQUEST_URL
    # fetched with the request URL
    assert zillow_service.called_url == REQUEST_URL
    # built a non-automated payload carrying the fetched zillow data
    payload = save_service.saved_payload
    assert payload.is_automated is False
    assert payload.listing_url == REQUEST_URL
    assert payload.zpid is None  # FK to scheduled_listings; not set here
    assert payload.details.zillow_property.id == "26110417"
    # returns the new underwriting id
    assert result.underwriting_id == 130


@pytest.mark.asyncio
async def test_create_is_idempotent_when_listing_url_exists():
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    save_service = FakeSaveService()
    reader = FakeUnderwritingReader(existing=SimpleNamespace(id=77))
    service = CreateUnderwritingFromUrlService(zillow_service, save_service, reader)

    with pytest.raises(UnderwritingAlreadyExistsError) as exc:
        await service.create(url=REQUEST_URL)

    assert exc.value.underwriting_id == 77
    # short-circuits before the external call and before persisting
    assert zillow_service.called_url is None
    assert save_service.saved_payload is None


@pytest.mark.asyncio
async def test_create_raises_when_fetch_returns_none():
    zillow_service = FakeZillowPropertyService(result=None)
    save_service = FakeSaveService()
    reader = FakeUnderwritingReader(existing=None)
    service = CreateUnderwritingFromUrlService(zillow_service, save_service, reader)

    with pytest.raises(ValueError, match="Could not fetch"):
        await service.create(url=REQUEST_URL)

    # nothing persisted on failure
    assert save_service.saved_payload is None
