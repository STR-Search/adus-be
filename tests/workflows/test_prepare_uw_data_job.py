from types import SimpleNamespace

import pytest

from app.workflows.prepare_uw_data_job import PrepareUwDataJob


class FakeListingsService:
    def __init__(self, listing):
        self.listing = listing
        self.requested_zpid = None

    async def get_by_zpid(self, zpid):
        self.requested_zpid = zpid
        return self.listing


class FakeListingDetailsService:
    def __init__(self, details=None):
        self.details = details

    async def get_by_zpid(self, zpid):
        return self.details


class FakeMarketService:
    def __init__(self, market=None):
        self.market = market
        self.called = False
        self.requested_id = None

    async def get_by_id(self, market_id):
        self.called = True
        self.requested_id = market_id
        return self.market


class FakeOpexByBedroomsService:
    def __init__(self, opex=None):
        self.opex = opex
        self.called_with = None

    async def get_by_market_and_bedrooms(self, bedrooms, market_id):
        self.called_with = {"bedrooms": bedrooms, "market_id": market_id}
        return self.opex


class FakeOpexBySizeService:
    def __init__(self, opex=None):
        self.opex = opex
        self.called_with = None

    async def get_by_market_and_sqft(self, sqft, market_id):
        self.called_with = {"sqft": sqft, "market_id": market_id}
        return self.opex


class FakeGetAllService:
    def __init__(self, items=None):
        self.items = items or []

    async def get_all(self):
        return self.items


class FakeExternalApiService:
    def __init__(self, fred=None):
        self.fred = fred

    async def get_30y_fixed_rate(self):
        return self.fred


class RecordingUwDataService:
    def __init__(self):
        self.received = None

    def normalize_sqft(self, area):
        return 2000 if area is not None else None

    def prepare(self, **kwargs):
        self.received = kwargs
        return {"prepared": True}


def _listing(preset=SimpleNamespace(market_id=3)):
    return SimpleNamespace(
        zpid="12345",
        detail_url="url",
        img_src="img",
        price=485000,
        address="addr",
        beds=4,
        baths=3,
        area=1800,
        preset=preset,
    )


def _job(listing, market=None, uw_service=None, **overrides):
    deps = dict(
        listings_service=FakeListingsService(listing),
        listing_details_service=FakeListingDetailsService(),
        market_service=FakeMarketService(market),
        opex_by_bedrooms_service=FakeOpexByBedroomsService(),
        opex_by_size_service=FakeOpexBySizeService(),
        construction_amenities_service=FakeGetAllService(),
        construction_remodeling_service=FakeGetAllService(),
        external_api_service=FakeExternalApiService(),
        uw_data_service=uw_service or RecordingUwDataService(),
    )
    deps.update(overrides)
    return PrepareUwDataJob(**deps), deps


@pytest.mark.asyncio
async def test_raises_value_error_when_listing_missing():
    job, _ = _job(listing=None)

    with pytest.raises(ValueError):
        await job.run("missing-zpid")


@pytest.mark.asyncio
async def test_fetches_cross_domain_data_and_delegates_to_service():
    uw_service = RecordingUwDataService()
    market = SimpleNamespace(market_name="Smokies", market_slug="smokies")
    job, deps = _job(listing=_listing(), market=market, uw_service=uw_service)

    result = await job.run("12345")

    assert result == {"prepared": True}
    assert deps["listings_service"].requested_zpid == "12345"
    assert deps["market_service"].requested_id == 3
    assert deps["opex_by_bedrooms_service"].called_with == {
        "bedrooms": 4,
        "market_id": 3,
    }
    # sqft passed to opex-by-size is normalized via the iron_bank service
    assert deps["opex_by_size_service"].called_with == {"sqft": 2000, "market_id": 3}
    assert uw_service.received["listing"] is deps["listings_service"].listing
    assert uw_service.received["market"] is market
    assert uw_service.received["market_id"] == 3


@pytest.mark.asyncio
async def test_skips_market_lookup_when_listing_has_no_preset():
    job, deps = _job(listing=_listing(preset=None))

    await job.run("12345")

    assert deps["market_service"].called is False
    assert deps["opex_by_bedrooms_service"].called_with == {
        "bedrooms": 4,
        "market_id": None,
    }


def test_from_session_wires_real_services():
    job = PrepareUwDataJob.from_session(db=object())

    from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
    from app.zillow.services.scheduled_listings_service import ScheduledListingsService

    assert isinstance(job.uw_data_service, PrepareUwDataService)
    assert isinstance(job.listings_service, ScheduledListingsService)
