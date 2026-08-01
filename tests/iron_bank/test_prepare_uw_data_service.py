from decimal import Decimal
from types import SimpleNamespace

from app.iron_bank.schemas.prepare_uw import PrepareUwDataResult
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService


class FakeSchema(SimpleNamespace):
    def model_dump(self):
        return dict(vars(self))


def _listing():
    return SimpleNamespace(
        zpid="12345",
        detail_url="https://zillow.com/homes/12345",
        img_src="https://photos.zillow.com/12345.jpg",
        price=485000,
        unformatted_price=None,
        address="123 Pine Ridge Rd",
        address_street="123 Pine Ridge Rd",
        address_city="Gatlinburg",
        address_state="TN",
        beds=4,
        baths=3,
        area=1800,
    )


def _opex_by_bedrooms():
    return FakeSchema(
        id=1,
        market_id=3,
        market_slug="smoky-mountains",
        bedrooms=4,
        sqft=None,
        cleaning_fee=275,
        num_of_turns=38,
        pool_hot_tub_low=1200,
        pool_hot_tub_high=2400,
        furnishings_low=25000,
        furnishings_mid=None,
        furnishings_high=60000,
        consolidated_shipping=18225,
        property_taxes=0.012,
        internet=100,
    )


def _opex_by_size():
    return FakeSchema(
        id=7,
        market_id=3,
        market_slug="smoky-mountains",
        bedrooms=None,
        sqft=2000,
        land_value=0.2,
        appreciation=0.045,
        utilities=350,
    )


class TestNormalizeSqft:
    def test_returns_none_for_none(self):
        assert PrepareUwDataService().normalize_sqft(None) is None

    def test_rounds_up_to_nearest_checkpoint(self):
        assert PrepareUwDataService().normalize_sqft(800) == 1000
        assert PrepareUwDataService().normalize_sqft(1000) == 1000
        assert PrepareUwDataService().normalize_sqft(1001) == 1500
        assert PrepareUwDataService().normalize_sqft(2700) == 2750

    def test_caps_at_largest_checkpoint(self):
        assert PrepareUwDataService().normalize_sqft(9000) == 4500


