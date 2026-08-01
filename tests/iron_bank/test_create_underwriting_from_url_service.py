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


class FakeMarketContextReader:
    """Stands in for PrepareUwDataJob, which satisfies the reader protocol."""

    def __init__(self, context=None):
        self.context = context or SimpleNamespace(
            market_id=3, opex=SimpleNamespace(absolute={"internet": 100})
        )
        self.called_with = None

    async def build_market_context(self, *, market_id, bedrooms, area):
        self.called_with = {
            "market_id": market_id,
            "bedrooms": bedrooms,
            "area": area,
        }
        return self.context


class RecordingBuilder:
    def __init__(self):
        self.received = None

    def build_from_zillow_property(self, **kwargs):
        self.received = kwargs
        return SimpleNamespace(name="payload")


def _zillow_property(**overrides):
    base = {
        "id": "26110417",
        "url": "https://www.zillow.com/homedetails/mapped",
        "price": 389000.0,
        "address": "727 N Pine St, San Antonio, TX 78202",
        "bedrooms": 5,
        "area": 4608,
    }
    base.update(overrides)
    return base


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


def _service(zillow_property=None, context_reader=None, builder=None):
    return CreateUnderwritingFromUrlService(
        FakeZillowPropertyService(result=zillow_property or _zillow_property()),
        FakeSaveService(),
        FakeUnderwritingReader(existing=None),
        market_context_reader=context_reader or FakeMarketContextReader(),
        builder=builder or RecordingBuilder(),
    )


@pytest.mark.asyncio
async def test_create_loads_market_context_keyed_to_the_fetched_property():
    context_reader = FakeMarketContextReader()
    builder = RecordingBuilder()
    service = _service(context_reader=context_reader, builder=builder)

    await service.create(url=REQUEST_URL, market_id=3)

    # bedrooms and sqft come off the live fetch, since there is no listing row
    assert context_reader.called_with == {"market_id": 3, "bedrooms": 5, "area": 4608}
    # and the context is handed to the builder to seed opex/rehab items
    assert builder.received["market_context"] is context_reader.context


@pytest.mark.asyncio
async def test_create_passes_a_null_market_id_through_for_a_template():
    context_reader = FakeMarketContextReader()
    service = _service(context_reader=context_reader)

    await service.create(url=REQUEST_URL)

    # the reader decides what a missing market means (template fallback), not us
    assert context_reader.called_with["market_id"] is None


@pytest.mark.asyncio
async def test_create_coerces_zillow_float_bedrooms_and_area_to_ints():
    context_reader = FakeMarketContextReader()
    service = _service(
        zillow_property=_zillow_property(bedrooms=5.0, area=4608.0),
        context_reader=context_reader,
    )

    await service.create(url=REQUEST_URL, market_id=3)

    assert context_reader.called_with["bedrooms"] == 5
    assert context_reader.called_with["area"] == 4608


@pytest.mark.asyncio
async def test_create_tolerates_missing_bedrooms_and_area():
    context_reader = FakeMarketContextReader()
    service = _service(
        zillow_property=_zillow_property(bedrooms=None, area=None),
        context_reader=context_reader,
    )

    await service.create(url=REQUEST_URL, market_id=3)

    assert context_reader.called_with == {
        "market_id": 3,
        "bedrooms": None,
        "area": None,
    }


@pytest.mark.asyncio
async def test_create_without_a_context_reader_seeds_no_line_items():
    builder = RecordingBuilder()
    service = CreateUnderwritingFromUrlService(
        FakeZillowPropertyService(result=_zillow_property()),
        FakeSaveService(),
        FakeUnderwritingReader(existing=None),
        builder=builder,
    )

    await service.create(url=REQUEST_URL, market_id=3)

    assert builder.received["market_context"] is None
