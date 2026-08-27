from types import SimpleNamespace

import pytest

from app.iron_bank.services.create_underwriting_from_url_service import (
    CreateUnderwritingFromUrlService,
    ListingMarketMismatchError,
    ListingNotScrapedError,
    UnderwritingAlreadyExistsError,
)

REQUEST_URL = "https://www.zillow.com/homedetails/26110417_zpid/"


class FakeZillowPropertyService:
    def __init__(self, result):
        self.result = result
        self.called_url = None
        self.called_market_id = None

    async def fetch_property_details(self, *, url: str, market_id: int | None = None):
        self.called_url = url
        self.called_market_id = market_id
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


class FakeListingsService:
    """Stands in for ScheduledListingsService.

    ``by_url`` is what the pre-fetch guard sees: None models a pasted URL that
    doesn't match the scraper's stored detail_url, which is the common case.
    """

    def __init__(self, listing=None, by_url=None):
        self.listing = listing
        self.by_url = by_url
        self.requested_zpid = None
        self.requested_url = None

    async def get_by_zpid(self, zpid: str):
        self.requested_zpid = zpid
        return self.listing

    async def get_by_detail_url(self, detail_url: str):
        self.requested_url = detail_url
        return self.by_url


@pytest.mark.asyncio
async def test_create_stamps_the_zpid_when_the_listing_was_scraped():
    """Fetching details persists the listing, so the FK is satisfiable."""
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    save_service = FakeSaveService()
    listings = FakeListingsService(listing=SimpleNamespace(zpid="26110417"))
    service = CreateUnderwritingFromUrlService(
        zillow_service,
        save_service,
        FakeUnderwritingReader(existing=None),
        listings_service=listings,
    )

    await service.create(url=REQUEST_URL)

    assert listings.requested_zpid == "26110417"
    assert save_service.saved_payload.zpid == "26110417"
    # still preserved on the stored blob as well
    assert save_service.saved_payload.details.zillow_property.id == "26110417"


@pytest.mark.asyncio
async def test_create_raises_when_the_listing_never_landed():
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    save_service = FakeSaveService()
    service = CreateUnderwritingFromUrlService(
        zillow_service,
        save_service,
        FakeUnderwritingReader(existing=None),
        listings_service=FakeListingsService(listing=None),
    )

    with pytest.raises(ListingNotScrapedError) as exc:
        await service.create(url=REQUEST_URL)

    assert exc.value.zpid == "26110417"
    assert exc.value.url == REQUEST_URL
    # nothing is persisted: a deal detached from its listing is invisible to
    # every job that keys on zpid
    assert save_service.saved_payload is None


@pytest.mark.asyncio
async def test_create_raises_when_the_fetched_property_has_no_zpid():
    zillow_service = FakeZillowPropertyService(result=_zillow_property(id=None))
    save_service = FakeSaveService()
    listings = FakeListingsService(listing=SimpleNamespace(zpid="26110417"))
    service = CreateUnderwritingFromUrlService(
        zillow_service,
        save_service,
        FakeUnderwritingReader(existing=None),
        listings_service=listings,
    )

    with pytest.raises(ListingNotScrapedError) as exc:
        await service.create(url=REQUEST_URL)

    assert exc.value.zpid is None
    # never looked up, because there was nothing to look up with
    assert listings.requested_zpid is None
    assert save_service.saved_payload is None


@pytest.mark.asyncio
async def test_create_without_a_listings_service_leaves_zpid_null():
    """Back-compat: callers that can't verify the listing still work."""
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    save_service = FakeSaveService()
    service = CreateUnderwritingFromUrlService(
        zillow_service, save_service, FakeUnderwritingReader(existing=None)
    )

    await service.create(url=REQUEST_URL)

    assert save_service.saved_payload.zpid is None


def _listing(*, market_id, zpid="26110417"):
    """A scraped listing under a preset belonging to ``market_id``.

    ``market_id=None`` is the exploratory bucket: the listing landed against the
    default preset for "no active market".
    """
    return SimpleNamespace(
        zpid=zpid, preset=SimpleNamespace(market_id=market_id, is_default=True)
    )


class FakeMarketNameReader:
    """Stands in for MarketService."""

    def __init__(self, name="Austin, TX", error=None):
        self.name = name
        self.error = error
        self.requested_market_id = None

    async def get_market_name_current(self, market_id: int):
        self.requested_market_id = market_id
        if self.error is not None:
            raise self.error
        return self.name


