from typing import Any

import structlog
from pydantic import BaseModel

from app.iron_bank.enums import UnderwritingSource
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)

logger = structlog.get_logger(__name__)


class UnderwritingPayloadBuilder(BaseUnderwritingPayloadBuilder):
    """Builds a save payload from prepared UW data.

    This replaces the FE mapping step for automated/draft underwriting flows.
    The opex and rehab line items are built by the shared base class off the
    market context embedded in ``prepared``. It does not fetch data or persist
    anything.
    """

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
            "source": UnderwritingSource.ADUS,
            "deal_status": self._DEFAULT_DEAL_STATUS,
            "is_automated": True,
            "listing_url": zillow_property.get("url"),
            "property_address": zillow_property.get("address"),
            "street": prepared.get("street"),
            "city": prepared.get("city"),
            "state": prepared.get("state"),
            "details": self._build_details(
                purchase_price=purchase_price,
                config=config,
                cleaning_cost=cleaning_cost,
                property_taxes=property_taxes,
            ),
            "taxes": self._build_taxes(config) if purchase_price is not None else None,
            "operating_expenses": self._build_operating_expenses(opex, property_taxes),
            "optimization_list": self._build_optimization_list(
                prepared, zpid=zillow_property.get("id")
            ),
        }
        return SaveUnderwritingPayload.model_validate(payload)
