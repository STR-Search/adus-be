import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload


class PurchasePriceReconciliationPayloadBuilder:
    @staticmethod
    def normalize_purchase_price(value: Any) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value if value > 0 else None
        if isinstance(value, int | float):
            amount = Decimal(str(value))
            return amount if amount > 0 else None

        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        if not cleaned:
            return None
        try:
            amount = Decimal(cleaned)
        except InvalidOperation:
            return None
        return amount if amount > 0 else None

    def build(
        self, *, underwriting, purchase_price: Decimal
    ) -> SaveUnderwritingPayload:
        if underwriting.detail is None or underwriting.detail.purchase_details is None:
            raise ValueError(
                "existing purchase details are required for price reconciliation"
            )
        if underwriting.detail.forecasted_revenue is None:
            raise ValueError(
                "existing forecasted revenue is required for price reconciliation"
            )
        if underwriting.taxes is None:
            raise ValueError("existing taxes are required for price reconciliation")

        purchase_details = underwriting.detail.purchase_details
        forecasted_revenue = underwriting.detail.forecasted_revenue
        payload = {
            "is_automated": underwriting.is_automated,
            "details": {
                "purchase_details": {
                    "purchase_price": purchase_price,
                    "down_payment_pct": purchase_details["down_payment_pct"],
                    "interest_rate": purchase_details["interest_rate"],
                    "mortgage_years": purchase_details["mortgage_years"],
                    "closing_costs_pct": purchase_details["closing_costs_pct"],
                },
                "forecasted_revenue": {
                    "co_hosting_fee_pct": forecasted_revenue["co_hosting_fee_pct"],
                    "annual_re_appreciation_pct": forecasted_revenue[
                        "annual_re_appreciation_pct"
                    ],
                    "scenarios": {
                        name: {
                            "forecasted_revenue": forecasted_revenue["scenarios"][name][
                                "forecasted_revenue"
                            ]
                        }
                        for name in ("low", "mid", "high")
                    },
                },
            },
            "taxes": {
                "land_assumptions_pct": underwriting.taxes.land_assumptions_pct,
                "sla_multiplier_pct": underwriting.taxes.sla_multiplier_pct,
                "bonus_amount_pct": underwriting.taxes.bonus_amount_pct,
                "tax_rate_pct": underwriting.taxes.tax_rate_pct,
            },
            "optimization_list": [
                {
                    "category": item.category,
                    "total_price": item.total_price,
                    "metric": item.metric,
                    "base_price": item.base_price,
                    "spec": item.spec,
                    "tier": item.tier,
                }
                for item in underwriting.optimization_items
            ],
            "operating_expenses": [
                {
                    "expense": expense.expense_name,
                    "monthly": expense.monthly_amount,
                }
                for expense in underwriting.operating_expenses
            ],
        }
        return SaveUnderwritingPayload.model_validate(payload)