class TestPrepare:
    def _prepare(self, **overrides):
        kwargs = dict(
            listing=_listing(),
            listing_details=SimpleNamespace(
                original_photos=["a.jpg"],
                lot_size_sqft=21780,
                description="Cabin in the woods.",
            ),
            market=SimpleNamespace(
                market_name="Smoky Mountains",
                market_slug="smoky-mountains",
                must_have_amenities=[SimpleNamespace(id=1, amenity_name="Hot Tub")],
            ),
            market_id=3,
            opex_by_bedrooms=_opex_by_bedrooms(),
            opex_by_size=_opex_by_size(),
            construction_amenities=[
                FakeSchema(
                    amenity_name="Hot Tub",
                    id=1,
                    location=None,
                    notes=None,
                    price_tier_1=8000,
                    price_tier_2=None,
                    price_tier_3=15000,
                )
            ],
            construction_remodeling=[FakeSchema(id=1, category="Flooring")],
            fred=SimpleNamespace(value=6.5, date="2026-06-01"),
        )
        kwargs.update(overrides)
        return PrepareUwDataService().prepare(**kwargs)

    def test_assembles_market_fields(self):
        prepared = self._prepare()
        assert isinstance(prepared, PrepareUwDataResult)
        result = prepared.model_dump()
        assert result["market_name"] == "Smoky Mountains"
        assert result["market_id"] == 3
        assert result["market_slug"] == "smoky-mountains"

    def test_transforms_zillow_property(self):
        result = self._prepare().model_dump()
        assert result["zillow_property"] == {
            "id": "12345",
            "url": "https://zillow.com/homes/12345",
            "thumbnail": "https://photos.zillow.com/12345.jpg",
            "price": 485000,
            "address": "123 Pine Ridge Rd",
            "bedrooms": 4,
            "bathrooms": 3,
            "area": 1800,
            "original_photos": ["a.jpg"],
            "lot_size_sqft": 21780,
            "description": "Cabin in the woods.",
        }

    def test_prefers_unformatted_price_when_available(self):
        listing = _listing()
        listing.price = 0
        listing.unformatted_price = "485000"

        result = self._prepare(listing=listing).model_dump()

        assert result["zillow_property"]["price"] == 485000

    def test_splits_opex_into_cleaning_ranged_absolute(self):
        opex = self._prepare().model_dump()["opex"]
        assert opex["cleaning"] == {"fee": 275, "num_of_turns": 38}
        assert opex["ranged"] == {"pool_hot_tub": {"low": 1200, "high": 2400}}
        assert opex["absolute"] == {"internet": 100, "utilities": 350}

    def test_surfaces_property_taxes_as_pct_not_absolute(self):
        opex = self._prepare().model_dump()["opex"]

        assert "property_taxes" not in opex["absolute"]
        assert opex["property_tax_pct"] == Decimal("0.012")

    def test_property_tax_pct_is_none_without_opex_by_bedrooms(self):
        opex = self._prepare(opex_by_bedrooms=None).model_dump()["opex"]

        assert opex["property_tax_pct"] is None

    def test_moves_land_value_and_appreciation_from_opex_to_config(self):
        result = self._prepare().model_dump()

        assert "land_value" not in result["opex"]["absolute"]
        assert "appreciation" not in result["opex"]["absolute"]
        assert result["config"]["land_assumptions"] == 0.2
        assert result["config"]["annual_re_appreciation_pct"] == 0.045

    def test_prepends_furnishings_amenity_from_opex(self):
        amenities = self._prepare().model_dump()["construction_amenities"]
        assert amenities[0] == {
            "amenity_name": "Furnishings",
            "id": 0,
            "location": None,
            "notes": None,
            "price_tier_1": 25000,
            "price_tier_2": None,
            "price_tier_3": 60000,
        }
        assert amenities[3]["amenity_name"] == "Hot Tub"

    def test_prepends_consolidated_shipping_amenity_from_opex(self):
        amenities = self._prepare().model_dump()["construction_amenities"]
        assert amenities[1] == {
            "amenity_name": "Consolidated Shipping",
            "id": -1,
            "location": None,
            "notes": None,
            "price_tier_1": 18225,
            "price_tier_2": 18225,
            "price_tier_3": 18225,
        }

    def test_surfaces_market_must_have_amenity_ids(self):
        result = self._prepare().model_dump()
        assert result["must_have_amenity_ids"] == [1]

    def test_must_have_amenity_ids_empty_without_market(self):
        result = self._prepare(market=None, market_id=None).model_dump()
        assert result["must_have_amenity_ids"] == []

    def test_must_have_amenity_ids_empty_when_market_has_none(self):
        market = SimpleNamespace(
            market_name="Smoky Mountains",
            market_slug="smoky-mountains",
            must_have_amenities=None,
        )
        result = self._prepare(market=market).model_dump()
        assert result["must_have_amenity_ids"] == []

    def test_consolidated_shipping_is_not_an_absolute_opex(self):
        opex = self._prepare().model_dump()["opex"]
        assert "consolidated_shipping" not in opex["absolute"]

    def test_config_includes_fred_rate_as_fraction(self):
        config = self._prepare().model_dump()["config"]
        assert config["fred"] == {"value": 0.065, "date": "2026-06-01"}

    def test_interest_rate_is_fred_rate_plus_spread(self):
        config = self._prepare().model_dump()["config"]
        # fred 6.5% -> 0.065 + 0.0035 spread
        assert config["interest_rate"] == 0.0685

    def test_interest_rate_falls_back_to_default_without_fred(self):
        config = self._prepare(fred=None).model_dump()["config"]
        assert config["interest_rate"] == 0.0688

    def test_handles_all_optional_inputs_missing(self):
        result = self._prepare(
            listing_details=None,
            market=None,
            market_id=None,
            opex_by_bedrooms=None,
            opex_by_size=None,
            fred=None,
        ).model_dump()
        assert result["market_name"] is None
        assert result["market_id"] is None
        assert result["market_slug"] is None
        assert result["zillow_property"]["original_photos"] is None
        assert result["zillow_property"]["lot_size_sqft"] is None
        assert result["opex"]["cleaning"] == {"fee": None, "num_of_turns": None}
        assert result["opex"]["absolute"] == {}
        assert result["construction_amenities"][0]["price_tier_1"] is None
        assert result["config"]["fred"] == {"value": 0.065, "date": "2024-06-01"}


