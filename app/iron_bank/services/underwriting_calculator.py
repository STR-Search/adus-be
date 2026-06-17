from decimal import Decimal

import structlog

from app.iron_bank.schemas.save_underwriting import (
    ForecastedRevenueInput,
    OperatingExpenseInput,
    OptimizationItemInput,
    PurchaseDetailsInput,
    UnderwritingTaxInput,
)

logger = structlog.get_logger(__name__)


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

        logger.debug(
            "calculate_purchase_details",
            purchase_price=purchase_price,
            down_payment_pct=down_payment_pct,
            closing_costs_pct=closing_costs_pct,
            down_payment_amount=down_payment_amount,
            loan_amount=loan_amount,
            closing_costs_amount=closing_costs_amount,
            interest_rate=data.get("interest_rate"),
            mortgage_years=data.get("mortgage_years"),
        )

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

        logger.debug(
            "calculate_taxes",
            purchase_price=purchase_price,
            optimization_total=optimization_total,
            land_assumptions_pct=taxes.land_assumptions_pct,
            sla_multiplier_pct=taxes.sla_multiplier_pct,
            bonus_amount_pct=taxes.bonus_amount_pct,
            tax_rate_pct=taxes.tax_rate_pct,
            improvement_basis=improvement_basis,
            estimated_short_life_assets=estimated_short_life_assets,
            y1_loss_from_depreciation=y1_loss_from_depreciation,
            tax_savings=tax_savings,
        )

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
        total_oop = self.calculate_total_oop(
            purchase_details=purchase_details,
            optimization_items=optimization_items,
        )

        logger.debug(
            "calculate_forecasted_revenue: pre-scenario inputs",
            total_opex_monthly=total_opex_monthly,
            opex_count=len(operating_expenses),
            opex_breakdown=[
                {"name": e.expense_name, "monthly_amount": e.monthly_amount}
                for e in operating_expenses
            ],
            debt_service_annual=debt_service_annual,
            principal_pay_down=principal_pay_down,
            annual_re_appreciation=annual_re_appreciation,
            annual_re_appreciation_pct=forecasted_revenue.annual_re_appreciation_pct,
            co_hosting_fee_pct=forecasted_revenue.co_hosting_fee_pct,
            total_oop=total_oop,
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

            logger.debug(
                "calculate_forecasted_revenue: scenario",
                scenario=scenario_name,
                opex_multiplier=opex_multiplier,
                gross_revenue=revenue,
                operating_expenses_annual=operating_expenses_annual,
                co_hosting_fee=co_hosting_fee,
                net_operating_income=net_operating_income,
                debt_service_annual=debt_service_annual,
                annual_free_cash_flow=annual_free_cash_flow,
                principal_pay_down=principal_pay_down,
                annual_re_appreciation=annual_re_appreciation,
                annual_total_re_return_pct=annual_total_re_return_pct,
            )

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
        total_oop = self.calculate_total_oop(
            purchase_details=purchase_details,
            optimization_items=optimization_items,
        )
        tax_savings = tax_data["tax_savings"]

        logger.debug(
            "calculate_y1_coc_incl_tax_savings: inputs",
            total_oop=total_oop,
            tax_savings=tax_savings,
        )

        result = {}
        for scenario_name, scenario in forecasted_revenue["scenarios"].items():
            noi = scenario["net_operating_income"]
            dsa = scenario["debt_service_annual"]
            numerator = noi - dsa + tax_savings
            y1_coc = self._y1_coc_percentage(numerator / total_oop)
            logger.debug(
                "calculate_y1_coc_incl_tax_savings: scenario",
                scenario=scenario_name,
                net_operating_income=noi,
                debt_service_annual=dsa,
                tax_savings=tax_savings,
                numerator=numerator,
                y1_coc_pct=y1_coc,
            )
            result[f"{scenario_name}_pct"] = y1_coc

        return result

    def calculate_cash_on_cash(
        self,
        forecasted_revenue: dict,
        total_oop: Decimal,
    ) -> dict:
        if total_oop == 0:
            raise ValueError("total_oop is required to calculate cash on cash")

        return {
            f"{scenario_name}_pct": self._percentage(
                scenario["annual_free_cash_flow"] / total_oop
            )
            for scenario_name, scenario in forecasted_revenue["scenarios"].items()
        }

    def calculate_prr(
        self, purchase_price: Decimal, mid_gross_revenue: Decimal
    ) -> Decimal:
        if mid_gross_revenue == 0:
            raise ValueError("mid gross revenue is required to calculate PRR")
        return self._percentage(mid_gross_revenue / purchase_price)

    def calculate_budget_to_pp(
        self,
        total_oop: Decimal,
        purchase_price: Decimal,
    ) -> Decimal:
        if purchase_price == 0:
            raise ValueError("purchase_price is required to calculate budget to PP")
        return self._percentage(total_oop / purchase_price)

    def _calculate_debt_service_annual(self, purchase_details: dict) -> Decimal:
        rate = purchase_details["interest_rate"] / self._MONTHS_IN_YEAR
        nper = purchase_details["mortgage_years"] * 12
        pv = purchase_details["loan_amount"]
        monthly_payment = self._pmt(rate=rate, nper=nper, pv=pv)
        annual = monthly_payment * self._MONTHS_IN_YEAR

        logger.debug(
            "_calculate_debt_service_annual",
            loan_amount=pv,
            interest_rate=purchase_details["interest_rate"],
            monthly_rate=rate,
            mortgage_years=purchase_details["mortgage_years"],
            total_months=nper,
            monthly_payment=monthly_payment,
            debt_service_annual=annual,
        )

        return annual

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
        principal_pay_down = loan_amount - ending_balance

        logger.debug(
            "_calculate_year_one_principal_pay_down",
            loan_amount=loan_amount,
            ending_balance_after_12_months=ending_balance,
            principal_pay_down=principal_pay_down,
        )

        return principal_pay_down

    def calculate_total_oop(
        self,
        purchase_details: dict,
        optimization_items: list[OptimizationItemInput],
    ) -> Decimal:
        optimization_total = sum(
            item.total_price or Decimal("0") for item in optimization_items
        )
        down_payment_amount = purchase_details["down_payment_amount"]
        closing_costs_amount = purchase_details["closing_costs_amount"]
        total_oop = down_payment_amount + closing_costs_amount + optimization_total

        logger.debug(
            "calculate_total_oop",
            down_payment_amount=down_payment_amount,
            closing_costs_amount=closing_costs_amount,
            optimization_total=optimization_total,
            optimization_count=len(optimization_items),
            total_oop=total_oop,
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
