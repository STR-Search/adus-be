from decimal import Decimal

from app.iron_bank.schemas.save_underwriting import (
    ForecastedRevenueInput,
    OperatingExpenseInput,
    OptimizationItemInput,
    PurchaseDetailsInput,
    UnderwritingTaxInput,
)


class UnderwritingCalculator:
    _LOW_OPEX_MULTIPLIER = Decimal("0.96")
    _MID_OPEX_MULTIPLIER = Decimal("1")
    _HIGH_OPEX_MULTIPLIER = Decimal("1.04")
    _MONTHS_IN_YEAR = Decimal("12")
    _MONEY_QUANT = Decimal("0.01")
    _PERCENT_QUANT = Decimal("0.0001")
    _Y1_COC_QUANT = Decimal("0.001")

    def calculate_purchase_details(
        self,
        purchase_details: PurchaseDetailsInput,
    ) -> dict:
        data = purchase_details.model_dump()

        purchase_price = data["purchase_price"]
        down_payment_pct = data["down_payment_pct"]
        closing_costs_pct = data["closing_costs_pct"]

        down_payment_amount = purchase_price * down_payment_pct
        loan_amount = purchase_price - down_payment_amount
        closing_costs_amount = purchase_price * closing_costs_pct

        return {
            **data,
            "down_payment_amount": down_payment_amount,
            "loan_amount": loan_amount,
            "closing_costs_amount": closing_costs_amount,
        }

    def calculate_taxes(
        self,
        taxes: UnderwritingTaxInput,
        purchase_price: Decimal,
        optimization_items: list[OptimizationItemInput],
    ) -> dict:
        data = taxes.model_dump(exclude_unset=True)
        optimization_total = sum(
            item.total_price or Decimal("0") for item in optimization_items
        )

        improvement_basis = (
            purchase_price * (Decimal("1") - taxes.land_assumptions_pct)
            + optimization_total
        )
        estimated_short_life_assets = improvement_basis * taxes.sla_multiplier_pct
        y1_loss_from_depreciation = estimated_short_life_assets * taxes.bonus_amount_pct
        tax_savings = taxes.tax_rate_pct * y1_loss_from_depreciation

        return {
            **data,
            "improvement_basis": improvement_basis,
            "estimated_short_life_assets": estimated_short_life_assets,
            "y1_loss_from_depreciation": y1_loss_from_depreciation,
            "tax_savings": tax_savings,
        }

    def calculate_forecasted_revenue(
        self,
        forecasted_revenue: ForecastedRevenueInput,
        purchase_details: dict,
        operating_expenses: list[OperatingExpenseInput],
        optimization_items: list[OptimizationItemInput],
    ) -> dict:
        data = forecasted_revenue.model_dump()
        total_opex_monthly = sum(
            expense.monthly_amount or Decimal("0") for expense in operating_expenses
        )
        debt_service_annual = self._calculate_debt_service_annual(purchase_details)
        principal_pay_down = self._calculate_year_one_principal_pay_down(
            purchase_details
        )
        annual_re_appreciation = (
            purchase_details["purchase_price"]
            * forecasted_revenue.annual_re_appreciation_pct
        )
        total_oop = self._calculate_total_oop(
            purchase_details=purchase_details,
            optimization_items=optimization_items,
        )

        scenario_multipliers = {
            "low": self._LOW_OPEX_MULTIPLIER,
            "mid": self._MID_OPEX_MULTIPLIER,
            "high": self._HIGH_OPEX_MULTIPLIER,
        }
        scenarios = {}
        for scenario_name, opex_multiplier in scenario_multipliers.items():
            scenario = getattr(forecasted_revenue.scenarios, scenario_name)
            revenue = scenario.forecasted_revenue
            operating_expenses_annual = (
                total_opex_monthly * self._MONTHS_IN_YEAR * opex_multiplier
            )
            co_hosting_fee = revenue * forecasted_revenue.co_hosting_fee_pct
            net_operating_income = revenue - operating_expenses_annual - co_hosting_fee
            annual_free_cash_flow = net_operating_income - debt_service_annual
            annual_total_re_return_pct = (
                annual_free_cash_flow + principal_pay_down + annual_re_appreciation
            ) / total_oop

            scenarios[scenario_name] = {
                **scenario.model_dump(),
                "operating_expenses_annual": self._money(operating_expenses_annual),
                "co_hosting_fee": self._money(co_hosting_fee),
                "net_operating_income": self._money(net_operating_income),
                "debt_service_annual": self._money(debt_service_annual),
                "annual_free_cash_flow": self._money(annual_free_cash_flow),
                "principal_pay_down": self._money(principal_pay_down),
                "annual_re_appreciation": self._money(annual_re_appreciation),
                "annual_total_re_return_pct": self._percentage(
                    annual_total_re_return_pct
                ),
            }

        return {
            **data,
            "scenarios": scenarios,
        }

    def calculate_y1_coc_incl_tax_savings(
        self,
        forecasted_revenue: dict,
        tax_data: dict,
        purchase_details: dict,
        optimization_items: list[OptimizationItemInput],
    ) -> dict:
        total_oop = self._calculate_total_oop(
            purchase_details=purchase_details,
            optimization_items=optimization_items,
        )
        tax_savings = tax_data["tax_savings"]

        return {
            f"{scenario_name}_pct": self._y1_coc_percentage(
                (
                    scenario["net_operating_income"]
                    - scenario["debt_service_annual"]
                    + tax_savings
                )
                / total_oop
            )
            for scenario_name, scenario in forecasted_revenue["scenarios"].items()
        }

    def _calculate_debt_service_annual(self, purchase_details: dict) -> Decimal:
        monthly_payment = self._pmt(
            rate=purchase_details["interest_rate"] / self._MONTHS_IN_YEAR,
            nper=purchase_details["mortgage_years"] * 12,
            pv=purchase_details["loan_amount"],
        )
        return monthly_payment * self._MONTHS_IN_YEAR

    def _calculate_year_one_principal_pay_down(
        self,
        purchase_details: dict,
    ) -> Decimal:
        loan_amount = purchase_details["loan_amount"]
        ending_balance = self._ending_balance(
            loan_amount=loan_amount,
            rate=purchase_details["interest_rate"],
            years=purchase_details["mortgage_years"],
            months_elapsed=12,
        )
        return loan_amount - ending_balance

    def _calculate_total_oop(
        self,
        purchase_details: dict,
        optimization_items: list[OptimizationItemInput],
    ) -> Decimal:
        optimization_total = sum(
            item.total_price or Decimal("0") for item in optimization_items
        )
        total_oop = (
            purchase_details["down_payment_amount"]
            + purchase_details["closing_costs_amount"]
            + optimization_total
        )
        if total_oop == 0:
            raise ValueError("total_oop is required to calculate forecasted revenue")
        return total_oop

    def _pmt(self, rate: Decimal, nper: int, pv: Decimal) -> Decimal:
        if rate == 0:
            return pv / Decimal(nper)
        return (pv * rate) / (Decimal("1") - (Decimal("1") + rate) ** -nper)

    def _ending_balance(
        self,
        loan_amount: Decimal,
        rate: Decimal,
        years: int,
        months_elapsed: int,
    ) -> Decimal:
        if rate == 0:
            monthly_payment = self._pmt(
                rate=Decimal("0"),
                nper=years * 12,
                pv=loan_amount,
            )
            return loan_amount - (monthly_payment * Decimal(months_elapsed))

        monthly_rate = rate / self._MONTHS_IN_YEAR
        total_months = years * 12
        return (
            loan_amount
            * (
                ((Decimal("1") + monthly_rate) ** months_elapsed)
                - ((Decimal("1") + monthly_rate) ** total_months)
            )
            / (Decimal("1") - ((Decimal("1") + monthly_rate) ** total_months))
        )

    def _money(self, value: Decimal) -> Decimal:
        return value.quantize(self._MONEY_QUANT)

    def _percentage(self, value: Decimal) -> Decimal:
        return value.quantize(self._PERCENT_QUANT)

    def _y1_coc_percentage(self, value: Decimal) -> Decimal:
        return value.quantize(self._Y1_COC_QUANT)
