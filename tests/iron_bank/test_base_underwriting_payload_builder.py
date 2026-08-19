from decimal import Decimal

from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)


def _builder():
    return BaseUnderwritingPayloadBuilder()


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
