from decimal import Decimal
from types import SimpleNamespace

from app.iron_bank.services.purchase_price_reconciliation_payload_builder import (
    PurchasePriceReconciliationPayloadBuilder,
)


def make_underwriting():
    return SimpleNamespace(
        detail=SimpleNamespace(
            purchase_details={
                "purchase_price": 485000,
                "down_payment_pct": 0.2,
                "interest_rate": 0.0675,
                "mortgage_years": 30,
                "closing_costs_pct": 0.03,
            },
            forecasted_revenue={
                "co_hosting_fee_pct": 0.1,
                "annual_re_appreciation_pct": 0.04,
                "scenarios": {
                    "low": {"forecasted_revenue": 72000},
                    "mid": {"forecasted_revenue": 98000},
                    "high": {"forecasted_revenue": 127000},
                },
            },
        ),
        taxes=SimpleNamespace(
            land_assumptions_pct=Decimal("0.20"),
            sla_multiplier_pct=Decimal("0.36"),
            bonus_amount_pct=Decimal("1"),
            tax_rate_pct=Decimal("0.37"),
        ),
        optimization_items=[
            SimpleNamespace(
                category="Furniture",
                total_price=Decimal("20000"),
                metric=None,
                base_price=None,
                spec=None,
                tier=None,
            )
        ],
        operating_expenses=[
            SimpleNamespace(
                expense_name="Utilities",
                monthly_amount=Decimal("1000"),
            )
        ],
    )


def test_normalize_purchase_price_accepts_zillow_money_values():
    normalize = PurchasePriceReconciliationPayloadBuilder.normalize_purchase_price

    assert normalize("$525,000") == Decimal("525000")
    assert normalize(525000) == Decimal("525000")
    assert normalize(None) is None
    assert normalize("Contact for price") is None
    assert normalize(0) is None


def test_build_uses_new_price_and_existing_assumptions():
    payload = PurchasePriceReconciliationPayloadBuilder().build(
        underwriting=make_underwriting(),
        purchase_price=Decimal("525000"),
    )

    assert payload.details.purchase_details.purchase_price == Decimal("525000")
    assert payload.details.purchase_details.down_payment_pct == Decimal("0.2")
    assert payload.details.purchase_details.interest_rate == Decimal("0.0675")
    assert (
        payload.details.forecasted_revenue.scenarios.mid.forecasted_revenue
        == Decimal("98000")
    )
    assert payload.taxes.land_assumptions_pct == Decimal("0.20")
    assert payload.optimization_list[0].total_price == Decimal("20000")
    assert payload.operating_expenses[0].monthly_amount == Decimal("1000")