def _service_with_listing(listing, by_url=None, **kwargs):
    return CreateUnderwritingFromUrlService(
        FakeZillowPropertyService(result=_zillow_property()),
        kwargs.pop("save_service", FakeSaveService()),
        FakeUnderwritingReader(existing=None),
        listings_service=FakeListingsService(listing=listing, by_url=by_url),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_create_rejects_a_market_the_listing_does_not_belong_to():
    save_service = FakeSaveService()
    service = _service_with_listing(
        _listing(market_id=3), save_service=save_service
    )

    with pytest.raises(ListingMarketMismatchError) as exc:
        await service.create(url=REQUEST_URL, market_id=5)

    assert exc.value.requested_market_id == 5
    assert exc.value.listing_market_id == 3
    assert exc.value.zpid == "26110417"
    # the correct id is in the message the analyst sees
    assert "market_id=3" in str(exc.value)
    # nothing persisted: the deal would have been seeded from market 5's opex
    assert save_service.saved_payload is None


@pytest.mark.asyncio
async def test_create_rejects_a_null_market_when_the_listing_has_one():
    """The guard runs even with no market_id — there is a right answer to give."""
    save_service = FakeSaveService()
    service = _service_with_listing(
        _listing(market_id=3), save_service=save_service
    )

    with pytest.raises(ListingMarketMismatchError) as exc:
        await service.create(url=REQUEST_URL)

    assert exc.value.requested_market_id is None
    assert exc.value.listing_market_id == 3
    # otherwise this would have been seeded from the zeroed template
    assert save_service.saved_payload is None


@pytest.mark.asyncio
async def test_create_proceeds_when_the_market_matches_the_listing():
    save_service = FakeSaveService()
    service = _service_with_listing(
        _listing(market_id=3), save_service=save_service
    )

    await service.create(url=REQUEST_URL, market_id=3)

    assert save_service.saved_payload.zpid == "26110417"


@pytest.mark.asyncio
async def test_create_allows_any_market_for_an_exploratory_listing():
    """A NULL preset market is "no market yet", not a market to contradict."""
    save_service = FakeSaveService()
    service = _service_with_listing(
        _listing(market_id=None), save_service=save_service
    )

    await service.create(url=REQUEST_URL, market_id=5)

    assert save_service.saved_payload.zpid == "26110417"


@pytest.mark.asyncio
async def test_create_allows_a_null_market_for_an_exploratory_listing():
    save_service = FakeSaveService()
    service = _service_with_listing(
        _listing(market_id=None), save_service=save_service
    )

    await service.create(url=REQUEST_URL)

    assert save_service.saved_payload.zpid == "26110417"


@pytest.mark.asyncio
async def test_create_skips_the_guard_when_the_listing_carries_no_preset():
    """Mirror-model drift disables the guard rather than 500ing the create."""
    save_service = FakeSaveService()
    service = _service_with_listing(
        SimpleNamespace(zpid="26110417"), save_service=save_service
    )

    await service.create(url=REQUEST_URL, market_id=5)

    assert save_service.saved_payload.zpid == "26110417"


@pytest.mark.asyncio
async def test_create_skips_the_guard_without_a_listings_service():
    """No listing to check against, so the requested market stands."""
    save_service = FakeSaveService()
    service = CreateUnderwritingFromUrlService(
        FakeZillowPropertyService(result=_zillow_property()),
        save_service,
        FakeUnderwritingReader(existing=None),
    )

    await service.create(url=REQUEST_URL, market_id=5)

    assert save_service.saved_payload is not None


@pytest.mark.asyncio
async def test_mismatch_names_the_market_the_listing_belongs_to():
    """The analyst picks markets by name, so the id alone is unactionable."""
    names = FakeMarketNameReader(name="Austin, TX")
    service = _service_with_listing(_listing(market_id=3), market_name_reader=names)

    with pytest.raises(ListingMarketMismatchError) as exc:
        await service.create(url=REQUEST_URL, market_id=5)

    assert names.requested_market_id == 3
    assert exc.value.listing_market_name == "Austin, TX"
    # both, so a human can read it and a client can re-submit with it
    assert "Austin, TX" in str(exc.value)
    assert "market_id=3" in str(exc.value)


@pytest.mark.asyncio
async def test_market_name_is_not_resolved_on_the_happy_path():
    """Naming costs a query; only the error path should pay it."""
    names = FakeMarketNameReader()
    service = _service_with_listing(_listing(market_id=3), market_name_reader=names)

    await service.create(url=REQUEST_URL, market_id=3)

    assert names.requested_market_id is None


@pytest.mark.asyncio
async def test_mismatch_degrades_to_the_id_when_the_market_cannot_be_named():
    """Unknown or soft-deleted market: the conflict is still real."""
    names = FakeMarketNameReader(name=None)
    service = _service_with_listing(_listing(market_id=3), market_name_reader=names)

    with pytest.raises(ListingMarketMismatchError) as exc:
        await service.create(url=REQUEST_URL, market_id=5)

    assert exc.value.listing_market_name is None
    assert "belongs to market 3" in str(exc.value)


@pytest.mark.asyncio
async def test_a_failed_name_lookup_still_raises_the_mismatch():
    """A lookup blowing up must not turn an actionable 409 into a 500."""
    names = FakeMarketNameReader(error=RuntimeError("db down"))
    service = _service_with_listing(_listing(market_id=3), market_name_reader=names)

    with pytest.raises(ListingMarketMismatchError) as exc:
        await service.create(url=REQUEST_URL, market_id=5)

    assert exc.value.listing_market_id == 3
    assert exc.value.listing_market_name is None


@pytest.mark.asyncio
async def test_mismatch_without_a_name_reader_still_raises():
    service = _service_with_listing(_listing(market_id=3))

    with pytest.raises(ListingMarketMismatchError) as exc:
        await service.create(url=REQUEST_URL, market_id=5)

    assert exc.value.listing_market_name is None


@pytest.mark.asyncio
async def test_market_mismatch_is_caught_before_the_fetch_when_the_url_is_on_file():
    """Saves the external call, and the wrong-market scrape attribution."""
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    save_service = FakeSaveService()
    listings = FakeListingsService(by_url=_listing(market_id=3))
    service = CreateUnderwritingFromUrlService(
        zillow_service,
        save_service,
        FakeUnderwritingReader(existing=None),
        listings_service=listings,
        market_name_reader=FakeMarketNameReader(name="Austin, TX"),
    )

    with pytest.raises(ListingMarketMismatchError) as exc:
        await service.create(url=REQUEST_URL, market_id=5)

    assert listings.requested_url == REQUEST_URL
    assert exc.value.listing_market_id == 3
    assert exc.value.listing_market_name == "Austin, TX"
    assert exc.value.zpid == "26110417"
    # never reached the external API
    assert zillow_service.called_url is None
    assert save_service.saved_payload is None


@pytest.mark.asyncio
async def test_pre_fetch_guard_runs_after_the_duplicate_guard():
    """A duplicate underwriting still wins, and costs no listing query."""
    listings = FakeListingsService(by_url=_listing(market_id=3))
    service = CreateUnderwritingFromUrlService(
        FakeZillowPropertyService(result=_zillow_property()),
        FakeSaveService(),
        FakeUnderwritingReader(existing=SimpleNamespace(id=77)),
        listings_service=listings,
    )

    with pytest.raises(UnderwritingAlreadyExistsError):
        await service.create(url=REQUEST_URL, market_id=5)

    assert listings.requested_url is None


@pytest.mark.asyncio
async def test_a_url_miss_falls_through_to_the_post_fetch_guard():
    """The pasted URL rarely matches detail_url; the zpid check is the backstop."""
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    save_service = FakeSaveService()
    listings = FakeListingsService(listing=_listing(market_id=3), by_url=None)
    service = CreateUnderwritingFromUrlService(
        zillow_service,
        save_service,
        FakeUnderwritingReader(existing=None),
        listings_service=listings,
    )

    with pytest.raises(ListingMarketMismatchError) as exc:
        await service.create(url=REQUEST_URL, market_id=5)

    # the URL lookup missed, so this one cost the fetch
    assert listings.requested_url == REQUEST_URL
    assert zillow_service.called_url == REQUEST_URL
    assert exc.value.listing_market_id == 3
    assert save_service.saved_payload is None


@pytest.mark.asyncio
async def test_a_matching_market_on_the_url_lookup_proceeds_to_the_fetch():
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    save_service = FakeSaveService()
    service = CreateUnderwritingFromUrlService(
        zillow_service,
        save_service,
        FakeUnderwritingReader(existing=None),
        listings_service=FakeListingsService(
            listing=_listing(market_id=3), by_url=_listing(market_id=3)
        ),
    )

    await service.create(url=REQUEST_URL, market_id=3)

    assert zillow_service.called_url == REQUEST_URL
    assert save_service.saved_payload.zpid == "26110417"


@pytest.mark.asyncio
async def test_pre_fetch_guard_rejects_a_null_market_too():
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    service = CreateUnderwritingFromUrlService(
        zillow_service,
        FakeSaveService(),
        FakeUnderwritingReader(existing=None),
        listings_service=FakeListingsService(by_url=_listing(market_id=3)),
    )

    with pytest.raises(ListingMarketMismatchError) as exc:
        await service.create(url=REQUEST_URL)

    assert exc.value.requested_market_id is None
    assert zillow_service.called_url is None


@pytest.mark.asyncio
async def test_pre_fetch_guard_allows_an_exploratory_listing():
    zillow_service = FakeZillowPropertyService(result=_zillow_property())
    save_service = FakeSaveService()
    service = CreateUnderwritingFromUrlService(
        zillow_service,
        save_service,
        FakeUnderwritingReader(existing=None),
        listings_service=FakeListingsService(
            listing=_listing(market_id=None), by_url=_listing(market_id=None)
        ),
    )

    await service.create(url=REQUEST_URL, market_id=5)

    assert zillow_service.called_url == REQUEST_URL
    assert save_service.saved_payload.zpid == "26110417"
