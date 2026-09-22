"""The blank create path: POST /iron-bank/underwritings/blank.

Covers the builder's blank entry point and the thin service above it. The four
input combinations (market and/or bedrooms) are asserted together in
``test_every_input_combination_seeds_the_canonical_opex_rows`` and then
individually, because what a sparsely-specified blank deal seeds is the whole
reason the endpoint's contract looks the way it does.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.router import get_create_blank_underwriting_controller, router
from app.iron_bank.schemas.create_blank_underwriting import (
    CreateBlankUnderwritingPayload,
)
from app.iron_bank.services import opex_catalog
from app.iron_bank.services.create_blank_underwriting_service import (
    CreateBlankUnderwritingService,
)
from app.iron_bank.services.non_automated_underwriting_payload_builder import (
    NonAutomatedUnderwritingPayloadBuilder,
)
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService

PURCHASE_PRICE = Decimal("389000")
FRED_VALUE = 6.5


class FakeSchema(SimpleNamespace):
    def model_dump(self):
        return dict(vars(self))


def _opex_by_bedrooms(market_id=3):
    return FakeSchema(
        id=1,
        market_id=market_id,
        market_slug="smoky-mountains",
        bedrooms=5,
        sqft=None,
        cleaning_fee=275,
        num_of_turns=38,
        pool_hot_tub_low=1200,
        pool_hot_tub_high=2400,
        pool_and_hot_tub=3000,
        furnishings_low=25000,
        furnishings_mid=40000,
        furnishings_high=60000,
        consolidated_shipping=18225,
        property_taxes=Decimal("0.012"),
        # land_value and appreciation live on the bedrooms row, not by size
        land_value=0.25,
        appreciation=0.045,
    )


def _market_context(*, market_id=3, bedrooms=True):
    """A realistic MarketContext, assembled the way production does.

    ``bedrooms=False`` drops the ``(market_id, bedrooms)`` opex row, which is
    exactly what the lookup returns when the analyst supplies no bedroom count.
    ``area`` is always unknown on this path, so the sqft-keyed row is never
    resolved and ``opex_by_size`` is always None.
    """
    return PrepareUwDataService().prepare_market_context(
        market=SimpleNamespace(
            market_name="Smoky Mountains",
            market_slug="smoky-mountains",
            analyst_owner_id=7,
            must_have_amenities=[SimpleNamespace(id=1, amenity_name="Hot Tub")],
        ),
        market_id=market_id,
        opex_by_bedrooms=_opex_by_bedrooms(market_id) if bedrooms else None,
        opex_by_size=None,
        construction_amenities=[
            FakeSchema(
                amenity_name="Hot Tub",
                id=1,
                location=None,
                notes=None,
                price_tier_1=8000,
                price_tier_2=12000,
                price_tier_3=15000,
            )
        ],
        construction_remodeling=[FakeSchema(id=1, category="Flooring")],
        fred=SimpleNamespace(value=FRED_VALUE, date="2026-06-01"),
        str_cribs_fee=SimpleNamespace(fee=9500),
    )


def _template_context(*, bedrooms=True):
    """What the job returns when no market was picked: a zeroed real context."""
    return PrepareUwDataService.to_template_market_context(
        _market_context(
            market_id=PrepareUwDataService.TEMPLATE_MARKET_ID, bedrooms=bedrooms
        )
    )


def _context_for(*, market: bool, bedrooms: bool):
    return (
        _market_context(bedrooms=bedrooms)
        if market
        else _template_context(bedrooms=bedrooms)
    )


def _build(*, market=True, bedrooms=5, bathrooms=Decimal("4.0"), current_user_id=42):
    return NonAutomatedUnderwritingPayloadBuilder().build_blank(
        purchase_price=PURCHASE_PRICE,
        market_context=_context_for(market=market, bedrooms=bedrooms is not None),
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        current_user_id=current_user_id,
    )


def _amounts(payload):
    return {row.expense_name: row.monthly_amount for row in payload.operating_expenses}


class FakeMarketContextReader:
    """Stands in for PrepareUwDataJob, which satisfies the reader protocol."""

    def __init__(self, context):
        self.context = context
        self.called_with = None

    async def build_market_context(self, *, market_id, bedrooms, area):
        self.called_with = {
            "market_id": market_id,
            "bedrooms": bedrooms,
            "area": area,
        }
        return self.context


class FakeSaveService:
    def __init__(self):
        self.saved_payload = None

    async def save(self, payload):
        self.saved_payload = payload
        return SimpleNamespace(underwriting_id=501)


class FakeUnderwritingRepository:
    def __init__(self):
        self.underwriting_data = None

    async def create(self, **kwargs):
        self.underwriting_data = kwargs["underwriting_data"]
        return SimpleNamespace(id=501)


# --------------------------------------------------------------------------
# Core shape
# --------------------------------------------------------------------------


def test_build_blank_sets_non_automated_core_fields():
    payload = _build()

    assert payload.source == UnderwritingSource.BLANK
    assert payload.is_automated is False
    assert payload.deal_status == DealStatus.TEMPLATE_GENERATED
    assert payload.purchase_price == PURCHASE_PRICE
    assert payload.bedrooms == 5
    assert payload.bathrooms == Decimal("4.0")
    assert payload.market_id == 3


def test_build_blank_leaves_every_listing_derived_column_null():
    """There is no listing, so nothing that describes one may be invented."""
    payload = _build()

    assert payload.listing_url is None
    assert payload.zpid is None
    assert payload.property_address is None
    assert payload.street is None
    assert payload.city is None
    assert payload.state is None


def test_build_blank_seeds_the_full_zillow_property_shape():
    payload = _build()

    stored = payload.details.zillow_property
    # what the analyst typed, mirrored into the blob
    assert stored.price == PURCHASE_PRICE
    assert stored.bedrooms == 5
    assert stored.bathrooms == Decimal("4.0")
    # every other key present and null, so the hero has a stable write target
    assert stored.id is None
    assert stored.url is None
    assert stored.thumbnail is None
    assert stored.address is None
    assert stored.area is None
    assert stored.original_photos is None
    assert stored.lot_size_sqft is None
    assert stored.description is None
    assert stored.lot_size_acres is None


def test_build_blank_mirrors_missing_bed_and_bath_as_nulls():
    payload = _build(bedrooms=None, bathrooms=None)

    assert payload.bedrooms is None
    assert payload.bathrooms is None
    assert payload.details.zillow_property.bedrooms is None
    assert payload.details.zillow_property.bathrooms is None


def test_build_blank_owner_falls_back_to_the_requesting_user():
    """A market-less deal has no analyst owner to inherit."""
    payload = _build(market=False, current_user_id=42)

    assert payload.owner_id == 42


def test_build_blank_prefers_the_markets_analyst_owner():
    payload = _build(market=True, current_user_id=42)

    assert payload.owner_id == 7


def test_build_blank_market_less_deal_has_no_market_id():
    payload = _build(market=False)

    assert payload.market_id is None


# --------------------------------------------------------------------------
# Financing and taxes — the reason purchase_price is mandatory
# --------------------------------------------------------------------------


@pytest.mark.parametrize("market", [True, False])
@pytest.mark.parametrize("bedrooms", [5, None])
def test_purchase_details_and_taxes_always_seed(market, bedrooms):
    payload = _build(market=market, bedrooms=bedrooms)

    purchase_details = payload.details.purchase_details
    assert purchase_details is not None
    assert purchase_details.purchase_price == PURCHASE_PRICE
    # FRED-derived, not the 0.0688 default: this is what a missing price would
    # have thrown away, and the reason the endpoint demands one.
    assert purchase_details.interest_rate == Decimal(
        str(FRED_VALUE / 100 + PrepareUwDataService._INTEREST_RATE_SPREAD_OVER_FRED)
    )
    assert payload.taxes is not None
    assert payload.taxes.sla_multiplier_pct == Decimal("0.36")


def test_land_assumptions_follow_the_market_when_bedrooms_are_known():
    """land_value lives on the (market, bedrooms) opex row, so it needs both."""
    assert _build(market=True, bedrooms=5).taxes.land_assumptions_pct == Decimal("0.25")
    assert _build(market=True, bedrooms=None).taxes.land_assumptions_pct == Decimal(
        "0.2"
    )


# --------------------------------------------------------------------------
# Operating expenses across the four input combinations
# --------------------------------------------------------------------------


@pytest.mark.parametrize("market", [True, False])
@pytest.mark.parametrize("bedrooms", [5, None])
def test_every_input_combination_seeds_the_canonical_opex_rows(market, bedrooms):
    """A blank sheet is sparse, but it is never short of rows.

    Every ``OPEX_ROWS`` row is seeded in canonical order however little the
    analyst supplied — only the amounts differ. That is what makes a
    sparsely-seeded blank deal legible rather than misleading.
    """
    payload = _build(market=market, bedrooms=bedrooms)

    assert [row.expense_name for row in payload.operating_expenses] == [
        label for _, label in opex_catalog.OPEX_ROWS
    ]


@pytest.mark.parametrize("market", [True, False])
@pytest.mark.parametrize("bedrooms", [5, None])
def test_sqft_keyed_rows_are_blank_in_every_combination(market, bedrooms):
    """``area`` is unknown at create, so these three cannot resolve.

    Nothing backfills them either — ``bedroom-context`` excludes sqft-keyed
    rows by design. Accepting an optional ``area`` at create would close it.
    """
    amounts = _amounts(_build(market=market, bedrooms=bedrooms))

    assert amounts["Internet"] is None
    assert amounts["Utilities"] is None
    assert amounts["Pest Control"] is None


def test_market_and_bedrooms_seed_real_amounts():
    payload = _build(market=True, bedrooms=5)
    amounts = _amounts(payload)

    assert amounts["Cleaning"] == Decimal("275") * Decimal("38")
    assert amounts["Property Taxes (Monthly)"] == (
        PURCHASE_PRICE * Decimal("0.012") / Decimal("12")
    )
    assert payload.details.cleaning_cost is not None
    assert payload.details.property_taxes is not None


def test_market_without_bedrooms_loses_the_markets_own_figures():
    """The ``(market_id, bedrooms)`` lookup misses, so the opex row is gone.

    This is the combination the pending product decision is about: a deal that
    knows its market still comes through with null cleaning and tax blobs,
    recoverable only if the frontend merges everything
    ``GET /underwritings/{id}/bedroom-context`` returns.
    """
    payload = _build(market=True, bedrooms=None)

    assert payload.details.cleaning_cost is None
    assert payload.details.property_taxes is None
    assert _amounts(payload)["Cleaning"] is None


def test_market_less_deal_zeroes_rather_than_blanks():
    """The template pass zeroes its figures unconditionally.

    Which makes *no market, no bedrooms* better-shaped than *market, no
    bedrooms*: it populates both details blobs where the combination that knows
    more leaves them null.
    """
    payload = _build(market=False, bedrooms=None)

    assert payload.details.cleaning_cost is not None
    assert payload.details.property_taxes is not None
    assert _amounts(payload)["Cleaning"] == 0


def test_optimization_list_seeds_in_every_combination():
    for market in (True, False):
        for bedrooms in (5, None):
            payload = _build(market=market, bedrooms=bedrooms)
            assert payload.optimization_list, (market, bedrooms)


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_requests_context_without_an_area():
    reader = FakeMarketContextReader(_market_context())
    save_service = FakeSaveService()
    service = CreateBlankUnderwritingService(
        save_service=save_service, market_context_reader=reader
    )

    result = await service.create(
        purchase_price=PURCHASE_PRICE,
        market_id=3,
        bedrooms=5,
        bathrooms=Decimal("4.0"),
        current_user_id=42,
    )

    # area is never known at create — the sqft-keyed rows seed blank
    assert reader.called_with == {"market_id": 3, "bedrooms": 5, "area": None}
    assert result.underwriting_id == 501


@pytest.mark.asyncio
async def test_service_saves_a_blank_payload():
    save_service = FakeSaveService()
    service = CreateBlankUnderwritingService(
        save_service=save_service,
        market_context_reader=FakeMarketContextReader(_market_context()),
    )

    await service.create(purchase_price=PURCHASE_PRICE, market_id=3, bedrooms=5)

    payload = save_service.saved_payload
    assert payload.source == UnderwritingSource.BLANK
    assert payload.listing_url is None
    assert payload.purchase_price == PURCHASE_PRICE


# --------------------------------------------------------------------------
# Request schema
# --------------------------------------------------------------------------


def test_payload_folds_an_unselected_market_to_none():
    """Clients send 0 from an unselected dropdown; a real 0 would break the FK."""
    assert CreateBlankUnderwritingPayload(
        purchase_price=PURCHASE_PRICE, market_id=0
    ).market_id is None


def test_payload_requires_a_positive_purchase_price():
    with pytest.raises(ValueError):
        CreateBlankUnderwritingPayload(market_id=3)
    with pytest.raises(ValueError):
        CreateBlankUnderwritingPayload(purchase_price=0)


def test_payload_rejects_unknown_keys():
    """extra="forbid", so a stray key is a 422 rather than a silent no-op."""
    with pytest.raises(ValueError):
        CreateBlankUnderwritingPayload(
            purchase_price=PURCHASE_PRICE, property_address="123 Main St"
        )


# --------------------------------------------------------------------------
# Persistence — what the save service does with a blank payload
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_reaches_the_underwriting_row():
    """``source`` is on UnderwritingBase, so it rides through to the column."""
    repository = FakeUnderwritingRepository()
    payload = _build(market=False)

    await SaveUnderwritingService(repository).save(payload)

    assert repository.underwriting_data["source"] == UnderwritingSource.BLANK


@pytest.mark.asyncio
async def test_zillow_path_still_falls_through_to_the_source_default():
    """The from-URL payload must not start writing NULL over the "adus" default.

    ``build_blank`` stamps a source and ``build_from_zillow_property`` does not;
    since the save dumps with ``exclude_unset``, an explicit None on the Zillow
    path would persist NULL instead of letting the column default apply.
    """
    repository = FakeUnderwritingRepository()
    payload = NonAutomatedUnderwritingPayloadBuilder().build_from_zillow_property(
        listing_url="https://www.zillow.com/homedetails/26110417_zpid/",
        zillow_property={"id": "26110417", "price": 389000.0, "bedrooms": 5},
    )

    await SaveUnderwritingService(repository).save(payload)

    assert "source" not in repository.underwriting_data


@pytest.mark.asyncio
async def test_the_bedrooms_column_wins_over_a_diverged_blob():
    """Which is what lets the blob go stale safely.

    The blob is the property *as found*, the column is the property *as
    underwritten*. An analyst adding a bedroom moves the column and should not
    rewrite history in the blob, so nothing may read the blob back as
    authoritative once the column is set.
    """
    repository = FakeUnderwritingRepository()
    payload = _build(bedrooms=5)
    payload.bedrooms = 6  # the analyst's later edit, blob left at 5

    await SaveUnderwritingService(repository).save(payload)

    assert repository.underwriting_data["bedrooms"] == 6
    assert payload.details.zillow_property.bedrooms == 5


# --------------------------------------------------------------------------
# Route
# --------------------------------------------------------------------------


def _client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_create_blank_underwriting_controller] = (
        lambda: FakeController()
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=99)
    return TestClient(app)


class FakeController:
    received: dict = {}

    async def create_blank(self, **kwargs):
        FakeController.received = kwargs
        return {"underwriting_id": 501}


def test_route_passes_every_field_through_and_returns_201():
    response = _client().post(
        "/iron-bank/underwritings/blank",
        json={
            "purchase_price": 389000,
            "market_id": 3,
            "bedrooms": 5,
            "bathrooms": 4.0,
        },
    )

    assert response.status_code == 201
    assert response.json() == {"underwriting_id": 501}
    assert FakeController.received == {
        "purchase_price": Decimal("389000"),
        "market_id": 3,
        "bedrooms": 5,
        "bathrooms": Decimal("4.0"),
        "current_user_id": 99,
    }


def test_route_accepts_a_price_alone():
    response = _client().post(
        "/iron-bank/underwritings/blank", json={"purchase_price": 389000}
    )

    assert response.status_code == 201
    assert FakeController.received["market_id"] is None
    assert FakeController.received["bedrooms"] is None


def test_route_folds_an_unselected_market_before_the_controller_sees_it():
    _client().post(
        "/iron-bank/underwritings/blank",
        json={"purchase_price": 389000, "market_id": 0},
    )

    # a real 0 would violate the FK to markets.market_keys_master
    assert FakeController.received["market_id"] is None


def test_route_rejects_a_missing_purchase_price():
    response = _client().post("/iron-bank/underwritings/blank", json={"market_id": 3})

    assert response.status_code == 422
