from decimal import Decimal
from typing import Any

import structlog
from pydantic import BaseModel

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService

logger = structlog.get_logger(__name__)


class UnderwritingPayloadBuilder(BaseUnderwritingPayloadBuilder):
    """Builds a save payload from prepared UW data.

    This replaces the FE mapping step for automated/draft underwriting flows.
    It does not fetch data or persist anything.
    """

    # Seeded optimization items all price at tier 2 for now; the analyst
    # re-tiers from the amenity catalog in the edit form.
    _AMENITY_PRICE_TIER_FIELD = "price_tier_2"
    _AMENITY_TIER_LABEL = "Mid"
    _AMENITY_METRIC = "flat"

    def build(self, prepared: dict[str, Any] | BaseModel) -> SaveUnderwritingPayload:
        if isinstance(prepared, BaseModel):
            prepared = prepared.model_dump()

        zillow_property = prepared.get("zillow_property") or {}
        config = prepared.get("config") or {}
        opex = prepared.get("opex") or {}

        purchase_price = self._money_to_decimal(zillow_property.get("price"))
        cleaning_cost = self._build_cleaning_cost(opex.get("cleaning") or {})
        property_taxes = self.build_opex_property_taxes(
            property_tax_pct=opex.get("property_tax_pct"),
            purchase_price=purchase_price,
        )

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
                property_taxes=property_taxes,
            ),
            "taxes": self._build_taxes(config) if purchase_price is not None else None,
            "operating_expenses": self._build_operating_expenses(opex, property_taxes),
            "optimization_list": self._build_optimization_list(prepared),
        }
        return SaveUnderwritingPayload.model_validate(payload)

    def build_opex_property_taxes(
        self,
        *,
        property_tax_pct: Any,
        purchase_price: Decimal | None,
        zillow_annual_tax: Decimal | None = None,
    ) -> dict[str, Any] | None:
        """Resolve the monthly Property Taxes opex item and its breakdown.

        Sources, in priority order:
        1. Market tax rate (opex_by_bedrooms.property_taxes) x purchase price.
        2. Zillow-provided annual tax amount (not wired up yet — callers will
           pass it once it is threaded through prepared zillow data).
        3. Neither -> None; the item is seeded blank for the team to fill out.

        Amounts are annual; OPEX is monthly, so both sources divide by 12.
        The returned dict is persisted on uw_details.property_taxes so the
        derivation stays auditable (mirrors cleaning_cost): the resolved
        amounts sit at the top level regardless of source, and the
        source-specific figures live under "inputs".
        """
        if property_tax_pct is not None and purchase_price is not None:
            pct = Decimal(str(property_tax_pct))
            annual = pct * purchase_price
            return {
                "source": "opex_property_tax_pct",
                "annual_amount": annual,
                "monthly_amount": annual / 12,
                "inputs": {
                    "opex_property_tax_pct": pct,
                    "purchase_price": purchase_price,
                },
            }
        if zillow_annual_tax is not None:
            return {
                "source": "zillow_annual_tax",
                "annual_amount": zillow_annual_tax,
                "monthly_amount": zillow_annual_tax / 12,
                "inputs": {},
            }
        return None

    def _build_optimization_list(
        self, prepared: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Seed the rehab budget from the amenity options prepared for this deal.

        Two groups, in this order: the options every deal gets (furnishings,
        consolidated shipping, the STR Cribs management fee) followed by the
        market's must-have amenities. Items whose tier-2 price is missing are
        still seeded with a blank amount — a visible row the analyst fills in
        beats a silently absent line item.
        """
        options_by_id = {
            option.get("id"): option
            for option in prepared.get("construction_amenities") or []
        }
        selected_ids = list(
            dict.fromkeys(
                [
                    *PrepareUwDataService.SEEDED_AMENITY_OPTION_IDS,
                    *(prepared.get("must_have_amenity_ids") or []),
                ]
            )
        )

        unknown_ids = [
            amenity_id for amenity_id in selected_ids if amenity_id not in options_by_id
        ]
        if unknown_ids:
            logger.warning(
                "_build_optimization_list: amenity ids absent from the catalog",
                zpid=(prepared.get("zillow_property") or {}).get("id"),
                market_id=prepared.get("market_id"),
                unknown_amenity_ids=unknown_ids,
            )

        return [
            self._amenity_to_optimization_item(options_by_id[amenity_id])
            for amenity_id in selected_ids
            if amenity_id in options_by_id
        ]

    def _amenity_to_optimization_item(self, option: dict[str, Any]) -> dict[str, Any]:
        price = option.get(self._AMENITY_PRICE_TIER_FIELD)
        return {
            "category": option.get("amenity_name"),
            "total_price": price,
            "base_price": price,
            "metric": self._AMENITY_METRIC,
            "tier": self._AMENITY_TIER_LABEL,
        }

    def _build_cleaning_cost(self, cleaning: dict[str, Any]) -> dict[str, Any] | None:
        fee = cleaning.get("fee")
        turns = cleaning.get("num_of_turns")
        if fee is None and turns is None:
            return None

        result = {
            "cost_per_clean": fee,
            "turns_per_month": turns,
        }
        if fee is not None and turns is not None:
            result["monthly_cleaning_cost"] = fee * turns
        return result

    def _build_operating_expenses(
        self,
        opex: dict[str, Any],
        property_taxes: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        expenses: list[dict[str, Any]] = []

        cleaning = opex.get("cleaning") or {}
        fee = cleaning.get("fee")
        turns = cleaning.get("num_of_turns")
        if fee is not None and turns is not None:
            expenses.append({"expense": "Cleaning", "monthly": fee * turns})

        # Always seeded — a blank amount means no source could resolve it and
        # the team fills it out manually.
        expenses.append(
            {
                "expense": "Property Taxes",
                "monthly": (
                    property_taxes["monthly_amount"] if property_taxes else None
                ),
            }
        )

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
