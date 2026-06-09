from decimal import Decimal

from app.iron_bank.schemas.save_underwriting import (
    ForecastedRevenueInput,
    OperatingExpenseInput,
    OptimizationItemInput,
    PurchaseDetailsInput,
)
from app.iron_bank.services.underwriting_calculator import UnderwritingCalculator


def test_calculates_forecasted_revenue_for_each_scenario():
    calculator = UnderwritingCalculator()
    purchase_details = calculator.calculate_purchase_details(
        PurchaseDetailsInput(
            purchase_price=Decimal("100000"),
            down_payment_pct=Decimal("0.20"),
            interest_rate=Decimal("0"),
            mortgage_years=10,
            closing_costs_pct=Decimal("0.03"),
        )
    )
    forecasted_revenue = ForecastedRevenueInput.model_validate(
        {
            "co_hosting_fee_pct": Decimal("0.10"),
            "annual_re_appreciation_pct": Decimal("0.04"),
            "scenarios": {
                "low": {"forecasted_revenue": Decimal("10000")},
                "mid": {"forecasted_revenue": Decimal("12000")},
                "high": {"forecasted_revenue": Decimal("15000")},
            },
        }
    )
    operating_expenses = [
        OperatingExpenseInput(expense="Utilities", monthly=Decimal("100")),
        OperatingExpenseInput(expense="Internet", monthly=Decimal("200")),
    ]
    optimization_items = [
        OptimizationItemInput(category="Paint", total_price=Decimal("5000")),
        OptimizationItemInput(category="Furniture", total_price=Decimal("2000")),
    ]

    result = calculator.calculate_forecasted_revenue(
        forecasted_revenue=forecasted_revenue,
        purchase_details=purchase_details,
        operating_expenses=operating_expenses,
        optimization_items=optimization_items,
    )

    assert result["co_hosting_fee_pct"] == Decimal("0.10")
    assert result["annual_re_appreciation_pct"] == Decimal("0.04")
    assert result["scenarios"]["low"] == {
        "forecasted_revenue": Decimal("10000"),
        "operating_expenses_annual": Decimal("3456.00"),
        "co_hosting_fee": Decimal("1000.00"),
        "net_operating_income": Decimal("5544.00"),
        "debt_service_annual": Decimal("8000.00"),
        "annual_free_cash_flow": Decimal("-2456.00"),
        "principal_pay_down": Decimal("8000.00"),
        "annual_re_appreciation": Decimal("4000.00"),
        "annual_total_re_return_pct": Decimal("0.3181"),
    }
    assert result["scenarios"]["mid"]["operating_expenses_annual"] == Decimal("3600")
    assert result["scenarios"]["mid"]["annual_total_re_return_pct"] == Decimal("0.3733")
    assert result["scenarios"]["high"]["operating_expenses_annual"] == Decimal("3744.00")
    assert result["scenarios"]["high"]["annual_total_re_return_pct"] == Decimal("0.4585")


def test_calculates_y1_coc_including_tax_savings_for_each_scenario():
    calculator = UnderwritingCalculator()
    purchase_details = calculator.calculate_purchase_details(
        PurchaseDetailsInput(
            purchase_price=Decimal("100000"),
            down_payment_pct=Decimal("0.20"),
            interest_rate=Decimal("0"),
            mortgage_years=10,
            closing_costs_pct=Decimal("0.03"),
        )
    )
    forecasted_revenue = {
        "scenarios": {
            "low": {
                "net_operating_income": Decimal("5544.00"),
                "debt_service_annual": Decimal("8000.00"),
            },
            "mid": {
                "net_operating_income": Decimal("7200.00"),
                "debt_service_annual": Decimal("8000.00"),
            },
            "high": {
                "net_operating_income": Decimal("9756.00"),
                "debt_service_annual": Decimal("8000.00"),
            },
        }
    }
    tax_data = {"tax_savings": Decimal("5000")}
    optimization_items = [
        OptimizationItemInput(category="Paint", total_price=Decimal("5000")),
        OptimizationItemInput(category="Furniture", total_price=Decimal("2000")),
    ]

    result = calculator.calculate_y1_coc_incl_tax_savings(
        forecasted_revenue=forecasted_revenue,
        tax_data=tax_data,
        purchase_details=purchase_details,
        optimization_items=optimization_items,
    )

    assert result == {
        "low_pct": Decimal("0.085"),
        "mid_pct": Decimal("0.140"),
        "high_pct": Decimal("0.225"),
    }
