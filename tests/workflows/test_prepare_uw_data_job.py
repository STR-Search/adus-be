from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.iron_bank.services import opex_catalog
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
from app.markets.schemas.opex import OpexByBedroomsSchema
from app.workflows.prepare_uw_data_job import (
    BedroomContextNotFoundError,
    PrepareUwDataJob,
)


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


class FakeStrCribsService:
    def __init__(self, fee=None):
        self.fee = fee
        self.requested_area = None

    async def get_by_area(self, area):
        self.requested_area = area
        return self.fee


class FakeExternalApiService:
    def __init__(self, fred=None):
        self.fred = fred

    async def get_30y_fixed_rate(self):
        return self.fred


class RecordingUwDataService:
    TEMPLATE_MARKET_ID = 1

    def __init__(self):
        self.received = None
        self.received_context_kwargs = None
        self.templated = None

    def normalize_sqft(self, area):
        return 2000 if area is not None else None

    def prepare(self, **kwargs):
        self.received = kwargs
        return {"prepared": True}

    def prepare_market_context(self, **kwargs):
        self.received_context_kwargs = kwargs
        return {"context": True}

    def to_template_market_context(self, context):
        self.templated = context
        return {"context": True, "template": True}


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
        str_cribs_service=FakeStrCribsService(),
        external_api_service=FakeExternalApiService(),
        uw_data_service=uw_service or RecordingUwDataService(),
        underwriting_repository=FakeUnderwritingRepository(_underwriting()),
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


class TestBuildMarketContext:
    """The non-automated create-from-URL flow's entry point: no listing, the
    market comes from the caller."""

    @pytest.mark.asyncio
    async def test_fetches_market_data_for_the_given_market_and_property_size(self):
        uw_service = RecordingUwDataService()
        market = SimpleNamespace(market_name="Smokies", market_slug="smokies")
        job, deps = _job(listing=None, market=market, uw_service=uw_service)

        context = await job.build_market_context(market_id=3, bedrooms=5, area=1800)

        assert context == {"context": True}
        assert deps["market_service"].requested_id == 3
        assert deps["opex_by_bedrooms_service"].called_with == {
            "bedrooms": 5,
            "market_id": 3,
        }
        assert deps["opex_by_size_service"].called_with == {
            "sqft": 2000,
            "market_id": 3,
        }
        assert deps["str_cribs_service"].requested_area == 1800
        assert uw_service.received_context_kwargs["market"] is market
        assert uw_service.received_context_kwargs["market_id"] == 3
        # no market_id was missing, so no template transform
        assert uw_service.templated is None

    @pytest.mark.asyncio
    async def test_falls_back_to_the_template_market_when_market_id_is_none(self):
        uw_service = RecordingUwDataService()
        job, deps = _job(listing=None, uw_service=uw_service)

        context = await job.build_market_context(market_id=None, bedrooms=5, area=1800)

        # the shape is loaded from the template market...
        assert deps["market_service"].requested_id == 1
        assert deps["opex_by_bedrooms_service"].called_with == {
            "bedrooms": 5,
            "market_id": 1,
        }
        assert deps["opex_by_size_service"].called_with == {
            "sqft": 2000,
            "market_id": 1,
        }
        # ...then zeroed out before it is handed back
        assert uw_service.templated == {"context": True}
        assert context == {"context": True, "template": True}

    @pytest.mark.asyncio
    async def test_skips_the_str_cribs_lookup_without_an_area(self):
        job, deps = _job(listing=None)

        await job.build_market_context(market_id=3, bedrooms=None, area=None)

        assert deps["str_cribs_service"].requested_area is None
        assert deps["opex_by_size_service"].called_with == {
            "sqft": None,
            "market_id": 3,
        }


def test_from_session_wires_real_services():
    job = PrepareUwDataJob.from_session(db=object())

    from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
    from app.zillow.services.scheduled_listings_service import ScheduledListingsService

    assert isinstance(job.uw_data_service, PrepareUwDataService)
    assert isinstance(job.listings_service, ScheduledListingsService)


