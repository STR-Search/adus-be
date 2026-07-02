from decimal import Decimal
from typing import Any

from app.iron_bank.enums import DealStatus
from app.iron_bank.services.purchase_price_reconciliation_payload_builder import (
    PurchasePriceReconciliationPayloadBuilder,
)


class BaseUnderwritingPayloadBuilder:
    """Shared default-seeding logic for underwriting payload builders.

    Holds the financing/tax defaults and the helpers that both the automated
    (``UnderwritingPayloadBuilder``) and non-automated
    (``NonAutomatedUnderwritingPayloadBuilder``) flows use to seed a draft
    underwriting. It does not fetch data or persist anything.
    """

    _DEFAULT_DEAL_STATUS = DealStatus.TEMPLATE_GENERATED
    _DEFAULT_SLA_MULTIPLIER_PCT = Decimal("0.36")
    _DEFAULT_BONUS_AMOUNT_PCT = Decimal("1")

    def _build_details(
        self,
        *,
        purchase_price: Decimal | None,
        config: dict[str, Any],
        cleaning_cost: dict[str, Any] | None,
        property_taxes: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        detail: dict[str, Any] = {}
        if purchase_price is not None:
            detail["purchase_details"] = {
                "purchase_price": purchase_price,
                "down_payment_pct": self._decimal_or_default(
                    config.get("down_payment"), Decimal("0.1")
                ),
                "interest_rate": self._decimal_or_default(
                    config.get("interest_rate"), Decimal("0.0688")
                ),
                "mortgage_years": int(config.get("loan_term_years") or 30),
                "closing_costs_pct": self._decimal_or_default(
                    config.get("closing_costs"), Decimal("0.03")
                ),
            }
        if cleaning_cost is not None:
            detail["cleaning_cost"] = cleaning_cost
        if property_taxes is not None:
            detail["property_taxes"] = property_taxes
        return detail or None

    def _build_taxes(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "land_assumptions_pct": self._decimal_or_default(
                config.get("land_assumptions"), Decimal("0.2")
            ),
            "sla_multiplier_pct": self._decimal_or_default(
                config.get("sla_multiplier_pct"), self._DEFAULT_SLA_MULTIPLIER_PCT
            ),
            "bonus_amount_pct": self._decimal_or_default(
                config.get("bonus_amount_pct"), self._DEFAULT_BONUS_AMOUNT_PCT
            ),
            "tax_rate_pct": self._decimal_or_default(
                config.get("tax_rate"), Decimal("0.37")
            ),
        }

    def _money_to_decimal(self, value: Any) -> Decimal | None:
        return PurchasePriceReconciliationPayloadBuilder.normalize_purchase_price(value)

    def _decimal_or_default(self, value: Any, default: Decimal) -> Decimal:
        if value is None:
            return default
        return Decimal(str(value))
