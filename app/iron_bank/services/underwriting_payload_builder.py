from typing import Any

from pydantic import BaseModel

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)


class UnderwritingPayloadBuilder(BaseUnderwritingPayloadBuilder):
    """Builds a save payload from prepared UW data.

    This replaces the FE mapping step for automated/draft underwriting flows.
    It does not fetch data or persist anything.
    """

    def build(self, prepared: dict[str, Any] | BaseModel) -> SaveUnderwritingPayload:
        if isinstance(prepared, BaseModel):
            prepared = prepared.model_dump()

        zillow_property = prepared.get("zillow_property") or {}
        config = prepared.get("config") or {}
        opex = prepared.get("opex") or {}

        purchase_price = self._money_to_decimal(zillow_property.get("price"))
        cleaning_cost = self._build_cleaning_cost(opex.get("cleaning") or {})

        payload = {
            "zpid": zillow_property.get("id"),
            "market_id": prepared.get("market_id"),
            "deal_status": self._DEFAULT_DEAL_STATUS,
            "is_automated": True,
            "listing_url": zillow_property.get("url"),
            "property_address": zillow_property.get("address"),
            "details": self._build_details(
                purchase_price=purchase_price,
                config=config,
                cleaning_cost=cleaning_cost,
            ),
            "taxes": self._build_taxes(config) if purchase_price is not None else None,
            "operating_expenses": self._build_operating_expenses(opex),
        }
        return SaveUnderwritingPayload.model_validate(payload)

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
            if amount is not None
        )
        return expenses

    def _humanize_expense_name(self, value: str) -> str:
        return value.replace("_", " ").title()