# --- build_bedroom_context ---------------------------------------------------
#
# The post-creation counterpart to build_market_context: re-seeds the values an
# analyst's bedroom change invalidates. Unlike the tests above these run against
# the real PrepareUwDataService, since the assembly they verify (which opex
# columns land where, which amenity options are priced) lives inside it.


def _opex_row(**overrides):
    values = dict(
        id=7,
        market_id=3,
        bedrooms=5,
        cleaning_fee=Decimal("180"),
        num_of_turns=Decimal("6"),
        property_taxes=Decimal("0.0125"),
        pool_hot_tub_low=Decimal("150"),
        pool_hot_tub_high=Decimal("300"),
        outdoor_landscaping=Decimal("120"),
        software=Decimal("40"),
        insurance_hoi=Decimal("210"),
        supplies=Decimal("75"),
        capex_reserve=Decimal("300"),
        hoa_fees=Decimal("0"),
        furnishings_low=Decimal("30000"),
        furnishings_mid=Decimal("45000"),
        furnishings_high=Decimal("60000"),
        consolidated_shipping=Decimal("5000"),
        land_value=Decimal("0.22"),
        appreciation=Decimal("0.045"),
    )
    values.update(overrides)
    return OpexByBedroomsSchema.model_validate(values)


_UNSET = object()


class FakeUnderwritingRepository:
    def __init__(self, underwriting):
        self.underwriting = underwriting
        self.requested_id = None

    async def get_by_id(self, underwriting_id):
        self.requested_id = underwriting_id
        return self.underwriting


def _expense(expense_id, expense_name, monthly_amount=Decimal("0")):
    return SimpleNamespace(
        id=expense_id, expense_name=expense_name, monthly_amount=monthly_amount
    )


def _ledger():
    """The deal's own expense rows, as the repository eager-loads them.

    Deliberately imperfect: "Internet" is size-keyed so no bedroom change should
    ever touch it, and "Software" is missing entirely — the analyst deleted that
    row, which is the case that has to come back as an insert rather than being
    silently skipped.
    """
    return [
        _expense(8801, "Internet", Decimal("100")),
        _expense(8804, "Pool/Hot Tub Maintenance", Decimal("125")),
        _expense(8805, "Outdoor/Landscaping", Decimal("100")),
        _expense(8807, "Household Supplies", Decimal("150")),
        _expense(8808, "Cleaning", Decimal("900")),
        _expense(8809, "Property Taxes (Monthly)", Decimal("400")),
        _expense(8810, "Insurance HOI", Decimal("200")),
        _expense(8811, "CapEx Reserve", Decimal("275")),
        _expense(8813, "HOA Fees", Decimal("0")),
    ]