class TestToTemplateMarketContext:
    """Market-less non-automated deals: keep every row, zero every amount."""

    def _context(self, **overrides):
        kwargs = dict(
            market=SimpleNamespace(
                market_name="Smoky Mountains",
                market_slug="smoky-mountains",
                must_have_amenities=[SimpleNamespace(id=1, amenity_name="Hot Tub")],
            ),
            market_id=1,
            opex_by_bedrooms=_opex_by_bedrooms(),
            opex_by_size=_opex_by_size(),
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
            fred=SimpleNamespace(value=6.5, date="2026-06-01"),
            str_cribs_fee=SimpleNamespace(fee=9500),
        )
        kwargs.update(overrides)
        return PrepareUwDataService().prepare_market_context(**kwargs)

    def _template(self, **overrides):
        return PrepareUwDataService.to_template_market_context(self._context(**overrides))

    def test_clears_market_identity_so_the_deal_is_market_less(self):
        template = self._template()
        assert template.market_id is None
        assert template.market_name is None
        assert template.market_slug is None

    def test_zeroes_every_opex_amount_but_keeps_the_rows(self):
        source = self._context()
        template = self._template()

        # same keys as the real market, so every row still renders for the analyst
        assert set(template.opex.absolute) == set(source.opex.absolute)
        assert source.opex.absolute["internet"] == Decimal("100")
        assert all(value == Decimal("0") for value in template.opex.absolute.values())

        assert template.opex.cleaning.fee == Decimal("0")
        assert template.opex.cleaning.num_of_turns == Decimal("0")
        assert template.opex.ranged.pool_hot_tub.low == Decimal("0")
        assert template.opex.ranged.pool_hot_tub.high == Decimal("0")
        assert template.opex.property_tax_pct == Decimal("0")

    def test_zeroes_only_the_three_seeded_amenity_options(self):
        template = self._template()
        by_id = {option.id: option for option in template.construction_amenities}

        for option_id in PrepareUwDataService.SEEDED_AMENITY_OPTION_IDS:
            option = by_id[option_id]
            assert option.price_tier_1 == Decimal("0")
            assert option.price_tier_2 == Decimal("0")
            assert option.price_tier_3 == Decimal("0")
        # names survive — only the prices are stripped
        assert by_id[PrepareUwDataService.FURNISHINGS_OPTION_ID].amenity_name == (
            "Furnishings"
        )
        assert by_id[
            PrepareUwDataService.STR_CRIBS_PROJECT_MANAGEMENT_OPTION_ID
        ].amenity_name == "STR Cribs - Project Management"

        # the rest of the catalog is the analyst's picklist, left untouched
        assert by_id[1].price_tier_2 == Decimal("12000")

    def test_drops_must_have_amenities(self):
        assert self._context().must_have_amenity_ids == [1]
        assert self._template().must_have_amenity_ids == []

    def test_reverts_market_derived_config_but_keeps_the_live_fred_rate(self):
        source = self._context()
        template = self._template()

        # market 1's land/appreciation assumptions must not leak into a
        # market-less template
        assert source.config.land_assumptions == 0.2
        assert source.config.annual_re_appreciation_pct == 0.045
        assert template.config.annual_re_appreciation_pct == 0.04
        # FRED and the rate derived from it are not market-specific
        assert template.config.fred.value == 0.065
        assert template.config.interest_rate == source.config.interest_rate

    def test_does_not_mutate_the_source_context(self):
        source = self._context()
        PrepareUwDataService.to_template_market_context(source)

        assert source.market_id == 1
        assert source.opex.cleaning.fee == Decimal("275")
        assert source.must_have_amenity_ids == [1]
