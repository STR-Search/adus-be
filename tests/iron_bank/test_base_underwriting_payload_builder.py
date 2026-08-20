from decimal import Decimal

from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService


def _builder():
    return BaseUnderwritingPayloadBuilder()


def _option(option_id: int, name: str, price=1000) -> dict:
    return {"id": option_id, "amenity_name": name, "price_tier_2": price}


class TestBuildOpexPropertyTaxes:
    """Amounts are money, so they are stored at cents.

    The assertions compare ``str(...)`` rather than the Decimal itself:
    Decimal equality ignores scale (Decimal("6000.0000") == Decimal("6000.00")),
    so only the string pins the number of decimal places actually persisted.
    """

    def test_amounts_are_quantized_to_cents(self):
        # 0.0125 carries four decimal places of its own, which would otherwise
        # propagate into the stored blob as 6000.0000.
        result = _builder().build_opex_property_taxes(
            property_tax_pct=Decimal("0.0125"),
            purchase_price=Decimal("480000"),
        )

        assert str(result["annual_amount"]) == "6000.00"
        assert str(result["monthly_amount"]) == "500.00"

    def test_a_repeating_monthly_amount_is_rounded(self):
        result = _builder().build_opex_property_taxes(
            property_tax_pct=Decimal("0.0125"),
            purchase_price=Decimal("500000"),
        )

        # 6250 / 12 = 520.8333...
        assert str(result["annual_amount"]) == "6250.00"
        assert str(result["monthly_amount"]) == "520.83"

    def test_rounding_is_half_even_matching_the_calculator(self):
        # 375000 * 0.0133 = 4987.50, / 12 = 415.625 exactly. Half-even gives
        # 415.62, half-up would give 415.63. This follows
        # UnderwritingCalculator._money so every money figure on the payload
        # rounds the same way.
        result = _builder().build_opex_property_taxes(
            property_tax_pct=Decimal("0.0133"),
            purchase_price=Decimal("375000"),
        )

        assert str(result["annual_amount"]) == "4987.50"
        assert str(result["monthly_amount"]) == "415.62"

    def test_inputs_keep_the_unrounded_figures(self):
        result = _builder().build_opex_property_taxes(
            property_tax_pct=Decimal("0.0125"),
            purchase_price=Decimal("480000"),
        )

        assert result["source"] == "opex_property_tax_pct"
        assert result["inputs"] == {
            "opex_property_tax_pct": Decimal("0.0125"),
            "purchase_price": Decimal("480000"),
        }

    def test_the_zillow_annual_source_is_quantized_too(self):
        result = _builder().build_opex_property_taxes(
            property_tax_pct=None,
            purchase_price=None,
            zillow_annual_tax=Decimal("7231.4567"),
        )

        assert result["source"] == "zillow_annual_tax"
        assert str(result["annual_amount"]) == "7231.46"
        # 7231.4567 / 12 = 602.6213916...
        assert str(result["monthly_amount"]) == "602.62"

    def test_returns_none_when_no_source_resolves(self):
        assert (
            _builder().build_opex_property_taxes(
                property_tax_pct=None, purchase_price=Decimal("480000")
            )
            is None
        )
        assert (
            _builder().build_opex_property_taxes(
                property_tax_pct=Decimal("0.0125"), purchase_price=None
            )
            is None
        )


class TestOptimizationListOrder:
    """The seeded rows bracket the must-haves, and sort_order is stamped from
    this list's positions on save, so the order is the contract."""

    _CATALOG = [
        _option(PrepareUwDataService.FURNISHINGS_OPTION_ID, "Furnishings"),
        _option(PrepareUwDataService.CONSOLIDATED_SHIPPING_OPTION_ID, "Shipping"),
        _option(
            PrepareUwDataService.STR_CRIBS_PROJECT_MANAGEMENT_OPTION_ID, "Project Mgmt"
        ),
        _option(1, "Hot Tub"),
        _option(2, "Fire Pit"),
        _option(3, "Sauna"),
    ]

    def _categories(self, must_have_amenity_ids: list[int]) -> list[str]:
        items = _builder()._build_optimization_list(
            {
                "construction_amenities": self._CATALOG,
                "must_have_amenity_ids": must_have_amenity_ids,
            }
        )
        return [item["category"] for item in items]

    def test_must_haves_sit_between_furnishings_and_the_service_lines(self):
        # Several must-haves, so the order within the middle block is pinned too:
        # it follows the order the market lists them, not the catalog's.
        assert self._categories([3, 1, 2]) == [
            "Furnishings",
            "Sauna",
            "Hot Tub",
            "Fire Pit",
            "Project Mgmt",
            "Shipping",
        ]

    def test_the_bracket_holds_with_no_must_haves(self):
        assert self._categories([]) == ["Furnishings", "Project Mgmt", "Shipping"]

    def test_a_must_have_naming_a_seeded_option_stays_in_its_bracket(self):
        # Can't happen with today's ids (catalog ids are positive, the seeded
        # sentinels are not), but the bracket must not depend on that.
        assert self._categories(
            [
                PrepareUwDataService.CONSOLIDATED_SHIPPING_OPTION_ID,
                1,
                PrepareUwDataService.FURNISHINGS_OPTION_ID,
            ]
        ) == ["Furnishings", "Hot Tub", "Project Mgmt", "Shipping"]

    def test_every_seeded_option_is_placed_in_the_bracket(self):
        # Guards drift: a fourth synthetic option added to the prepare service
        # would otherwise be silently left out of the seeded payload.
        builder = BaseUnderwritingPayloadBuilder
        assert set(
            builder._LEADING_AMENITY_OPTION_IDS + builder._TRAILING_AMENITY_OPTION_IDS
        ) == set(PrepareUwDataService.SEEDED_AMENITY_OPTION_IDS)