def _underwriting(**overrides):
    base = {
        "id": 42,
        "market_id": 3,
        "purchase_price": Decimal("480000"),
        "detail": None,
        "operating_expenses": _ledger(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _bedroom_context_job(opex_row, underwriting=_UNSET):
    return _job(
        listing=_listing(),
        uw_service=PrepareUwDataService(),
        opex_by_bedrooms_service=FakeOpexByBedroomsService(opex_row),
        underwriting_repository=FakeUnderwritingRepository(
            _underwriting() if underwriting is _UNSET else underwriting
        ),
    )


@pytest.mark.asyncio
async def test_bedroom_context_keys_the_opex_lookup_on_the_requested_bedrooms():
    job, deps = _bedroom_context_job(_opex_row())

    context = await job.build_bedroom_context(
        underwriting_id=42, bedrooms=5
    )

    assert deps["opex_by_bedrooms_service"].called_with == {
        "bedrooms": 5,
        "market_id": 3,
    }
    assert context.bedrooms == 5
    by_name = {u.expense_name: u.monthly_amount for u in context.operating_expenses}
    assert by_name["Cleaning"] == Decimal("1080")  # 180 x 6 turns
    assert by_name["Pool/Hot Tub Maintenance"] == Decimal("150")  # the low end
    assert by_name["Property Taxes (Monthly)"] == Decimal("500.00")  # 0.0125 x 480k / 12
    assert context.land_assumptions_pct == Decimal("0.22")
    assert context.annual_re_appreciation_pct == Decimal("0.045")


@pytest.mark.asyncio
async def test_bedroom_context_updates_exclude_sqft_keyed_rows():
    # opex_by_size is never looked up: it is keyed on sqft, so a bedroom change
    # leaves internet/pest_control/utilities alone and they must not appear here
    # for the FE to overwrite. MISC is excluded too — no market supplies it.
    job, deps = _bedroom_context_job(_opex_row())

    context = await job.build_bedroom_context(
        underwriting_id=42, bedrooms=5
    )

    # In OPEX_ROWS order, which is the catalog's order.
    assert [u.expense_name for u in context.operating_expenses] == [
        "Pool/Hot Tub Maintenance",
        "Outdoor/Landscaping",
        "Software",
        "Household Supplies",
        "Cleaning",
        "Property Taxes (Monthly)",
        "Insurance HOI",
        "CapEx Reserve",
        "HOA Fees",
    ]
    assert deps["opex_by_size_service"].called_with is None
    assert deps["str_cribs_service"].requested_area is None


@pytest.mark.asyncio
async def test_bedroom_context_updates_carry_the_underwritings_own_row_ids():
    # The client patches by id rather than matching labels itself, so the ids
    # must be the ledger's — and a row the deal no longer has must come back as
    # an insert, not vanish.
    job, _ = _bedroom_context_job(_opex_row())

    context = await job.build_bedroom_context(underwriting_id=42, bedrooms=5)

    by_name = {u.expense_name: u.id for u in context.operating_expenses}
    assert by_name["Cleaning"] == 8808
    assert by_name["HOA Fees"] == 8813
    # deleted from this deal — id=None tells the client to insert it, which
    # _upsert_children already handles
    assert by_name["Software"] is None
    # size-keyed, so it is not in the patch at all and keeps its stored value
    assert "Internet" not in by_name


@pytest.mark.asyncio
async def test_bedroom_context_returns_only_the_two_bedroom_keyed_options():
    job, _ = _bedroom_context_job(_opex_row())

    context = await job.build_bedroom_context(
        underwriting_id=42, bedrooms=5
    )

    by_id = {option.id: option for option in context.construction_amenities}
    # "Design / Project Management" (-2) is priced from str_cribs_fee, keyed on
    # area, so it does not move with bedrooms and is excluded.
    assert set(by_id) == {
        PrepareUwDataService.FURNISHINGS_OPTION_ID,
        PrepareUwDataService.CONSOLIDATED_SHIPPING_OPTION_ID,
    }

    furnishings = by_id[PrepareUwDataService.FURNISHINGS_OPTION_ID]
    # All three tiers, so a re-tiered analyst choice is honoured rather than
    # forced back to Mid.
    assert furnishings.price_tier_1 == Decimal("30000")
    assert furnishings.price_tier_2 == Decimal("45000")
    assert furnishings.price_tier_3 == Decimal("60000")

    shipping = by_id[PrepareUwDataService.CONSOLIDATED_SHIPPING_OPTION_ID]
    assert shipping.price_tier_2 == Decimal("5000")


@pytest.mark.asyncio
async def test_bedroom_context_blobs_match_what_creation_would_persist():
    # The whole reason these are derived server-side: the FE places them
    # straight onto uw_details, so they must be identical to the catalog's
    # output for the same inputs — the same functions the payload builders use.
    job, _ = _bedroom_context_job(_opex_row())
    purchase_price = Decimal("480000")

    context = await job.build_bedroom_context(
        underwriting_id=42, bedrooms=5
    )

    assert context.cleaning_cost == opex_catalog.build_cleaning_cost(
        {"fee": Decimal("180"), "num_of_turns": Decimal("6")}
    )
    assert context.property_taxes == opex_catalog.build_opex_property_taxes(
        property_tax_pct=Decimal("0.0125"), purchase_price=purchase_price
    )
    assert context.cleaning_cost["monthly_cleaning_cost"] == Decimal("1080")
    assert context.property_taxes["annual_amount"] == Decimal("6000.0000")


@pytest.mark.asyncio
async def test_bedroom_context_raises_when_the_market_has_no_row_at_that_count():
    # Markets do not cover every bedroom count. Returning an all-null context
    # would let the FE place blanks over the analyst's existing numbers, so the
    # caller turns this into a 404 instead.
    job, _ = _bedroom_context_job(None)

    with pytest.raises(
        BedroomContextNotFoundError, match="No opex data for market 3 at 7 bedrooms"
    ):
        await job.build_bedroom_context(
            underwriting_id=42, bedrooms=7
        )


@pytest.mark.asyncio
async def test_bedroom_context_reads_market_and_price_off_the_underwriting():
    # Neither is accepted from the caller, so the property-tax blob can never be
    # computed against a price the client was holding stale.
    job, deps = _bedroom_context_job(
        _opex_row(),
        underwriting=_underwriting(market_id=9, purchase_price=Decimal("600000")),
    )

    context = await job.build_bedroom_context(underwriting_id=42, bedrooms=5)

    assert deps["underwriting_repository"].requested_id == 42
    assert deps["opex_by_bedrooms_service"].called_with == {
        "bedrooms": 5,
        "market_id": 9,
    }
    # 0.0125 * 600000, not the 480000 the default fixture carries
    assert context.property_taxes["annual_amount"] == Decimal("7500.0000")


@pytest.mark.asyncio
async def test_bedroom_context_falls_back_to_the_purchase_details_blob():
    # The top-level column is promoted from purchase_details on save/update, so
    # it is normally set; the blob covers rows where that promotion never ran.
    job, _ = _bedroom_context_job(
        _opex_row(),
        underwriting=_underwriting(
            purchase_price=None,
            detail=SimpleNamespace(purchase_details={"purchase_price": 400000}),
        ),
    )

    context = await job.build_bedroom_context(underwriting_id=42, bedrooms=5)

    assert context.property_taxes["annual_amount"] == Decimal("5000.0000")


@pytest.mark.asyncio
async def test_bedroom_context_still_returns_opex_without_a_purchase_price():
    # A deal with no price yet is legitimate: the tax blob is null but the
    # opex and furnishing values are still worth re-seeding.
    job, _ = _bedroom_context_job(
        _opex_row(), underwriting=_underwriting(purchase_price=None)
    )

    context = await job.build_bedroom_context(underwriting_id=42, bedrooms=5)

    assert context.property_taxes is None
    by_name = {u.expense_name: u.monthly_amount for u in context.operating_expenses}
    assert by_name["Cleaning"] == Decimal("1080")
    # No price means no tax amount to apply, so the row is left out rather than
    # patched to null over a figure the analyst can see.
    assert "Property Taxes (Monthly)" not in by_name
    assert context.land_assumptions_pct == Decimal("0.22")


@pytest.mark.asyncio
async def test_bedroom_context_raises_when_the_underwriting_does_not_exist():
    job, _ = _bedroom_context_job(_opex_row(), underwriting=None)

    with pytest.raises(BedroomContextNotFoundError, match="Underwriting 42 not found"):
        await job.build_bedroom_context(underwriting_id=42, bedrooms=5)


@pytest.mark.asyncio
async def test_bedroom_context_raises_for_a_market_less_deal():
    # A template deal has no market figures to re-seed from.
    job, deps = _bedroom_context_job(
        _opex_row(), underwriting=_underwriting(market_id=None)
    )

    with pytest.raises(BedroomContextNotFoundError, match="has no market"):
        await job.build_bedroom_context(underwriting_id=42, bedrooms=5)

    # bailed before touching the opex table
    assert deps["opex_by_bedrooms_service"].called_with is None
