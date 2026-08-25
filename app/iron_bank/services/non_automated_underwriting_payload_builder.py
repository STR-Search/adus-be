from typing import Any

from app.iron_bank.schemas.prepare_uw import MarketContext
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services import opex_catalog
from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)


class NonAutomatedUnderwritingPayloadBuilder(BaseUnderwritingPayloadBuilder):
    """Builds a non-automated save payload from external Zillow data.

    Used by the create-from-URL flow: the external API has already been called
    and mapped to a ``zillow_property`` dict. When a ``market_context`` is given
    the opex and rehab line items are seeded from it through the same base-class
    helpers the automated flow uses (a market-less deal gets a zeroed template
    context — see ``PrepareUwDataService.to_template_market_context``); without
    one, financing and tax terms are seeded with defaults and no line items are
    produced. The fetched ``zillow_property`` is stored on ``uw_details``
    (``is_automated=False``), so it is read back from storage rather than
    hydrated live. Ownership follows the market's analyst owner when there is
    one, otherwise ``current_user_id``. Does not fetch data or persist anything.
    """

    def build_from_zillow_property(
        self,
        *,
        listing_url: str,
        zillow_property: dict[str, Any],
        market_context: MarketContext | None = None,
        current_user_id: int | None = None,
    ) -> SaveUnderwritingPayload:
        # street/city/state ride along on the fetched dict but belong on the
        # underwritings row's own columns, not in the stored zillow_property
        # blob — lift them out before the rest is persisted on uw_details.
        zillow_property = dict(zillow_property)
        street = zillow_property.pop("street", None)
        city = zillow_property.pop("city", None)
        state = zillow_property.pop("state", None)

        purchase_price = self._money_to_decimal(zillow_property.get("price"))

        context = market_context.model_dump() if market_context else {}
        # No market context means no market-derived terms, so the base defaults
        # apply — the same thing an empty config dict yields.
        config = context.get("config") or {}
        opex = context.get("opex") or {}
        cleaning_cost = opex_catalog.build_cleaning_cost(opex.get("cleaning") or {})
        property_taxes = opex_catalog.build_opex_property_taxes(
            property_tax_pct=opex.get("property_tax_pct"),
            purchase_price=purchase_price,
        )

        details = (
            self._build_details(
                purchase_price=purchase_price,
                config=config,
                cleaning_cost=cleaning_cost,
                property_taxes=property_taxes,
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
            # Null for a template (market-less) deal — see
            # to_template_market_context, which clears the identity fields.
            "market_id": context.get("market_id"),
            # A market-less (template) deal has no analyst owner to inherit, so
            # it falls to the analyst who created it.
            "owner_id": self._resolve_owner_id(
                context, fallback_user_id=current_user_id
            ),
            "property_address": zillow_property.get("address"),
            "street": street,
            "city": city,
            "state": state,
            "bedrooms": self._as_int(zillow_property.get("bedrooms")),
            "bathrooms": zillow_property.get("bathrooms"),
            "purchase_price": purchase_price,
            "details": details,
            "taxes": self._build_taxes(config) if purchase_price is not None else None,
        }
        if market_context is not None:
            payload["operating_expenses"] = self._build_operating_expenses(
                opex, property_taxes
            )
            payload["optimization_list"] = self._build_optimization_list(
                context, zpid=zillow_property.get("id")
            )
        return SaveUnderwritingPayload.model_validate(payload)
