from decimal import Decimal, InvalidOperation
import re
from typing import Any

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload


class UnderwritingPayloadBuilder:
    """Builds a save payload from prepared UW data.

    This replaces the FE mapping step for automated/draft underwriting flows.
    It does not fetch data or persist anything.
    """

    _DEFAULT_DEAL_STATUS = "Draft"
    _DEFAULT_SLA_MULTIPLIER_PCT = Decimal("0.36")
    _DEFAULT_BONUS_AMOUNT_PCT = Decimal("1")
    # Absolute opex keys that are not monthly operating expenses and must not
    # be saved as such.
    _EXCLUDED_ABSOLUTE_EXPENSES = frozenset({"consolidated_shipping"})

    def build(self, prepared: dict[str, Any]) -> SaveUnderwritingPayload:
        zillow_property = prepared.get("zillow_property") or {}
        config = prepared.get("config") or {}
        opex = prepared.get("opex") or {}

        purchase_price = self._money_to_decimal(zillow_property.get("price"))
        cleaning_cost = self._build_cleaning_cost(opex.get("cleaning") or {})

        payload = {
            "zpid": zillow_property.get("id"),
            "market_id": prepared.get("market_id"),
            "deal_status": self._DEFAULT_DEAL_STATUS,
            "listing_url": zillow_property.get("url"),
            "property_address": zillow_property.get("address"),
            "purchase_price": purchase_price,
            "uw_details": self._build_uw_details(
                purchase_price=purchase_price,
                config=config,
                cleaning_cost=cleaning_cost,
            ),
            "taxes": self._build_taxes(config) if purchase_price is not None else None,
            "operating_expenses": self._build_operating_expenses(opex),
        }
        return SaveUnderwritingPayload.model_validate(payload)

    def _build_uw_details(
        self,
        *,
        purchase_price: Decimal | None,
        config: dict[str, Any],
        cleaning_cost: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        detail: dict[str, Any] = {}
        if purchase_price is not None:
            detail["purchase_details"] = {
                "purchase_price": purchase_price,
                "down_payment_pct": self._decimal_or_default(config.get("down_payment"), Decimal("0.1")),
                "interest_rate": self._decimal_or_default(config.get("interest_rate"), Decimal("0.07")),
                "mortgage_years": int(config.get("loan_term_years") or 30),
                "closing_costs_pct": self._decimal_or_default(config.get("closing_costs"), Decimal("0.03")),
            }
        if cleaning_cost is not None:
            detail["cleaning_cost"] = cleaning_cost
        return detail or None

    def _build_taxes(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "land_assumptions_pct": self._decimal_or_default(config.get("land_assumptions"), Decimal("0.2")),
            "sla_multiplier_pct": self._decimal_or_default(
                config.get("sla_multiplier_pct"), self._DEFAULT_SLA_MULTIPLIER_PCT
            ),
            "bonus_amount_pct": self._decimal_or_default(
                config.get("bonus_amount_pct"), self._DEFAULT_BONUS_AMOUNT_PCT
            ),
            "tax_rate_pct": self._decimal_or_default(config.get("tax_rate"), Decimal("0.37")),
        }

    def _build_cleaning_cost(self, cleaning: dict[str, Any]) -> dict[str, Any] | None:
        fee = cleaning.get("fee")
        turns = cleaning.get("num_of_turns")
        if fee is None and turns is None:
            return None

        result = {
            "cost_per_clean": fee,
            "turns_per_year": turns,
        }
        if fee is not None and turns is not None:
            result["annual_cleaning_cost"] = fee * turns
        return result

    def _build_operating_expenses(self, opex: dict[str, Any]) -> list[dict[str, Any]]:
        expenses: list[dict[str, Any]] = []

        cleaning = opex.get("cleaning") or {}
        fee = cleaning.get("fee")
        turns = cleaning.get("num_of_turns")
        if fee is not None and turns is not None:
            expenses.append({"expense": "Cleaning", "monthly": fee * turns})

        pool_hot_tub = (opex.get("ranged") or {}).get("pool_hot_tub") or {}
        if pool_hot_tub.get("low") is not None:
            expenses.append(
                {"expense": "Pool/Hot Tub Maintenance", "monthly": pool_hot_tub["low"]}
            )

        absolute = opex.get("absolute") or {}
        expenses.extend(
            {"expense": self._humanize_expense_name(name), "monthly": amount}
            for name, amount in absolute.items()
            if amount is not None and name not in self._EXCLUDED_ABSOLUTE_EXPENSES
        )
        return expenses

    def _money_to_decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        if isinstance(value, int | float):
            return Decimal(str(value))

        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    def _decimal_or_default(self, value: Any, default: Decimal) -> Decimal:
        if value is None:
            return default
        return Decimal(str(value))

    def _humanize_expense_name(self, value: str) -> str:
        return value.replace("_", " ").title()
