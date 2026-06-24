from typing import Any

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)


class NonAutomatedUnderwritingPayloadBuilder(BaseUnderwritingPayloadBuilder):
    """Builds a non-automated save payload from external Zillow data.

    Used by the create-from-URL flow: the external API has already been called
    and mapped to a ``zillow_property`` dict. Unlike the automated flow there is
    no market context, so no opex; financing and tax terms are seeded with
    defaults for the analyst to refine later. The fetched ``zillow_property`` is
    stored on ``uw_details`` (``is_automated=False``), so it is read back from
    storage rather than hydrated live. Does not fetch data or persist anything.
    """

    def build_from_zillow_property(
        self,
        *,
        listing_url: str,
        zillow_property: dict[str, Any],
    ) -> SaveUnderwritingPayload:
        purchase_price = self._money_to_decimal(zillow_property.get("price"))

        details = (
            self._build_details(
                purchase_price=purchase_price,
                config={},
                cleaning_cost=None,
            )
            or {}
        )
        details["zillow_property"] = zillow_property

        # NOTE: the top-level ``zpid`` column has a FK to
        # ``zillow.scheduled_listings`` (the automated source of truth). A
        # property fetched live from Zillow is not in that table, so we must
        # leave the column null here — the zpid is preserved on
        # ``details.zillow_property.id``.
        payload = {
            "deal_status": self._DEFAULT_DEAL_STATUS,
            "is_automated": False,
            "listing_url": listing_url,
            "property_address": zillow_property.get("address"),
            "purchase_price": purchase_price,
            "details": details,
            "taxes": self._build_taxes({}) if purchase_price is not None else None,
        }
        return SaveUnderwritingPayload.model_validate(payload)
