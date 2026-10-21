from decimal import Decimal

import pytest

from app.iron_bank.schemas.save_underwriting import (
    ForecastedRevenueInput,
    OperatingExpenseInput,
    OptimizationItemInput,
    ProjectLoanInput,
    PurchaseDetailsInput,
    UnderwritingTaxInput,
)
from app.iron_bank.services.underwriting_calculator import UnderwritingCalculator


def test_calculates_taxes_using_sla_multiplier_pct():
    calculator = UnderwritingCalculator()
    taxes = UnderwritingTaxInput(
        land_assumptions_pct=Decimal("0.20"),
        sla_multiplier_pct=Decimal("0.36"),
        bonus_amount_pct=Decimal("1"),
        tax_rate_pct=Decimal("0.37"),
    )
    optimization_items = [
        OptimizationItemInput(category="Paint", total_price=Decimal("7000"))
    ]

    result = calculator.calculate_taxes(
        taxes=taxes,
        purchase_price=Decimal("100000"),
        optimization_items=optimization_items,
    )

    assert result["improvement_basis"] == Decimal("87000.00")
    assert result["estimated_short_life_assets"] == Decimal("31320.0000")
    assert result["tax_savings"] == Decimal("11588.400000")


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
    assert result["scenarios"]["high"]["operating_expenses_annual"] == Decimal(
        "3744.00"
    )
    assert result["scenarios"]["high"]["annual_total_re_return_pct"] == Decimal(
        "0.4585"
    )


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


def test_calculates_total_oop_and_cash_on_cash_from_forecasted_revenue():
    calculator = UnderwritingCalculator()
    purchase_details = {
        "down_payment_amount": Decimal("200000"),
        "closing_costs_amount": Decimal("30000"),
    }
    optimization_items = [
        OptimizationItemInput(category="Furniture", total_price=Decimal("20000"))
    ]
    forecasted_revenue = {
        "scenarios": {
            "low": {"annual_free_cash_flow": Decimal("108480.00")},
            "mid": {"annual_free_cash_flow": Decimal("128000.00")},
            "high": {"annual_free_cash_flow": Decimal("147520.00")},
        }
    }

    total_oop = calculator.calculate_total_oop(
        purchase_details=purchase_details,
        optimization_items=optimization_items,
    )
    cash_on_cash = calculator.calculate_cash_on_cash(
        forecasted_revenue=forecasted_revenue,
        total_oop=total_oop,
    )

    assert total_oop == Decimal("250000")
    assert cash_on_cash == {
        "low_pct": Decimal("0.4339"),
        "mid_pct": Decimal("0.5120"),
        "high_pct": Decimal("0.5901"),
    }


def test_calculates_prr_and_budget_to_pp():
    calculator = UnderwritingCalculator()

    assert calculator.calculate_prr(
        purchase_price=Decimal("1000000"),
        mid_gross_revenue=Decimal("220000"),
    ) == Decimal("0.2200")
    assert calculator.calculate_budget_to_pp(
        total_oop=Decimal("250000"),
        purchase_price=Decimal("1000000"),
    ) == Decimal("0.2500")


# --- project loan -------------------------------------------------------------


def test_project_loan_monthly_amount_is_the_loan_payment():
    result = UnderwritingCalculator().calculate_project_loan(
        ProjectLoanInput(
            loan_amount=Decimal("50000"),
            interest_rate=Decimal("0.065"),
            terms_years=7,
        )
    )

    # Excel: =PMT(0.065/12, 84, -50000)
    assert result["monthly_amount"] == Decimal("742.47")
    assert result["loan_amount"] == Decimal("50000")


def test_project_loan_at_zero_interest_splits_the_principal():
    result = UnderwritingCalculator().calculate_project_loan(
        ProjectLoanInput(
            loan_amount=Decimal("84000"), interest_rate=Decimal("0"), terms_years=7
        )
    )

    assert result["monthly_amount"] == Decimal("1000.00")


def test_project_loan_without_an_amount_has_no_monthly_amount():
    result = UnderwritingCalculator().calculate_project_loan(
        ProjectLoanInput(interest_rate=Decimal("0.065"), terms_years=7)
    )

    assert result["monthly_amount"] is None


def _total_oop(project_loan):
    return UnderwritingCalculator().calculate_total_oop(
        purchase_details={
            "down_payment_amount": Decimal("200000"),
            "closing_costs_amount": Decimal("30000"),
        },
        optimization_items=[
            OptimizationItemInput(category="Furniture", total_price=Decimal("20000"))
        ],
        project_loan=project_loan,
    )


def test_total_oop_nets_out_the_project_loan():
    assert _total_oop({"loan_amount": Decimal("50000")}) == Decimal("200000")


def test_total_oop_reads_a_stored_project_loan_blob():
    # As persisted: jsonable_encoder has turned the Decimals into floats.
    stored = {
        "loan_amount": 50000.0,
        "interest_rate": 0.065,
        "terms_years": 7,
        "monthly_amount": 742.47,
    }

    assert _total_oop(stored) == Decimal("200000")


def test_total_oop_ignores_a_project_loan_without_an_amount():
    assert _total_oop({"loan_amount": None}) == Decimal("250000")
    assert _total_oop(None) == Decimal("250000")


def test_project_loan_cannot_exceed_the_out_of_pocket_total():
    with pytest.raises(ValueError, match="project loan amount"):
        _total_oop({"loan_amount": Decimal("250000.01")})
