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
                original_photos=["a.jpg"], lot_size_sqft=21780
            ),
            market=SimpleNamespace(
                market_name="Smoky Mountains", market_slug="smoky-mountains"
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
        assert amenities[2]["amenity_name"] == "Hot Tub"

    def test_prepends_consolidated_shipping_amenity_from_opex(self):
        amenities = self._prepare().model_dump()["construction_amenities"]
        assert amenities[1] == {
            "amenity_name": "Consolidated Shipping",
            "id": -1,
            "location": None,
            "notes": None,
            "price_tier_1": 18225,
            "price_tier_2": None,
            "price_tier_3": None,
        }

    def test_consolidated_shipping_is_not_an_absolute_opex(self):
        opex = self._prepare().model_dump()["opex"]
        assert "consolidated_shipping" not in opex["absolute"]

    def test_config_includes_fred_rate_as_fraction(self):
        config = self._prepare().model_dump()["config"]
        assert config["fred"] == {"value": 0.065, "date": "2026-06-01"}

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
